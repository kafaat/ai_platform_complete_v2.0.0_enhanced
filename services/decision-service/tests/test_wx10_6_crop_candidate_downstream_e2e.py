"""WX-10.6 — Crop Intelligence → Decision Candidate boundary: DOWNSTREAM consumption E2E.

Proves the boundary OUTPUT — a ``crop_decision_candidate`` produced by the WX-10.6 bridge and
recorded via ``POST /v1/decisions/record`` (the bridge's real HTTP target) — is CONSUMED by the
downstream reviewer surface the Approvals Console uses (``GET /v1/decisions/review-queue``) and
is reviewable, WITHOUT being auto-approved or dispatched. This is the real coverage that
replaces the old "machine-consumed … pending reviewer UI" waiver: the reviewer UI now exists
(WX-10.8 Approvals Console) and consumes exactly this candidate.

Real Postgres + SoR on (the decision-service CI job provides both). Skipped when DATABASE_URL is
absent so local ``pytest`` without a DB stays green. The platform producer's ``submit=true`` path
remains behind the test-only flag ``CROP_TWIN_DIRECT_DECISION_ENABLED`` (default-false → 403 in
production) — unchanged; this E2E exercises the decision-service consumer seam the producer feeds.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres (DATABASE_URL)")

TENANT = "00000000-0000-0000-0000-0000000106a6"
OTHER_TENANT = "00000000-0000-0000-0000-0000000206a6"
LINEAGE = "cand/wx106e2e0001"


def _client():
    import main
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def _candidate_payload(decision_id: str) -> dict:
    """Exactly the shape the WX-10.6 bridge emits: a reviewable candidate, never a final decision.

    ``persist_decision_record`` derives review_state='pending_approval' from stage=='candidate'
    and reads candidate_lineage_id from decision_value — matching crop_decision_bridge.
    """
    return {
        "decision_id": decision_id,
        "field_id": "f-wx106",
        "decision_type": "crop_decision_candidate",
        "stage": "candidate",
        "decision_value": {
            "status": "pending_approval",
            "approval_required": True,
            "candidate_lineage_id": LINEAGE,
            "evidence": {"field_id": "f-wx106", "accumulated_gdd": 42.0},
            "evidence_ids": ["snap-a", "snap-b", LINEAGE],
        },
    }


def _record(client, decision_id: str, tenant: str = TENANT):
    return client.post(
        "/v1/decisions/record",
        json=_candidate_payload(decision_id),
        headers={"X-Tenant-Id": tenant},
    )


def _queue(client, tenant: str = TENANT) -> dict:
    r = client.get("/v1/decisions/review-queue", headers={"X-Tenant-Id": tenant})
    assert r.status_code == 200, r.text
    return r.json()


# ── producer output is recorded authoritatively as a pending candidate ──────────────
def test_candidate_recorded_authoritative_pending():
    r = _record(_client(), "dec_wx106_rec")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["authoritative"] is True and b["persisted"] is True
    assert b["stage"] == "candidate" and b["decision_id"] == "dec_wx106_rec"


# ── downstream consumption: the candidate surfaces in the reviewer queue ─────────────
def test_candidate_surfaces_in_downstream_review_queue():
    c = _client()
    _record(c, "dec_wx106_q")
    body = _queue(c)
    assert body["authoritative"] is True
    mine = [it for it in body["items"] if it["decision_id"] == "dec_wx106_q"]
    assert len(mine) == 1, body
    item = mine[0]
    assert item["decision_type"] == "crop_decision_candidate"
    assert item["stage"] == "candidate"
    assert item["review_state"] == "pending_approval"  # not auto-approved/dispatched


# ── the reviewer path consumes and acts on the boundary output ──────────────────────
def test_candidate_is_reviewable_and_leaves_queue():
    c = _client()
    _record(c, "dec_wx106_rev")
    r = c.post(
        "/v1/decisions/dec_wx106_rev/review",
        json={
            "action": "approve",
            "reason": "ok",
            "expected_state": "pending_approval",
            "candidate_lineage_id": LINEAGE,
            "idempotency_key": "wx106-approve",
            "policy_version": "rev/1.0.0",
        },
        headers={"X-Tenant-Id": TENANT, "X-Reviewed-By": "u-rev"},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["state"] == "approved" and b["previous_state"] == "pending_approval"
    # once approved, it is no longer a pending candidate in the reviewer queue.
    remaining = [it for it in _queue(c)["items"] if it["decision_id"] == "dec_wx106_rev"]
    assert remaining == []


# ── fail-closed: the candidate is tenant-isolated in the downstream surface ──────────
def test_candidate_not_visible_to_other_tenant_queue():
    c = _client()
    _record(c, "dec_wx106_iso")
    other = [
        it for it in _queue(c, tenant=OTHER_TENANT)["items"] if it["decision_id"] == "dec_wx106_iso"
    ]
    assert other == []
