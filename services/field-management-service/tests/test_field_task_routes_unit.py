"""field-management-service task/inspection routes — unit contract (no database).

The live behaviour (RLS, hand-off, evidence versions, close gate, cost trigger, expense link) is
measured on PostgreSQL by tests_v9/test_field_task_inspection_live_pg.py. This file pins what can
be decided without a database: the gateway identity check, the role→permission map against the
platform's own matrix, the evidence digest formula v274's guard recomputes, the pure hand-off view,
and the refusal mapping of the expense link.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SERVICE_DIR = Path(__file__).resolve().parents[1]
ROOT = SERVICE_DIR.parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.append(str(SERVICE_DIR))

pytest.importorskip("fastapi")

import fm_gateway  # noqa: E402
import fm_task_costs  # noqa: E402
import fm_task_inspection  # noqa: E402
from fastapi import HTTPException  # noqa: E402

TENANT = "11111111-1111-4111-8111-111111111111"


def _status(fn, *args):
    with pytest.raises(HTTPException) as err:
        fn(*args)
    return err.value.status_code, err.value.detail


# ── gateway identity ────────────────────────────────────────────────────────


def test_the_dedicated_token_is_required_and_fails_closed(monkeypatch):
    monkeypatch.delenv("FIELD_TASKS_SERVICE_TOKEN", raising=False)
    assert _status(fm_gateway.authorize, "t", TENANT, "7", "manager")[0] == 503
    monkeypatch.setenv("FIELD_TASKS_SERVICE_TOKEN", "secret-token")
    assert _status(fm_gateway.authorize, None, TENANT, "7", "manager")[0] == 401
    assert _status(fm_gateway.authorize, "secret-tokeX", TENANT, "7", "manager")[0] == 401
    # The shared agent token is not this channel's token.
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "agent")
    assert _status(fm_gateway.authorize, "agent", TENANT, "7", "manager")[0] == 401


def test_trusted_tenant_and_user_are_required(monkeypatch):
    monkeypatch.setenv("FIELD_TASKS_SERVICE_TOKEN", "secret-token")
    assert _status(fm_gateway.authorize, "secret-token", TENANT, " ", "manager")[0] == 403
    assert _status(fm_gateway.authorize, "secret-token", "not-a-uuid", "7", "manager")[0] == 403
    assert _status(fm_gateway.authorize, "secret-token", None, "7", "manager")[0] == 403
    caller = fm_gateway.authorize("secret-token", TENANT.upper(), " 7 ", "Expert")
    assert (caller.tenant_id, caller.user_id, caller.role) == (TENANT, "7", "agronomist")


def test_an_unknown_role_claim_holds_no_permission(monkeypatch):
    monkeypatch.setenv("FIELD_TASKS_SERVICE_TOKEN", "secret-token")
    for claim in ("platform_admin", "", None, "root"):
        caller = fm_gateway.authorize("secret-token", TENANT, "7", claim)
        assert not any(caller.can(p) for p in fm_gateway.CHECKED_PERMISSIONS)
        assert _status(fm_gateway.require, caller, fm_gateway.FIELD_VIEW)[0] == 403


def _platform_authorization():
    platform = ROOT / "services" / "sahool-platform"
    if str(platform) not in sys.path:
        sys.path.insert(0, str(platform))
    return importlib.import_module("core.authorization")


# The six permissions the task routes check, fixed here so a permission that vanishes from every
# role (and so from a map-derived set) still fails the comparison below.
ROUTE_PERMISSIONS = frozenset(
    {
        "field:view",
        "field:edit",
        "observation:record",
        "inspection:review",
        "analytics:view",
        "activity:execute",
    }
)


def test_role_permissions_equal_the_platform_matrix():
    """The service mirrors the platform's role matrix for the permissions it checks; drift fails.

    Every tenant role of core's UserRole is compared (a role missing from the service map holds
    nothing there, so it fails unless the platform also grants it none of the six); platform_admin
    is not a tenant role and holds none of them in this service.
    """
    auth = _platform_authorization()
    routes = {
        fm_gateway.FIELD_VIEW,
        fm_gateway.FIELD_EDIT,
        fm_gateway.OBSERVATION_RECORD,
        fm_gateway.INSPECTION_REVIEW,
        fm_gateway.ANALYTICS_VIEW,
        fm_gateway.ACTIVITY_EXECUTE,
    }
    assert routes == ROUTE_PERMISSIONS
    assert fm_gateway.CHECKED_PERMISSIONS == ROUTE_PERMISSIONS
    tenant_roles = [r for r in auth.UserRole if r is not auth.UserRole.PLATFORM_ADMIN]
    assert len(tenant_roles) == 5
    for platform_role in tenant_roles:
        granted = fm_gateway.ROLE_PERMISSIONS.get(platform_role.value, frozenset())
        platform_granted = {p.value for p in auth._ROLE_PERMISSIONS[platform_role]}
        assert granted == platform_granted & ROUTE_PERMISSIONS, platform_role.value
    assert set(fm_gateway.ROLE_PERMISSIONS) == {r.value for r in tenant_roles}
    # Every alias the gateway accepts is the platform's alias (api/main.py:_ROLE_ALIASES).
    main_src = (ROOT / "services/sahool-platform/api/main.py").read_text(encoding="utf-8")
    for alias, role in fm_gateway.ROLE_ALIASES.items():
        assert f'"{alias}": UserRole.{role.upper()}' in main_src, alias


# ── evidence digest and the hand-off view ───────────────────────────────────


def test_the_evidence_digest_is_the_formula_v274_recomputes():
    sha = "a" * 64
    expected = hashlib.sha256(f"e-1|{sha}|notes | with bar".encode()).hexdigest()
    assert fm_task_inspection.evidence_digest("e-1", sha, "notes | with bar") == expected
    assert fm_task_inspection.evidence_digest(None, None, None) == hashlib.sha256(b"||").hexdigest()
    migration = (ROOT / "migrations/v274_inspection_evidence_versions.sql").read_text(
        encoding="utf-8"
    )
    assert (
        "coalesce(NEW.photo_evidence_id::text, '') || '|' || coalesce(NEW.photo_content_sha256, '')"
        in migration
    )
    assert "|| '|' || coalesce(NEW.notes, '')" in migration


def _caller(user="9", role="manager"):
    return fm_gateway.Caller(TENANT, user, role)


def _task(assignee="5", status="in_progress", evidence=(), photo=None):
    return {
        "assigned_to": assignee,
        "status": status,
        "created_at": None,
        "inspection_due_at": None,
        "inspection_assigned_by": "9",
        "evidence": list(evidence),
        "photo": photo,
    }


def _event(rev, action, assignee="5", actor="5", version=None):
    return {
        "revision": rev,
        "action": action,
        "previous_assignee": assignee,
        "assignee": assignee,
        "actor": actor,
        "reason": None,
        "evidence_version": version,
    }


PHOTO = {"evidence_id": "e-1", "content_sha256": "b" * 64}
V1 = {"version": 1, "photo_evidence_id": None, "photo_content_sha256": None, "notes": "n"}
V2 = {"version": 2, "photo_evidence_id": "e-1", "photo_content_sha256": "b" * 64, "notes": "n"}


def test_the_view_offers_accept_to_the_assignee_only():
    fresh = fm_task_inspection.view(_task(), [], _caller("5", "worker"))
    assert (fresh["review_state"], fresh["can_accept"], fresh["can_submit"]) == (
        "assigned",
        True,
        False,
    )
    other = fm_task_inspection.view(_task(), [], _caller("6", "worker"))
    assert other["can_accept"] is False and other["can_reassign"] is False
    closed = fm_task_inspection.view(_task(status="completed"), [], _caller("5", "worker"))
    assert closed["can_accept"] is False


def test_an_approval_holds_only_while_the_pin_photo_is_the_approved_versions():
    events = [
        _event(1, "accept"),
        _event(2, "submit", version=1),
        _event(3, "approve", actor="9", version=1),
    ]
    held = fm_task_inspection.view(_task(evidence=[V1]), events, _caller())
    assert (held["evidence_approved"], held["evidence_pending_review"]) == (True, False)
    # scout-ingest stores a photo after the approval: the approved version no longer matches.
    stale = fm_task_inspection.view(_task(evidence=[V1], photo=PHOTO), events, _caller())
    assert (stale["evidence_approved"], stale["evidence_pending_review"]) == (False, True)
    assert stale["current_evidence"] == {
        "version": None,
        "photo_evidence_id": "e-1",
        "photo_content_sha256": "b" * 64,
    }
    assert stale["approved_evidence"] == V1
    # After a new submit and approval of v2 (the photo record), it holds again.
    events += [_event(4, "submit", version=2), _event(5, "approve", actor="9", version=2)]
    again = fm_task_inspection.view(_task(evidence=[V1, V2], photo=PHOTO), events, _caller())
    assert again["evidence_approved"] is True and again["current_evidence"] == V2


def test_review_is_for_someone_other_than_the_assignee_with_inspection_review():
    events = [_event(1, "accept"), _event(2, "submit", version=1)]
    task = _task(evidence=[V1])
    assert fm_task_inspection.view(task, events, _caller("9", "agronomist"))["can_review"] is True
    assert fm_task_inspection.view(task, events, _caller("5", "agronomist"))["can_review"] is False
    assert fm_task_inspection.view(task, events, _caller("9", "worker"))["can_review"] is False


def test_a_reopen_or_reassign_resets_acceptance():
    for action in ("reopen", "reassign"):
        events = [_event(1, "accept"), _event(2, action)]
        view = fm_task_inspection.view(_task(), events, _caller("5", "worker"))
        assert view["accepted"] is False and view["can_accept"] is True


def test_the_finding_request_shape():
    model = fm_task_inspection.InspectionFinding
    with pytest.raises(ValueError):
        model(expected_revision=1, action="approve", reason="ok")  # names no version
    with pytest.raises(ValueError):
        model(expected_revision=1, action="approve", reason="ok", evidence_version=1, notes="x")
    with pytest.raises(ValueError):
        model(expected_revision=1, action="submit", reason="ok", evidence_version=1)
    assert model(expected_revision=1, action="submit", reason="  ok ").reason == "ok"


# ── expense link and cost trace helpers ─────────────────────────────────────


class _GuardRefusal(Exception):
    sqlstate = "23514"

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def test_link_guard_refusals_map_to_client_errors():
    for message, expected in (
        ("original_expense_required", (422, "original_expense_required")),
        ("task_farm_mismatch", (422, "task_location_mismatch")),
        ("task_field_mismatch", (422, "task_location_mismatch")),
        ("entry_already_linked", (409, "entry_already_linked")),
    ):
        refusal = fm_task_costs.link_refusal(_GuardRefusal(message))
        assert (refusal.status_code, refusal.detail) == expected
    assert fm_task_costs.link_refusal(RuntimeError("connection reset")) is None
    migration = (ROOT / "migrations/v276_task_cost_trace.sql").read_text(encoding="utf-8")
    for message in (
        "original_expense_required",
        "task_farm_mismatch",
        "task_field_mismatch",
        "entry_already_linked",
    ):
        assert f"RAISE EXCEPTION '{message}' USING ERRCODE = '23514'" in migration


def test_expense_totals_net_a_correction_per_currency():
    rows = [
        {"entry_type": "expense", "amount": "10.00", "currency": "YER", "reverses_entry_id": None},
        {"entry_type": "expense", "amount": "4.00", "currency": "YER", "reverses_entry_id": "e1"},
        {"entry_type": "expense", "amount": "2.50", "currency": "USD", "reverses_entry_id": None},
        {"entry_type": "income", "amount": "99", "currency": "YER", "reverses_entry_id": None},
    ]
    assert fm_task_costs.expense_totals(rows) == {"YER": "6.00", "USD": "2.50"}


def test_the_task_routes_are_registered_under_the_gateway_prefix():
    spec = importlib.util.spec_from_file_location("fm_main_routes_unit", SERVICE_DIR / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    routes = {(m, r.path) for r in mod.app.routes for m in getattr(r, "methods", ())}
    prefix = "/internal/field-tasks"
    expected = {
        ("GET", f"{prefix}/fields/{{field_id}}/inspection-assignees"),
        ("GET", f"{prefix}/fields/{{field_id}}/pins/{{pin_id}}/inspection-task"),
        ("POST", f"{prefix}/fields/{{field_id}}/pins/{{pin_id}}/inspection-task"),
        ("GET", f"{prefix}/fields/{{field_id}}/tasks/{{task_id}}/handoff"),
        ("POST", f"{prefix}/fields/{{field_id}}/tasks/{{task_id}}/handoff/accept"),
        ("POST", f"{prefix}/fields/{{field_id}}/tasks/{{task_id}}/handoff/reassign"),
        ("POST", f"{prefix}/fields/{{field_id}}/tasks/{{task_id}}/handoff/finding"),
        ("GET", f"{prefix}/tasks/{{task_id}}/cost-trace"),
        ("POST", f"{prefix}/farm-book/entries/{{entry_id}}/task"),
    }
    assert expected <= routes


def test_equipment_identity_is_part_of_evidence_digest():
    digest = fm_task_inspection.evidence_digest
    assert digest(None, None, "notes|x") == hashlib.sha256(b"||notes|x").hexdigest()
    assert (
        digest(None, None, "notes|x", "eqp_A")
        == hashlib.sha256(b"equipment:eqp_A|||notes|x").hexdigest()
    )
    assert digest(None, None, "notes|x", "eqp_A") != digest(None, None, "notes|x", "eqp_B")


def test_submit_carries_equipment_identity():
    request = fm_task_inspection.InspectionFinding(
        action="submit", expected_revision=1, reason="finding", equipment_id="eqp_A"
    )
    assert request.equipment_id == "eqp_A"


@pytest.mark.parametrize("action", ["approve", "return"])
def test_reviewer_cannot_replace_the_equipment_identity(action):
    with pytest.raises(ValueError):
        fm_task_inspection.InspectionFinding(
            action=action,
            expected_revision=2,
            reason="review",
            evidence_version=1,
            equipment_id="eqp_B",
        )


@pytest.mark.parametrize("equipment_id", ["", "a|b", " x ", "a" * 51])
def test_invalid_equipment_reference_refused(equipment_id):
    with pytest.raises(ValueError):
        fm_task_inspection.InspectionFinding(
            action="submit", expected_revision=1, reason="finding", equipment_id=equipment_id
        )


# ── pre-v292 store (Devin review on #1666) ─────────────────────────────────
# Applying v292 needs a separate approval, so a rebuilt field-management can run against a store
# without inspection_evidence_versions.equipment_id. Legacy evidence must keep reading and
# writing; only an explicit equipment declaration is refused, never silently dropped.


class _EvidenceStore:
    """Answers the inspection queries the way a v274..v291 (or v292) store would."""

    def __init__(self, *, has_equipment: bool):
        self.has_equipment = has_equipment
        self.queries: list[str] = []
        self.inserts: list[tuple] = []

    async def fetchval(self, sql, *args):
        self.queries.append(sql)
        assert "pg_attribute" in sql and "equipment_id" in sql
        return self.has_equipment

    async def fetchrow(self, sql, *args):
        self.queries.append(sql)
        if "FROM field_tasks" in sql:
            return {"assigned_to": "u1", "status": "open", "pin_id": "pin-1"}
        return None  # no prior version / no photo

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        if "inspection_evidence_versions" in sql and not self.has_equipment:
            assert "NULL AS equipment_id" in sql, "pre-v292 read must not name the column"
        return []

    async def execute(self, sql, *args):
        self.queries.append(sql)
        if "equipment_id" in sql and not self.has_equipment:
            raise AssertionError("pre-v292 write named a column the store does not have")
        self.inserts.append(args)
        return "INSERT 0 1"


def _run(coro):
    import asyncio

    return asyncio.run(coro)


@pytest.mark.parametrize("has_equipment", [False, True])
def test_inspection_read_works_with_and_without_the_v292_column(has_equipment):
    store = _EvidenceStore(has_equipment=has_equipment)
    task, events = _run(
        fm_task_inspection._load(
            store, fm_gateway.Caller(TENANT, "u1", "owner"), "f1", "t1", write=False
        )
    )
    assert task["evidence"] == [] and events == []
    reads = [q for q in store.queries if "FROM inspection_evidence_versions" in q]
    assert reads and ("NULL AS equipment_id" in reads[0]) is (not has_equipment)


def test_pre_v292_legacy_evidence_write_keeps_the_v274_digest():
    store = _EvidenceStore(has_equipment=False)
    version = _run(
        fm_task_inspection._record_version(
            store, fm_gateway.Caller(TENANT, "u1", "owner"), "f1", "t1", "pin-1", None, "note"
        )
    )
    assert version == 1
    (args,) = store.inserts
    assert len(args) == 10  # no equipment column
    assert args[8] == fm_task_inspection.evidence_digest(None, None, "note")


def test_pre_v292_equipment_declaration_is_refused_not_dropped():
    store = _EvidenceStore(has_equipment=False)
    with pytest.raises(HTTPException) as err:
        _run(
            fm_task_inspection._record_version(
                store,
                fm_gateway.Caller(TENANT, "u1", "owner"),
                "f1",
                "t1",
                "pin-1",
                None,
                "note",
                "eqp_A",
            )
        )
    assert err.value.status_code == 409 and "v292" in err.value.detail
    assert store.inserts == []


def test_v292_equipment_declaration_is_written_and_digested():
    store = _EvidenceStore(has_equipment=True)
    _run(
        fm_task_inspection._record_version(
            store, fm_gateway.Caller(TENANT, "u1", "owner"), "f1", "t1", "pin-1", None, "n", "eqp_A"
        )
    )
    (args,) = store.inserts
    assert args[-1] == "eqp_A"
    assert args[8] == fm_task_inspection.evidence_digest(None, None, "n", "eqp_A")
