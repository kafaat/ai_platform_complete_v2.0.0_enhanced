"""Manual irrigation slice — route wiring of the live re-check, confirm actor/deviation, and
independent verification (IRR slice, owner decisions 2026-10-06).

The pure verdicts are unit-tested in ``test_irrx1_2_manual_execution_lifecycle.py``; these tests
prove the ROUTES call them at the moment of action and persist what the decisions require, with a
fake connection that records every statement (no database: route wiring, not SQL semantics —
the SQL/RLS behaviour is certified by ``test_irrx1_pcert_real_postgres.py``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

route = pytest.importorskip("api.routers.irrigation_engineering")
from fastapi import HTTPException  # noqa: E402

TENANT = "00000000-0000-0000-0000-00000000a11c"
OPERATOR = SimpleNamespace(tenant_id=TENANT, user_id="u-operator")
VERIFIER = SimpleNamespace(tenant_id=TENANT, user_id="u-verifier")


class FakeConn:
    def __init__(self, row: dict, *, confirmer: str | None = "u-operator"):
        self.row = row
        self.confirmer = confirmer
        self.executed: list[tuple[str, tuple]] = []

    @contextlib.asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, sql, *args):
        return self.row

    async def fetchval(self, sql, *args):
        assert "irrigation_manual_execution_events" in sql
        return self.confirmer

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))

    def events(self) -> list[dict]:
        return [
            json.loads(args[5] if "'confirmed','confirmed'" not in sql else args[3])
            for sql, args in self.executed
            if sql.startswith("INSERT INTO irrigation_manual_execution_events")
        ]

    def updates(self) -> list[str]:
        return [sql for sql, _ in self.executed if sql.startswith("UPDATE")]


def _row(state: str, **kw) -> dict:
    now = datetime.now(UTC)
    base = {
        "execution_id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": TENANT,
        "field_id": "fld-1",
        "season_id": "sea-1",
        "system_id": "sys-1",
        "recommendation_id": "xplan_1",
        "recommendation_digest": "c" * 64,
        "decision_id": "dec_1",
        "execution_plan_id": "xplan_1",
        "plan_digest": "c" * 64,
        "execution_mode": "manual_measured",
        "state": state,
        "target_depth_mm": 20.0,
        "target_volume_m3": 1000.0,
        "nominal_flow_m3_h": 100.0,
        "valid_from": now - timedelta(hours=12),
        "valid_until": now + timedelta(hours=12),
        "created_by": "u-planner",
    }
    base.update(kw)
    return base


def _bound_state(**kw) -> dict:
    base = {
        "status": "ok",
        "authoritative": True,
        "execution_plan_id": "xplan_1",
        "decision_id": "dec_1",
        "plan_digest": "c" * 64,
        "review_state": "approved",
        "decision_value_digest": "d" * 64,
        "current_decision_value_digest": "d" * 64,
        "bound": True,
    }
    base.update(kw)
    return base


def _install(monkeypatch, conn: FakeConn, *, state=None, raises: int | None = None):
    @contextlib.asynccontextmanager
    async def _tc(_user):
        yield conn

    calls = []

    async def _plan_state(plan_id, *, tenant_id=None):
        calls.append((plan_id, tenant_id))
        if raises:
            raise HTTPException(status_code=raises, detail="down")
        return state or _bound_state()

    monkeypatch.setattr(route, "tenant_connection", _tc)
    monkeypatch.setattr(route, "get_execution_plan_state", _plan_state)
    return calls


def _start(conn, user=OPERATOR):
    req = route.ManualExecutionTransitionRequest(target_state="started")
    return asyncio.run(
        route.transition_manual_execution_endpoint(conn.row["execution_id"], req, user=user)
    )


# ── start: the live re-check is made, and its verdict governs ───────────────────────────
def test_start_rechecks_the_live_plan_and_records_what_it_verified(monkeypatch):
    conn = FakeConn(_row("approved"))
    calls = _install(monkeypatch, conn)
    out = _start(conn)
    assert out["state"] == "started"
    assert calls == [("xplan_1", TENANT)]
    assert conn.events()[0]["plan_recheck"]["decision_value_digest"] == "d" * 64


@pytest.mark.parametrize(
    ("state", "raises", "reason"),
    [
        (_bound_state(plan_digest="f" * 64), None, "APPROVED_PLAN_DIGEST_CHANGED"),
        (_bound_state(review_state="rejected"), None, "APPROVAL_WITHDRAWN"),
        (
            _bound_state(current_decision_value_digest="e" * 64),
            None,
            "APPROVED_DECISION_VERSION_CHANGED",
        ),
        (None, 503, "APPROVED_PLAN_RECHECK_UNAVAILABLE"),
        (None, 404, "APPROVED_PLAN_NOT_FOUND"),
    ],
)
def test_start_fails_closed_and_writes_nothing(monkeypatch, state, raises, reason):
    conn = FakeConn(_row("approved"))
    _install(monkeypatch, conn, state=state, raises=raises)
    with pytest.raises(HTTPException) as exc:
        _start(conn)
    assert exc.value.status_code == 409 and exc.value.detail == reason
    assert conn.executed == []


# ── confirm: re-check against the executed window, actor + deviation recorded ───────────
def _confirm(conn, user=OPERATOR, **kw):
    row = conn.row
    base = dict(
        started_at=row["valid_from"] + timedelta(hours=1),
        stopped_at=row["valid_from"] + timedelta(hours=11),
        completion_ratio=1,
        meter_start_m3=100,
        meter_end_m3=1100,
    )
    base.update(kw)
    req = route.ManualExecutionConfirmRequest(
        confirmation=route.ManualExecutionConfirmation(**base)
    )
    return asyncio.run(route.confirm_manual_execution(row["execution_id"], req, user=user))


def test_confirm_records_the_confirming_actor_and_the_live_recheck(monkeypatch):
    conn = FakeConn(_row("stopped"))
    _install(monkeypatch, conn)
    result = _confirm(conn, meter_end_m3=900, deviation_reason="pump tripped")
    assert result.deviation_pct == pytest.approx(-0.2)
    event = conn.events()[0]
    assert event["to"] == "confirmed" and event["actor"] == "u-operator"
    assert event["deviation_reason"] == "pump tripped"
    assert event["plan_recheck"]["plan_digest"] == "c" * 64


def test_confirm_beyond_tolerance_without_reason_is_422_and_writes_nothing(monkeypatch):
    conn = FakeConn(_row("stopped"))
    _install(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _confirm(conn, meter_end_m3=800)
    assert exc.value.status_code == 422
    assert conn.executed == []


def test_confirm_of_an_execution_outside_the_approved_window_is_refused(monkeypatch):
    conn = FakeConn(_row("stopped"))
    _install(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _confirm(conn, stopped_at=conn.row["valid_until"] + timedelta(minutes=5))
    assert exc.value.detail == "EXECUTED_OUTSIDE_APPROVED_WINDOW"
    assert conn.executed == []


# ── verify: independent, and a refusal leaves a record ─────────────────────────────────
def _verify(conn, user, **kw):
    base = dict(
        as_applied_digest="a" * 64,
        reviewer_id="ignored-client-value",
        reviewed_at=datetime.now(UTC),
        evidence_digests=["b" * 64],
        volume_verified=True,
        timing_verified=True,
        field_verified=True,
    )
    base.update(kw)
    req = route.ManualExecutionVerifyRequest(verification=route.ManualVerificationInput(**base))
    return asyncio.run(route.verify_manual_execution(conn.row["execution_id"], req, user=user))


@pytest.mark.parametrize("who", ["u-operator", "u-planner"])
def test_the_confirmer_or_creator_cannot_verify(monkeypatch, who):
    conn = FakeConn(_row("confirmed", as_applied={}, confirmation={}, as_applied_digest="a" * 64))
    _install(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _verify(conn, SimpleNamespace(tenant_id=TENANT, user_id=who))
    assert exc.value.detail == "VERIFIER_MUST_BE_INDEPENDENT"
    assert conn.executed == []


def test_an_execution_without_a_recorded_confirmer_cannot_be_verified(monkeypatch):
    conn = FakeConn(
        _row("confirmed", as_applied={}, confirmation={}, as_applied_digest="a" * 64),
        confirmer=None,
    )
    _install(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _verify(conn, VERIFIER)
    assert exc.value.detail == "CONFIRMER_NOT_RECORDED"


def test_a_refused_verification_is_recorded_before_the_refusal(monkeypatch):
    conn = FakeConn(_row("confirmed", as_applied={}, confirmation={}, as_applied_digest="a" * 64))
    _install(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _verify(conn, VERIFIER, volume_verified=False)
    assert exc.value.status_code == 409
    assert conn.updates() == []  # no state change
    (event,) = conn.events()
    assert event["verification_rejected"] is True and event["actor"] == "u-verifier"
    assert "VOLUME_NOT_VERIFIED" in event["blocking_reasons"]
