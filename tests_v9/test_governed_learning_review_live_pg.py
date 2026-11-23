"""Governed learning proposals have a review path (G14 / F-D02, live PG).

``governed_model_promotion_candidates`` and ``irrigation_learning_proposals`` are written with
``review_required`` and ``auto_promote``/``auto_adjust`` false (``api/learning_feedback.py`` and
``api/irrigation_closed_loop_runtime.py``), but before this change no code read the first table
and no path wrote ``approved``/``rejected`` to either: the ``review_requested`` event was the end
of the line. These tests drive the two review routes over HTTP into the platform app, on a
migrated Postgres, through a NOBYPASSRLS role:

* a reviewer holding ``decision:model-activation-approve`` lists the tenant's pending proposals
  (another tenant's are invisible) and records accept/reject with identity, time and reason;
* a role without the permission is refused (403), another tenant's id and an unknown id are 404,
  an illegal transition (accept from ``blocked``, a stale pool digest) is 409, a missing reason
  is 422, and the same decision again replays without a second event while the opposite
  decision is 409;
* recording ``accept`` changes only the review columns: ``auto_promote``/``auto_adjust`` stay
  false, the evidence and proposed parameter changes are untouched, and the response says
  ``applied: false``.

Needs ``TEST_DATABASE_URL`` pointing at a database built from ``migrations/MANIFEST.txt``.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

# Switch read before any import (test_certification_switch_precedes_importorskip): on the
# certifying CI step a missing dependency or an unusable database fails the run, not a skip.
_CERTIFICATION_REQUIRED = os.getenv("GOVERNED_LEARNING_REVIEW_CERTIFICATION_REQUIRED") == "1"


def _require(module: str):
    """Import ``module``; under the certification switch a missing one fails the run."""
    if _CERTIFICATION_REQUIRED:
        return importlib.import_module(module)
    return pytest.importorskip(module)


asyncpg = _require("asyncpg")
httpx = _require("httpx")
_require("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
# The module connects as the schema owner and creates its own throwaway NOBYPASSRLS role for the
# request path. On its certifying CI step the owner comes from TEST_DATABASE_ADMIN_URL, so the
# step's TEST_DATABASE_URL never names a privileged role.
DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
_TABLES = ("governed_model_promotion_candidates", "irrigation_learning_proposals", "events")
_POOL = "a" * 64
_REVIEW_EVENT = "learning.proposal.review_recorded"


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in _TABLES:
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        f"GOVERNED_LEARNING_REVIEW_CERTIFICATION_REQUIRED=1 but the live database is unusable: {_WHY}"
    )
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import api.main as main

    return main


async def _seed_candidate(owner, tenant, candidate_id, status, evidence):
    await owner.execute(
        """INSERT INTO governed_model_promotion_candidates
        (tenant_id,candidate_id,season_id,task,status,review_required,auto_promote,evidence,
         candidate_digest)
        VALUES ($1::uuid,$2,'season-g14','yield_forecast',$3,TRUE,FALSE,$4::jsonb,$5)""",
        tenant,
        candidate_id,
        status,
        json.dumps(evidence),
        uuid.uuid4().hex + uuid.uuid4().hex,
    )


async def _seed_proposal(owner, tenant, proposal_id, status):
    await owner.execute(
        """INSERT INTO irrigation_learning_proposals
        (tenant_id,field_id,season_id,proposal_id,status,review_required,auto_adjust,
         proposed_parameter_changes,source_lineage,evidence_digest,proposal_digest)
        VALUES ($1::uuid,'field-g14','season-g14',$2,$3,TRUE,FALSE,$4::jsonb,$5::jsonb,$6,$7)""",
        tenant,
        proposal_id,
        status,
        json.dumps([{"parameter": "p", "proposed_delta": 1}]),
        json.dumps({"closed_loop_digest": "c" * 64}),
        "e" * 64,
        uuid.uuid4().hex + uuid.uuid4().hex,
    )


async def _scenario(monkeypatch) -> dict:
    main = _platform()
    from core.canonical_schemas import UserRole, UserSchema

    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    ready, blocked, theirs = (f"gmp_{uuid.uuid4().hex[:12]}" for _ in range(3))
    proposal = f"ilp_{uuid.uuid4().hex[:12]}"
    owner = await asyncpg.connect(DSN)
    role = None
    if await owner.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ):
        role = f"g14_rls_{uuid.uuid4().hex[:10]}"
        await owner.execute(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}";'
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}";'
            f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "{role}";'
        )

    async def setup(conn):
        if role:
            await conn.execute(f'SET ROLE "{role}"')

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4, setup=setup)
    monkeypatch.setattr(main, "_DB_POOL", pool)
    # The per-client minute window is shared by every test in the process; this journey
    # must not spend it for the live tests that follow (as test_farm_access_scope_live_pg).
    monkeypatch.setattr(main, "_RATE_LIMIT_PER_MIN", 0, raising=False)
    await _seed_candidate(owner, tenant, ready, "review_ready", {"pool_digest": _POOL, "n": 4})
    await _seed_candidate(owner, tenant, blocked, "blocked", {"n": 1})
    await _seed_candidate(owner, other, theirs, "review_ready", {"n": 4})
    await _seed_proposal(owner, tenant, proposal, "review_ready")
    acting = {"user": None}
    main.app.dependency_overrides[main.get_current_user] = lambda: acting["user"]
    out: dict = {}

    def as_(actor, role_, tenant_=tenant):
        acting["user"] = UserSchema(user_id=actor, tenant_id=tenant_, role=role_, name_ar="مراجع")

    async def events(entity_id):
        return await owner.fetch(
            "SELECT payload, actor_id FROM events WHERE tenant_id=$1::uuid AND event_type=$2"
            " AND payload->>'proposal_id'=$3",
            tenant,
            _REVIEW_EVENT,
            entity_id,
        )

    base = "/api/v1/learning/governed-proposals"
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=60,
        ) as client:

            async def review(kind, pid, body):
                return await client.post(f"{base}/{kind}/{pid}/review", json=body)

            accept = {"decision": "accept", "reason": "evidence reviewed"}

            # ── permission ─────────────────────────────────────────────────────────
            as_("manager-1", UserRole.MANAGER)
            out["manager_list"] = (await client.get(base)).status_code
            out["manager_review"] = (await review("model_promotion", ready, accept)).status_code

            # ── read side ──────────────────────────────────────────────────────────
            as_("owner-1", UserRole.OWNER)
            listed = await client.get(base)
            out["list_status"] = listed.status_code
            items = listed.json().get("items", []) if listed.status_code == 200 else []
            out["listed_ids"] = sorted(i["proposal_id"] for i in items)
            out["expected_ids"] = sorted([ready, blocked, proposal])
            out["listed_flags"] = {
                (i["kind"], i.get("auto_promote"), i.get("auto_adjust"), i["review_required"])
                for i in items
            }

            # ── refusals ───────────────────────────────────────────────────────────
            out["other_tenant"] = (await review("model_promotion", theirs, accept)).status_code
            out["unknown_id"] = (await review("model_promotion", "gmp_nope", accept)).status_code
            out["unknown_kind"] = (await review("weights", ready, accept)).status_code
            out["no_reason"] = (
                await review("model_promotion", ready, {"decision": "accept", "reason": "  "})
            ).status_code
            out["accept_blocked"] = (await review("model_promotion", blocked, accept)).status_code
            out["stale_pool"] = (
                await review("model_promotion", ready, {**accept, "reviewed_pool_digest": "b" * 64})
            ).status_code

            # ── accept records the decision and applies nothing ────────────────────
            body = {**accept, "reviewed_pool_digest": _POOL}
            first = await review("model_promotion", ready, body)
            out["accept"] = first.status_code, first.json() if first.status_code == 200 else None
            out["accept_row"] = dict(
                await owner.fetchrow(
                    "SELECT status, reviewed_by, reviewed_at IS NOT NULL AS has_time, auto_promote,"
                    " evidence FROM governed_model_promotion_candidates"
                    " WHERE tenant_id=$1::uuid AND candidate_id=$2",
                    tenant,
                    ready,
                )
            )
            again = await review("model_promotion", ready, body)
            out["replay"] = again.status_code, again.json() if again.status_code == 200 else None
            out["opposite"] = (
                await review("model_promotion", ready, {"decision": "reject", "reason": "x"})
            ).status_code
            out["accept_events"] = [
                (json.loads(e["payload"]), e["actor_id"]) for e in await events(ready)
            ]

            # ── reject an irrigation proposal ──────────────────────────────────────
            rej = await review("irrigation", proposal, {"decision": "reject", "reason": "too few"})
            out["reject"] = rej.status_code, rej.json() if rej.status_code == 200 else None
            out["reject_row"] = dict(
                await owner.fetchrow(
                    "SELECT status, reviewed_by, auto_adjust, proposed_parameter_changes"
                    " FROM irrigation_learning_proposals WHERE tenant_id=$1::uuid AND proposal_id=$2",
                    tenant,
                    proposal,
                )
            )
            out["reject_events"] = len(await events(proposal))
            after = await client.get(base)
            out["after_ids"] = sorted(i["proposal_id"] for i in after.json().get("items", []))
            out["theirs_row"] = await owner.fetchval(
                "SELECT status FROM governed_model_promotion_candidates"
                " WHERE tenant_id=$1::uuid AND candidate_id=$2",
                other,
                theirs,
            )
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        try:
            if await owner.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"):
                async with owner.transaction():
                    await owner.execute("SET LOCAL session_replication_role = replica")
                    await owner.execute(
                        "DELETE FROM event_outbox WHERE event_id IN (SELECT event_id FROM events"
                        " WHERE tenant_id = ANY($1::uuid[]))",
                        [tenant, other],
                    )
                    for table in (
                        "events",
                        "governed_model_promotion_candidates",
                        "irrigation_learning_proposals",
                    ):
                        await owner.execute(
                            f"DELETE FROM {table} WHERE tenant_id = ANY($1::uuid[])",
                            [tenant, other],
                        )
        finally:
            if role:
                await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
            await owner.close()
    return out


@pytest.fixture(scope="module")
def scenario():
    mp = pytest.MonkeyPatch()
    try:
        yield asyncio.run(_scenario(mp))
    finally:
        mp.undo()


def test_a_role_without_the_permission_can_neither_list_nor_review(scenario):
    assert scenario["manager_list"] == 403
    assert scenario["manager_review"] == 403


def test_the_reviewer_lists_only_this_tenants_pending_proposals(scenario):
    assert scenario["list_status"] == 200
    assert scenario["listed_ids"] == scenario["expected_ids"]
    assert scenario["listed_flags"] == {
        ("model_promotion", False, None, True),
        ("irrigation", None, False, True),
    }


def test_wrong_tenant_unknown_id_and_unknown_kind_are_refused(scenario):
    assert scenario["other_tenant"] == 404
    assert scenario["unknown_id"] == 404
    assert scenario["unknown_kind"] == 422
    assert scenario["theirs_row"] == "review_ready"


def test_an_illegal_or_unexplained_decision_is_refused(scenario):
    assert scenario["no_reason"] == 422
    assert scenario["accept_blocked"] == 409
    assert scenario["stale_pool"] == 409


def test_accept_records_identity_time_and_reason_and_applies_nothing(scenario):
    status, body = scenario["accept"]
    assert status == 200
    assert body["status"] == "approved"
    assert body["reviewed_by"] == "owner-1"
    assert body["reviewed_at"]
    assert body["reason"] == "evidence reviewed"
    assert body["applied"] is False
    assert body["idempotent_replay"] is False
    row = scenario["accept_row"]
    assert row["status"] == "approved"
    assert row["reviewed_by"] == "owner-1"
    assert row["has_time"] is True
    assert row["auto_promote"] is False
    assert json.loads(row["evidence"]) == {"pool_digest": _POOL, "n": 4}
    [(payload, actor)] = scenario["accept_events"]
    assert actor == "owner-1"
    assert payload["decision"] == "accept"
    assert payload["reason"] == "evidence reviewed"
    assert payload["reviewed_by"] == "owner-1"
    assert payload["applied"] is False


def test_the_same_decision_replays_and_the_opposite_is_refused(scenario):
    status, body = scenario["replay"]
    assert status == 200
    assert body["idempotent_replay"] is True
    assert body["status"] == "approved"
    assert body["reviewed_at"] == scenario["accept"][1]["reviewed_at"]
    assert scenario["opposite"] == 409
    assert len(scenario["accept_events"]) == 1


def test_rejecting_an_irrigation_proposal_leaves_its_parameters_alone(scenario):
    status, body = scenario["reject"]
    assert status == 200
    assert body["status"] == "rejected"
    assert body["applied"] is False
    row = scenario["reject_row"]
    assert row["status"] == "rejected"
    assert row["reviewed_by"] == "owner-1"
    assert row["auto_adjust"] is False
    assert json.loads(row["proposed_parameter_changes"]) == [
        {"parameter": "p", "proposed_delta": 1}
    ]
    assert scenario["reject_events"] == 1
    assert set(scenario["after_ids"]) == set(scenario["expected_ids"]) - {
        scenario["accept"][1]["proposal_id"],
        body["proposal_id"],
    }
