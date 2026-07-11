"""WX-10.6 — POST /api/v1/crop-twin/decision-candidate (routers/crop_twin) — direct call.

Crop Intelligence → Decision Candidate boundary. Verifies: `_compose_state` exposes the
canonical gdd_product internally (single GDD computation, no re-derivation); the candidate
lineage is anchored on that gdd_product; preview writes nothing; submit yields
pending_approval only on authoritative persistence; decision-service failure fails closed;
evidence is lossless; lineage is stable and GDD-sensitive; no path bypasses approval; and
the existing compose response contract is unchanged (gdd_product stays internal-only).
"""

from __future__ import annotations

import api.crop_decision_bridge as bridge
import api.main  # noqa: F401 — initialise api.main before importing the router (import cycle)
import api.routers.crop_twin as mod
import pytest
from api.routers.crop_twin import (
    ComposeForecastDay,
    ComposeSoil,
    CropDecisionCandidateRequest,
    CropTwinComposeRequest,
    _compose_state,
    compose_crop_twin,
    crop_decision_candidate_endpoint,
)
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-cand",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مرشّح",
)


def _fake_gdd_factory(counter=None, **overrides):
    async def _fake_gdd(*, daily_t_min, daily_t_max, base_c, upper_cutoff_c, method, **_kw):
        if counter is not None:
            counter.append(1)
        daily = []
        for mn, mx in zip(daily_t_min, daily_t_max, strict=False):
            tmax = max(min(mx, upper_cutoff_c) if upper_cutoff_c is not None else mx, base_c)
            tmin = max(mn, base_c)
            daily.append(round(max(0.0, (tmax + tmin) / 2.0 - base_c), 3))
        product = {
            "product": "gdd",
            "calculation_version": "gdd/daily/1.0.0",
            "daily_gdd": daily,
            "accumulated_gdd": round(sum(daily), 3),
            "thresholds_used": {
                "base_c": base_c,
                "upper_cutoff_c": upper_cutoff_c,
                "method": method,
            },
            "valid_period": {"days": len(daily)},
            "limitations": [],
            "derived_from": "canonical_daily_weather_series",
            "gdd_lineage_id": "gddseq/fake-compose",
            "contributing_state_ids": [f"snap-{i}" for i in range(len(daily))],
            "series_quality_status": "validated",
        }
        product.update(overrides)
        return product

    return _fake_gdd


def _patch_gdd(monkeypatch, counter=None, **overrides):
    monkeypatch.setattr(mod, "get_gdd_product", _fake_gdd_factory(counter, **overrides))


def _req(submit=False, **over):
    base = dict(
        field_id="f-1",
        season_id="s-1",
        crop="wheat",
        stage="mid",
        forecast=[
            ComposeForecastDay(t_min_c=12.0, t_max_c=26.0, et0_mm=5.0),
            ComposeForecastDay(t_min_c=14.0, t_max_c=28.0, et0_mm=5.0),
        ],
        ndvi=0.6,
        spectral_product_ids=["spec-1"],
        soil=ComposeSoil(texture="loam"),
    )
    base.update(over)
    return CropDecisionCandidateRequest(submit=submit, **base)


def _authoritative_record(monkeypatch):
    async def fake_record(payload, tenant_id=None):
        return {
            "accepted": True,
            "authoritative": True,
            "persisted": True,
            "decision_id": "dec_endpoint",
            "stage": payload.get("stage"),
        }

    monkeypatch.setattr(bridge, "record_decision", fake_record)


# ── _compose_state: gdd_product is internal, computed once ─────────────────────
@pytest.mark.asyncio
async def test_compose_state_returns_canonical_gdd_product_once(monkeypatch):
    counter: list[int] = []
    _patch_gdd(monkeypatch, counter=counter)
    st = await _compose_state(_req())
    assert isinstance(st.get("gdd_product"), dict)
    assert st["gdd_product"]["gdd_lineage_id"] == "gddseq/fake-compose"
    # single GDD computation — no second derivation.
    assert sum(counter) == 1
    # the crop_intelligence evidence lineage carries the SAME gdd lineage anchors.
    ci = st["twin"]["crop_intelligence"]
    assert "gddseq/fake-compose" in ci["evidence_ids"]


