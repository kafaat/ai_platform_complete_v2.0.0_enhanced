"""WX-10.6 — Crop→Decision candidate bridge: builder + fail-closed submit (unit, no network).

Ownership: Crop Intelligence interprets; decision-service owns the decision + approval.
The bridge only builds/submits a reviewable ``pending_approval`` candidate. gdd_product is
the sole authoritative source of accumulated GDD + GDD lineage.
"""

from __future__ import annotations

import api.crop_decision_bridge as bridge
import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit


def _ci(**over):
    ci = {
        "schema": "crop_intelligence_state.v2",
        "engine_version": "crop-intelligence/5.0.0",
        "field_id": "f1",
        "season_id": "s1",
        "confidence": "medium",
        "calibrated": False,
        "evidence_ids": ["e1"],
        "phenology": {"stage": "flowering", "gdd_cumulative": 500.0},
        "stress_flags": [{"code": "water_deficit", "source": "water"}],
        "stress_memory": {"product_version": "crop-stress-memory/2.0.0"},
        "limitations": [],
        "recommendation_context": {
            "schema": "crop_recommendation_context.v1",
            "stage": "flowering",
            "active_stress_codes": ["water_deficit"],
            "urgency": "high",
            "urgent_factors": [],
            "evidence_ids": ["e2"],
            "decision_boundary": {
                "is_decision": False,
                "consumer": "decision-service",
                "approval_required": True,
            },
        },
    }
    ci.update(over)
    return ci


def _gdd(**over):
    g = {
        "accumulated_gdd": 26.0,
        "gdd_lineage_id": "gddseq/abc123",
        "contributing_state_ids": ["snap-1", "snap-2"],
        "limitations": [],
        "calculation_version": "gdd/daily/1.0.0",
        "series_quality_status": "validated",
    }
    g.update(over)
    return g


def _authoritative(payload, tenant_id=None):
    # decision-service SoR-on response for /v1/decisions/record (echoes stage).
    async def _run():
        return {
            "accepted": True,
            "authoritative": True,
            "persisted": True,
            "decision_id": "dec_abc123",
            "stage": payload.get("stage"),
        }

    return _run()


# ── builder: contract + lineage ────────────────────────────────────────────────
def test_candidate_pending_approval_and_lineage_carried():
    out = bridge.build_crop_decision_candidate(_ci(), gdd_product=_gdd())
    assert out["decision_type"] == "crop_decision_candidate"
    assert out["status"] == "pending_approval"
    assert out["approval_required"] is True
    # evidence ids lossless + ordered: CI ⊕ context ⊕ contributing ⊕ lineage.
    assert out["evidence_ids"] == ["e1", "e2", "snap-1", "snap-2", "gddseq/abc123"]
    # GDD anchors sourced only from gdd_product.
    assert out["evidence"]["accumulated_gdd"] == 26.0
    assert out["evidence"]["gdd_lineage_id"] == "gddseq/abc123"
    assert out["evidence"]["contributing_state_ids"] == ["snap-1", "snap-2"]
    assert out["candidate_lineage_id"].startswith("cand/")
    assert out["ownership"] == {
        "interpretation": "crop-intelligence-engine",
        "decision": "decision-service",
    }


def test_lineage_stable_for_identical_inputs():
    a = bridge.build_crop_decision_candidate(_ci(), gdd_product=_gdd())
    b = bridge.build_crop_decision_candidate(_ci(), gdd_product=_gdd())
    assert a["candidate_lineage_id"] == b["candidate_lineage_id"]


def test_lineage_changes_when_gdd_changes():
    base = bridge.build_crop_decision_candidate(_ci(), gdd_product=_gdd())["candidate_lineage_id"]
    acc = bridge.build_crop_decision_candidate(_ci(), gdd_product=_gdd(accumulated_gdd=27.0))[
        "candidate_lineage_id"
    ]
    lin = bridge.build_crop_decision_candidate(_ci(), gdd_product=_gdd(gdd_lineage_id="gddseq/z"))[
        "candidate_lineage_id"
    ]
    ids = bridge.build_crop_decision_candidate(
        _ci(), gdd_product=_gdd(contributing_state_ids=["snap-9"])
    )["candidate_lineage_id"]
    assert base != acc and base != lin and base != ids


def test_contributing_id_order_changes_lineage():
    a = bridge.build_crop_decision_candidate(
        _ci(), gdd_product=_gdd(contributing_state_ids=["snap-1", "snap-2"])
    )["candidate_lineage_id"]
    b = bridge.build_crop_decision_candidate(
        _ci(), gdd_product=_gdd(contributing_state_ids=["snap-2", "snap-1"])
    )["candidate_lineage_id"]
    assert a != b


def test_degraded_gdd_series_quality_preserved():
    out = bridge.build_crop_decision_candidate(
        _ci(), gdd_product=_gdd(series_quality_status="degraded", limitations=["missing_days"])
    )
    assert out["evidence"]["gdd_series_quality_status"] == "degraded"
    assert "missing_days" in out["limitations"]


