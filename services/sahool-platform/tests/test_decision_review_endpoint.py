"""WX-10.7 — platform reviewer BFF (routers/decision_review) — direct call, mocked facade.

The platform route is a thin proxy: it forwards to decision-service and FAILS CLOSED unless the
service proves an authoritative transition. These tests mock the facade (no network/DB) and
verify: authoritative pass-through, mirror-ack/non-authoritative → 503, lineage-mismatch in the
response → 503, service-down → 503, 404/409 propagation, and that tenant + reviewed_by are
forwarded from the JWT user. Permission enforcement (403) is covered by the authorization matrix
test alongside.
"""

from __future__ import annotations

import api.main  # noqa: F401 — initialise api.main before importing the router (import cycle)
import api.routers.decision_review as mod
import pytest
from api.routers.decision_review import DecisionReviewRequest, review_decision_candidate
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="rev-1",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.MANAGER,
    name_ar="مراجع",
)


def _authoritative(**over):
    base = {
        "authoritative": True,
        "persisted": True,
        "decision_id": "dec_1",
        "previous_state": "pending_approval",
        "state": "approved",
        "review_id": "rev_abc",
        "reviewed_by": "rev-1",
        "reviewed_at": "2026-07-11T00:00:00+00:00",
        "candidate_lineage_id": "cand/lin-1",
        "replay": False,
    }
    base.update(over)
    return base


def _req(**over):
    base = dict(
        action="approve",
        reason="reviewed",
        expected_state="pending_approval",
        candidate_lineage_id="cand/lin-1",
        idempotency_key="k-1",
    )
    base.update(over)
    return DecisionReviewRequest(**base)


def _patch(monkeypatch, fake):
    monkeypatch.setattr(mod, "ds_review_decision", fake)


@pytest.mark.asyncio
async def test_authoritative_review_passes_through(monkeypatch):
    seen = {}

    async def fake(decision_id, payload, *, tenant_id=None, reviewed_by=None):
        seen.update(decision_id=decision_id, tenant_id=tenant_id, reviewed_by=reviewed_by)
        return _authoritative(decision_id=decision_id)

    _patch(monkeypatch, fake)
    out = await review_decision_candidate(decision_id="dec_1", req=_req(), user=_USER)
    assert out["state"] == "approved" and out["review_id"] == "rev_abc"
    # tenant + reviewed_by are taken from the JWT user, not the request body.
    assert seen["tenant_id"] == str(_USER.tenant_id) and seen["reviewed_by"] == "rev-1"


@pytest.mark.asyncio
async def test_mirror_ack_non_authoritative_fails_closed(monkeypatch):
    async def fake(decision_id, payload, *, tenant_id=None, reviewed_by=None):
        return {"accepted": True, "authoritative": False, "persisted": False}

    _patch(monkeypatch, fake)
    with pytest.raises(HTTPException) as ei:
        await review_decision_candidate(decision_id="dec_1", req=_req(), user=_USER)
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_lineage_mismatch_in_response_fails_closed(monkeypatch):
    async def fake(decision_id, payload, *, tenant_id=None, reviewed_by=None):
        return _authoritative(decision_id=decision_id, candidate_lineage_id="cand/OTHER")

    _patch(monkeypatch, fake)
    with pytest.raises(HTTPException) as ei:
        await review_decision_candidate(decision_id="dec_1", req=_req(), user=_USER)
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_wrong_decision_id_in_response_fails_closed(monkeypatch):
    async def fake(decision_id, payload, *, tenant_id=None, reviewed_by=None):
        return _authoritative(decision_id="dec_OTHER")

    _patch(monkeypatch, fake)
    with pytest.raises(HTTPException) as ei:
        await review_decision_candidate(decision_id="dec_1", req=_req(), user=_USER)
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_service_down_502_becomes_503(monkeypatch):
    async def fake(decision_id, payload, *, tenant_id=None, reviewed_by=None):
        raise HTTPException(status_code=502, detail="down")

    _patch(monkeypatch, fake)
    with pytest.raises(HTTPException) as ei:
        await review_decision_candidate(decision_id="dec_1", req=_req(), user=_USER)
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_conflict_409_propagates(monkeypatch):
    async def fake(decision_id, payload, *, tenant_id=None, reviewed_by=None):
        raise HTTPException(status_code=409, detail="not_pending_approval")

    _patch(monkeypatch, fake)
    with pytest.raises(HTTPException) as ei:
        await review_decision_candidate(decision_id="dec_1", req=_req(), user=_USER)
    assert ei.value.status_code == 409


@pytest.mark.asyncio
async def test_not_found_404_propagates(monkeypatch):
    async def fake(decision_id, payload, *, tenant_id=None, reviewed_by=None):
        raise HTTPException(status_code=404, detail="not found")

    _patch(monkeypatch, fake)
    with pytest.raises(HTTPException) as ei:
        await review_decision_candidate(decision_id="dec_1", req=_req(), user=_USER)
    assert ei.value.status_code == 404
