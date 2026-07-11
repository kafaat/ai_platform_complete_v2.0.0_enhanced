import api.crop_decision_bridge as bridge
import pytest
from fastapi import HTTPException


def _crop_state():
    return {
        "schema": "crop_intelligence_state.v2",
        "engine_version": "crop-intelligence/5.0.0",
        "field_id": "f1",
        "season_id": "s1",
        "confidence": "medium",
        "calibrated": False,
        "evidence_ids": ["e1"],
        "phenology": {"stage": "flowering"},
        "stress_memory": {"product_version": "crop-stress-memory/2.0.0"},
        "recommendation_context": {
            "is_decision": False,
            "urgency": "high",
            "crop_health": "stressed",
            "water_need": {"status": "available"},
            "stress_summary": ["water_deficit"],
            "evidence_ids": ["e2"],
        },
    }


def test_candidate_is_pending_approval_and_preserves_lineage():
    out = bridge.build_crop_decision_candidate(_crop_state())
    assert out["decision_type"] == "crop_management"
    assert out["status"] == "pending_approval"
    assert out["approval_required"] is True
    assert out["evidence_ids"] == ["e1", "e2"]


@pytest.mark.asyncio
async def test_submission_is_explicit_only(monkeypatch):
    called = False

    async def fake_record(payload, tenant_id=None):
        nonlocal called
        called = True
        return {"decision_id": "d1"}

    monkeypatch.setattr(bridge, "record_decision", fake_record)
    out = await bridge.submit_crop_decision_candidate(_crop_state(), tenant_id="t1", submit=False)
    assert out["approval_state"] == "not_submitted"
    assert called is False


@pytest.mark.asyncio
async def test_submission_records_pending_candidate(monkeypatch):
    async def fake_record(payload, tenant_id=None):
        return {"decision_id": "d1"}

    monkeypatch.setattr(bridge, "record_decision", fake_record)
    out = await bridge.submit_crop_decision_candidate(_crop_state(), tenant_id="t1", submit=True)
    assert out["approval_state"] == "pending_approval"
    assert out["decision_id"] == "d1"


@pytest.mark.asyncio
async def test_decision_service_failure_is_fail_closed(monkeypatch):
    async def fake_record(payload, tenant_id=None):
        raise HTTPException(status_code=503, detail="down")

    monkeypatch.setattr(bridge, "record_decision", fake_record)
    out = await bridge.submit_crop_decision_candidate(_crop_state(), tenant_id="t1", submit=True)
    assert out["approval_state"] == "submit_unavailable"
    assert out["decision_id"] is None