# ── builder: fail-closed ───────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        {"gdd_lineage_id": "x", "contributing_state_ids": ["s"]},  # missing accumulated_gdd
        {"accumulated_gdd": 1.0, "contributing_state_ids": ["s"]},  # missing lineage
        {"accumulated_gdd": 1.0, "gdd_lineage_id": "x"},  # missing contributing
        {"accumulated_gdd": 1.0, "gdd_lineage_id": "x", "contributing_state_ids": []},  # empty
    ],
)
def test_missing_gdd_product_fails_closed(bad):
    with pytest.raises(ValueError):
        bridge.build_crop_decision_candidate(_ci(), gdd_product=bad)


def test_boundary_is_decision_fails_closed():
    ci = _ci()
    ci["recommendation_context"]["decision_boundary"]["is_decision"] = True
    with pytest.raises(ValueError):
        bridge.build_crop_decision_candidate(ci, gdd_product=_gdd())


def test_non_decision_service_consumer_fails_closed():
    ci = _ci()
    ci["recommendation_context"]["decision_boundary"]["consumer"] = "elsewhere"
    with pytest.raises(ValueError):
        bridge.build_crop_decision_candidate(ci, gdd_product=_gdd())


def test_approval_not_required_fails_closed():
    ci = _ci()
    ci["recommendation_context"]["decision_boundary"]["approval_required"] = False
    with pytest.raises(ValueError):
        bridge.build_crop_decision_candidate(ci, gdd_product=_gdd())


# ── submit: preview vs submit, fail-closed proof ───────────────────────────────
@pytest.mark.asyncio
async def test_preview_writes_nothing(monkeypatch):
    called = False

    async def fake_record(payload, tenant_id=None):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(bridge, "record_decision", fake_record)
    out = await bridge.submit_crop_decision_candidate(
        _ci(), gdd_product=_gdd(), tenant_id="t1", submit=False
    )
    assert out["approval_state"] == "preview"
    assert out["submitted"] is False and out["persisted"] is False
    assert out["candidate_id"] is None
    assert called is False


@pytest.mark.asyncio
async def test_submit_pending_approval_on_authoritative_persist(monkeypatch):
    monkeypatch.setattr(bridge, "record_decision", _authoritative)
    out = await bridge.submit_crop_decision_candidate(
        _ci(), gdd_product=_gdd(), tenant_id="t1", submit=True, created_by="u1"
    )
    assert out["approval_state"] == "pending_approval"
    assert out["submitted"] is True and out["persisted"] is True
    assert out["authoritative"] is True
    assert out["candidate_id"] == "dec_abc123"


@pytest.mark.asyncio
async def test_preview_and_submit_share_identical_lineage(monkeypatch):
    monkeypatch.setattr(bridge, "record_decision", _authoritative)
    pv = await bridge.submit_crop_decision_candidate(
        _ci(), gdd_product=_gdd(), tenant_id="t1", submit=False
    )
    sub = await bridge.submit_crop_decision_candidate(
        _ci(), gdd_product=_gdd(), tenant_id="t1", submit=True
    )
    assert pv["candidate_lineage_id"] == sub["candidate_lineage_id"]
    # submit must not rebuild/mutate the evidence.
    assert pv["candidate"]["evidence"] == sub["candidate"]["evidence"]
    assert pv["candidate"]["evidence_ids"] == sub["candidate"]["evidence_ids"]


@pytest.mark.asyncio
async def test_mirror_ack_non_authoritative_fails_closed(monkeypatch):
    async def fake_record(payload, tenant_id=None):
        # SoR off ⇒ mirror-ack: persisted:false ⇒ no fake success.
        return {"accepted": True, "authoritative": False, "persisted": False, "stage": "candidate"}

    monkeypatch.setattr(bridge, "record_decision", fake_record)
    with pytest.raises(HTTPException) as ei:
        await bridge.submit_crop_decision_candidate(
            _ci(), gdd_product=_gdd(), tenant_id="t1", submit=True
        )
    assert ei.value.status_code == 502


@pytest.mark.asyncio
async def test_empty_decision_id_fails_closed(monkeypatch):
    async def fake_record(payload, tenant_id=None):
        return {"authoritative": True, "persisted": True, "decision_id": "", "stage": "candidate"}

    monkeypatch.setattr(bridge, "record_decision", fake_record)
    with pytest.raises(HTTPException) as ei:
        await bridge.submit_crop_decision_candidate(
            _ci(), gdd_product=_gdd(), tenant_id="t1", submit=True
        )
    assert ei.value.status_code == 502


@pytest.mark.asyncio
async def test_wrong_stage_echo_fails_closed(monkeypatch):
    # authoritative+persisted but the response points to a DIFFERENT record (stage mismatch).
    async def fake_record(payload, tenant_id=None):
        return {"authoritative": True, "persisted": True, "decision_id": "d1", "stage": "decision"}

    monkeypatch.setattr(bridge, "record_decision", fake_record)
    with pytest.raises(HTTPException) as ei:
        await bridge.submit_crop_decision_candidate(
            _ci(), gdd_product=_gdd(), tenant_id="t1", submit=True
        )
    assert ei.value.status_code == 502


@pytest.mark.asyncio
async def test_decision_service_down_fails_closed(monkeypatch):
    async def fake_record(payload, tenant_id=None):
        raise HTTPException(status_code=503, detail="down")

    monkeypatch.setattr(bridge, "record_decision", fake_record)
    with pytest.raises(HTTPException) as ei:
        await bridge.submit_crop_decision_candidate(
            _ci(), gdd_product=_gdd(), tenant_id="t1", submit=True
        )
    assert ei.value.status_code == 503
