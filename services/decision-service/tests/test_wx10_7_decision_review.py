"""WX-10.7 — decision-service reviewer transition, against REAL Postgres.

These tests require a running Postgres with the decision-service migrations applied and
DECISION_SERVICE_SOR_ENABLED=true (the decision-service CI job provides both). They are skipped
when DATABASE_URL is absent so local `pytest` without a DB stays green.

Covers: approve/reject state machine, evidence immutability (hash before==after), fail-closed
(wrong tenant / stale expected_state / lineage mismatch / double review / empty reject reason),
idempotent replay vs payload-mismatch conflict, the CONCURRENCY RACE (two concurrent reviews →
exactly one success + one audit row + one terminal state + one outbox row + loser 409), and
DB-level append-only enforcement on decision_reviews.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres (DATABASE_URL)")
# NOTE: the CI job sets DECISION_SERVICE_SOR_ENABLED=true for this file's step (SoR on); the
# mirror-mode contract tests run in a SEPARATE step with SoR off. We do NOT mutate os.environ
# here (that would leak into the mirror step's process and break its persisted:false invariant).

TENANT = "00000000-0000-0000-0000-0000000010a7"
OTHER_TENANT = "00000000-0000-0000-0000-0000000020a7"


def _run(coro):
    return asyncio.run(coro)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _seed_candidate(decision_id: str, lineage: str, *, tenant: str = TENANT) -> None:
    conn = await _connect()
    try:
        await conn.execute("DELETE FROM decision_reviews WHERE decision_id=$1", decision_id)
        await conn.execute("DELETE FROM decision_record WHERE decision_id=$1", decision_id)
        await conn.execute(
            """
            INSERT INTO decision_record
              (decision_id, tenant_id, decision_type, stage, decision_value,
               review_state, candidate_lineage_id)
            VALUES ($1, $2::uuid, 'crop_decision_candidate', 'candidate', $3::jsonb,
                    'pending_approval', $4)
            """,
            decision_id,
            tenant,
            json.dumps(
                {
                    "status": "pending_approval",
                    "approval_required": True,
                    "candidate_lineage_id": lineage,
                    "evidence": {"field_id": "f1", "accumulated_gdd": 26.0},
                    "evidence_ids": ["snap-1", "snap-2", lineage],
                }
            ),
            lineage,
        )
    finally:
        await conn.close()


async def _fetch_record(decision_id: str):
    conn = await _connect()
    try:
        return await conn.fetchrow(
            "SELECT stage, review_state, decision_value FROM decision_record WHERE decision_id=$1",
            decision_id,
        )
    finally:
        await conn.close()


async def _counts(decision_id: str):
    conn = await _connect()
    try:
        reviews = await conn.fetchval(
            "SELECT count(*) FROM decision_reviews WHERE decision_id=$1", decision_id
        )
        outbox = await conn.fetchval(
            "SELECT count(*) FROM decision_outbox_events "
            "WHERE aggregate_id=$1 AND event_type='DECISION_REVIEWED'",
            decision_id,
        )
        return reviews, outbox
    finally:
        await conn.close()


def _review(decision_id, **over):
    from persistence import review_decision

    args = dict(
        tenant_id=TENANT,
        decision_id=decision_id,
        action="approve",
        new_state="approved",
        reason="ok",
        reviewed_by="u-rev",
        candidate_lineage_id="cand/lin-1",
        idempotency_key="idem-1",
        policy_version="rev/1.0.0",
    )
    args.update(over)
    return review_decision(**args)


# ── state machine ──────────────────────────────────────────────────────────────
def test_approve_pending_candidate_becomes_approved():
    _run(_seed_candidate("dec_ap1", "cand/lin-1"))
    res = _run(_review("dec_ap1"))
    assert res["status"] == "ok"
    assert res["authoritative"] is True and res["persisted"] is True
    assert res["previous_state"] == "pending_approval" and res["state"] == "approved"
    assert res["review_id"] and res["reviewed_by"] == "u-rev" and res["reviewed_at"]
    assert res["candidate_lineage_id"] == "cand/lin-1"
    assert _run(_fetch_record("dec_ap1"))["review_state"] == "approved"
    assert _run(_counts("dec_ap1")) == (1, 1)


def test_reject_pending_candidate_becomes_rejected():
    _run(_seed_candidate("dec_rj1", "cand/lin-1"))
    res = _run(_review("dec_rj1", action="reject", new_state="rejected", reason="insufficient"))
    assert res["status"] == "ok" and res["state"] == "rejected"
    assert _run(_fetch_record("dec_rj1"))["review_state"] == "rejected"


def test_evidence_is_immutable_across_review():
    _run(_seed_candidate("dec_im1", "cand/lin-1"))
    before = _run(_fetch_record("dec_im1"))["decision_value"]
    _run(_review("dec_im1"))
    after = _run(_fetch_record("dec_im1"))["decision_value"]
    # decision_value (the evidence) is byte-identical — only `review_state` changed.
    assert json.loads(before) == json.loads(after)
    # stage stays 'candidate' (kind); the lifecycle lives in review_state.
    assert _run(_fetch_record("dec_im1"))["stage"] == "candidate"


# ── fail-closed ──────────────────────────────────────────────────────────────
def test_wrong_tenant_is_not_found_no_oracle():
    _run(_seed_candidate("dec_wt1", "cand/lin-1", tenant=OTHER_TENANT))
    res = _run(_review("dec_wt1"))  # reviewer is TENANT, record is OTHER_TENANT
    assert res["status"] == "not_found"


def test_lineage_mismatch_conflicts():
    _run(_seed_candidate("dec_lm1", "cand/lin-1"))
    res = _run(_review("dec_lm1", candidate_lineage_id="cand/WRONG"))
    assert res["status"] == "conflict" and res["reason"] == "candidate_lineage_mismatch"


def test_double_review_conflicts_and_leaves_one_terminal():
    _run(_seed_candidate("dec_dr1", "cand/lin-1"))
    first = _run(_review("dec_dr1", idempotency_key="k-1"))
    assert first["status"] == "ok"
    second = _run(
        _review("dec_dr1", action="reject", new_state="rejected", reason="x", idempotency_key="k-2")
    )
    assert second["status"] == "conflict"  # not_pending_approval
    assert _run(_fetch_record("dec_dr1"))["review_state"] == "approved"
    assert _run(_counts("dec_dr1")) == (1, 1)


def test_not_found_candidate():
    res = _run(_review("dec_missing_xyz"))
    assert res["status"] == "not_found"


# ── idempotency ──────────────────────────────────────────────────────────────
def test_idempotent_replay_same_key_same_payload():
    _run(_seed_candidate("dec_id1", "cand/lin-1"))
    first = _run(_review("dec_id1", idempotency_key="idem-r"))
    replay = _run(_review("dec_id1", idempotency_key="idem-r"))
    assert replay["status"] == "ok" and replay["replay"] is True
    assert replay["review_id"] == first["review_id"]
    assert _run(_counts("dec_id1")) == (1, 1)  # no second audit / outbox row


def test_idempotency_key_payload_mismatch_conflicts():
    _run(_seed_candidate("dec_id2", "cand/lin-1"))
    _run(_review("dec_id2", idempotency_key="idem-m", reason="first"))
    res = _run(_review("dec_id2", idempotency_key="idem-m", reason="different"))
    assert res["status"] == "conflict" and res["reason"] == "idempotency_key_payload_mismatch"


# ── the concurrency race ─────────────────────────────────────────────────────
def test_two_concurrent_reviews_exactly_one_wins():
    _run(_seed_candidate("dec_cc1", "cand/lin-1"))

    async def _race():
        from persistence import review_decision

        common = dict(
            tenant_id=TENANT,
            decision_id="dec_cc1",
            candidate_lineage_id="cand/lin-1",
            reviewed_by="u-rev",
            policy_version="rev/1.0.0",
        )
        return await asyncio.gather(
            review_decision(
                action="approve",
                new_state="approved",
                reason="a",
                idempotency_key="race-A",
                **common,
            ),
            review_decision(
                action="reject",
                new_state="rejected",
                reason="b",
                idempotency_key="race-B",
                **common,
            ),
        )

    results = _run(_race())
    oks = [r for r in results if r["status"] == "ok"]
    conflicts = [r for r in results if r["status"] == "conflict"]
    assert len(oks) == 1, results
    assert len(conflicts) == 1, results
    reviews, outbox = _run(_counts("dec_cc1"))
    assert reviews == 1 and outbox == 1  # exactly one audit + one outbox row
    assert _run(_fetch_record("dec_cc1"))["review_state"] in ("approved", "rejected")


# ── DB-level append-only ─────────────────────────────────────────────────────
def test_decision_reviews_is_append_only():
    import asyncpg

    _run(_seed_candidate("dec_ao1", "cand/lin-1"))
    _run(_review("dec_ao1", idempotency_key="ao"))

    async def _mutate(sql):
        conn = await _connect()
        try:
            await conn.execute(sql, "dec_ao1")
        finally:
            await conn.close()

    for sql in (
        "UPDATE decision_reviews SET reason='tampered' WHERE decision_id=$1",
        "DELETE FROM decision_reviews WHERE decision_id=$1",
    ):
        with pytest.raises(asyncpg.PostgresError):
            _run(_mutate(sql))


# ── HTTP endpoint (TestClient, SoR on) ───────────────────────────────────────
def _client():
    import main
    from fastapi.testclient import TestClient

    return TestClient(main.app)


_HDR = {"X-Tenant-Id": TENANT, "X-Reviewed-By": "u-rev"}


def _body(**over):
    b = {
        "action": "approve",
        "reason": "ok",
        "expected_state": "pending_approval",
        "candidate_lineage_id": "cand/lin-1",
        "idempotency_key": "http-1",
    }
    b.update(over)
    return b


def test_endpoint_bad_action_is_422():
    r = _client().post("/v1/decisions/dec_x/review", json=_body(action="delete"), headers=_HDR)
    assert r.status_code == 422


def test_endpoint_reject_empty_reason_is_422():
    r = _client().post(
        "/v1/decisions/dec_x/review", json=_body(action="reject", reason="  "), headers=_HDR
    )
    assert r.status_code == 422


def test_endpoint_missing_reviewer_is_400():
    r = _client().post("/v1/decisions/dec_x/review", json=_body(), headers={"X-Tenant-Id": TENANT})
    assert r.status_code == 400


def test_endpoint_missing_tenant_is_401():
    r = _client().post("/v1/decisions/dec_x/review", json=_body(), headers={"X-Reviewed-By": "u"})
    assert r.status_code == 401


def test_endpoint_stale_expected_state_is_409():
    r = _client().post(
        "/v1/decisions/dec_x/review", json=_body(expected_state="approved"), headers=_HDR
    )
    assert r.status_code == 409


def test_endpoint_approve_is_authoritative_200():
    _run(_seed_candidate("dec_http_ok", "cand/lin-1"))
    r = _client().post(
        "/v1/decisions/dec_http_ok/review",
        json=_body(idempotency_key="http-ok"),
        headers=_HDR,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authoritative"] is True and body["persisted"] is True
    assert body["state"] == "approved" and body["previous_state"] == "pending_approval"
    assert body["review_id"] and body["reviewed_by"] == "u-rev"


def test_endpoint_not_found_is_404():
    r = _client().post(
        "/v1/decisions/dec_http_missing/review", json=_body(idempotency_key="http-nf"), headers=_HDR
    )
    assert r.status_code == 404


def test_endpoint_mirror_mode_fails_closed_503(monkeypatch):
    # Under the interim-bridge/mirror deployment (SoR off) the review transition cannot be made,
    # so the endpoint fails closed (503) and NEVER returns a mirror ack.
    import main

    monkeypatch.setattr(main, "sor_enabled", lambda: False)
    r = _client().post("/v1/decisions/dec_x/review", json=_body(), headers=_HDR)
    assert r.status_code == 503
    assert "persisted" not in r.json() or r.json().get("persisted") is not False