@pytest.mark.asyncio
async def test_compose_response_contract_has_no_gdd_product_key(monkeypatch):
    # gdd_product is internal-only: the public compose response must not expose it.
    _patch_gdd(monkeypatch)
    body = await compose_crop_twin(
        req=CropTwinComposeRequest(**_req().model_dump(exclude={"submit"})), user=_USER
    )
    assert "gdd_product" not in body


# ── endpoint: preview vs submit ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_preview_writes_nothing(monkeypatch):
    _patch_gdd(monkeypatch)
    called = []

    async def fake_record(payload, tenant_id=None):
        called.append(1)
        return {}

    monkeypatch.setattr(bridge, "record_decision", fake_record)
    out = await crop_decision_candidate_endpoint(req=_req(submit=False), user=_USER)
    assert out["approval_state"] == "preview"
    assert out["submitted"] is False
    assert out["candidate"]["status"] == "pending_approval"
    assert out["candidate"]["approval_required"] is True
    assert not called  # no network write on preview


@pytest.mark.asyncio
async def test_submit_creates_pending_approval_only(monkeypatch):
    _patch_gdd(monkeypatch)
    _authoritative_record(monkeypatch)
    out = await crop_decision_candidate_endpoint(req=_req(submit=True), user=_USER)
    assert out["approval_state"] == "pending_approval"
    assert out["submitted"] is True and out["authoritative"] is True
    assert out["candidate_id"] == "dec_endpoint"
    assert out["candidate"]["approval_required"] is True


@pytest.mark.asyncio
async def test_decision_service_failure_no_fake_success(monkeypatch):
    from fastapi import HTTPException

    _patch_gdd(monkeypatch)

    async def down(payload, tenant_id=None):
        raise HTTPException(status_code=503, detail="down")

    monkeypatch.setattr(bridge, "record_decision", down)
    with pytest.raises(HTTPException) as ei:
        await crop_decision_candidate_endpoint(req=_req(submit=True), user=_USER)
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_evidence_ids_lossless_through_endpoint(monkeypatch):
    _patch_gdd(monkeypatch)
    out = await crop_decision_candidate_endpoint(req=_req(submit=False), user=_USER)
    eids = out["candidate"]["evidence_ids"]
    # spectral evidence + GDD lineage anchors all survive.
    assert "spec-1" in eids
    assert "gddseq/fake-compose" in eids
    assert "snap-0" in eids and "snap-1" in eids


@pytest.mark.asyncio
async def test_preview_and_submit_lineage_identical(monkeypatch):
    _patch_gdd(monkeypatch)
    _authoritative_record(monkeypatch)
    pv = await crop_decision_candidate_endpoint(req=_req(submit=False), user=_USER)
    sub = await crop_decision_candidate_endpoint(req=_req(submit=True), user=_USER)
    assert pv["candidate_lineage_id"] == sub["candidate_lineage_id"]
    assert pv["candidate"]["evidence"] == sub["candidate"]["evidence"]


@pytest.mark.asyncio
async def test_changing_gdd_snapshot_changes_candidate_lineage(monkeypatch):
    _patch_gdd(monkeypatch)
    base = await crop_decision_candidate_endpoint(req=_req(submit=False), user=_USER)
    # a different GDD lineage (new snapshot) ⇒ different candidate lineage.
    _patch_gdd(monkeypatch, gdd_lineage_id="gddseq/other-snapshot")
    other = await crop_decision_candidate_endpoint(req=_req(submit=False), user=_USER)
    assert base["candidate_lineage_id"] != other["candidate_lineage_id"]


@pytest.mark.asyncio
async def test_missing_gdd_lineage_fails_closed(monkeypatch):
    from fastapi import HTTPException

    # canonical product without a lineage id ⇒ builder refuses ⇒ endpoint 422 (no candidate).
    _patch_gdd(monkeypatch, gdd_lineage_id=None)
    with pytest.raises(HTTPException) as ei:
        await crop_decision_candidate_endpoint(req=_req(submit=True), user=_USER)
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_degraded_gdd_quality_preserved(monkeypatch):
    _patch_gdd(monkeypatch, series_quality_status="degraded", limitations=["missing_days_present"])
    out = await crop_decision_candidate_endpoint(req=_req(submit=False), user=_USER)
    assert out["candidate"]["evidence"]["gdd_series_quality_status"] == "degraded"
    assert "missing_days_present" in out["candidate"]["limitations"]
