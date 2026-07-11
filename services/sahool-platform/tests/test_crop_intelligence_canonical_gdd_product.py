"""WX-10.5 — Crop Intelligence consumes the canonical Weather GDD product."""

import inspect

import pytest
from api.crop_twin import TwinDay, crop_twin_state

pytestmark = pytest.mark.unit


def _days(n: int = 2) -> list[TwinDay]:
    return [TwinDay(t_min_c=10, t_max_c=25, et0_mm=5, kc=1) for _ in range(n)]


def _product(**overrides):
    base = {
        "product": "gdd",
        "calculation_version": "gdd/daily/1.0.0",
        "daily_gdd": [12.5, 13.5],
        "accumulated_gdd": 26.0,
        "thresholds_used": {"base_c": 5.0, "upper_cutoff_c": 30.0, "method": "modified"},
        "limitations": [],
        "derived_from": "canonical_daily_weather_series",
        "gdd_lineage_id": "gddseq/test-lineage",
        "contributing_state_ids": ["snap-1", "snap-2"],
        "series_quality_status": "validated",
    }
    base.update(overrides)
    return base


def test_crop_intelligence_uses_authoritative_accumulated_gdd_not_local_sum():
    product = _product(daily_gdd=[999.0, 999.0], accumulated_gdd=26.0)
    out = crop_twin_state(
        "wheat",
        _days(),
        taw_mm=100,
        raw_fraction=0.5,
        gdd_daily_override=[1.0, 1.0],
        gdd_product=product,
    )
    assert out["phenology"]["gdd_cumulative"] == 26.0
    ci = out["crop_intelligence"]
    assert ci["phenology"]["method"] == "modified"
    assert ci["phenology"]["formula_version"] == "gdd/daily/1.0.0"


def test_gdd_lineage_flows_into_crop_intelligence_evidence():
    out = crop_twin_state(
        "wheat",
        _days(),
        taw_mm=100,
        raw_fraction=0.5,
        source_ids=["spectral-1"],
        gdd_product=_product(),
    )
    assert out["crop_intelligence"]["evidence_ids"] == [
        "spectral-1",
        "snap-1",
        "snap-2",
        "gddseq/test-lineage",
    ]


def test_degraded_gdd_series_is_not_elevated():
    out = crop_twin_state(
        "wheat",
        _days(),
        taw_mm=100,
        raw_fraction=0.5,
        gdd_product=_product(
            series_quality_status="degraded", limitations=["missing_days_present"]
        ),
    )
    limitations = out["crop_intelligence"]["limitations"]
    assert "missing_days_present" in limitations
    assert "canonical_gdd_series_degraded" in limitations


def test_missing_canonical_product_is_explicit_compatibility_limitation():
    out = crop_twin_state(
        "wheat",
        _days(),
        taw_mm=100,
        raw_fraction=0.5,
        gdd_daily_override=[1.0, 2.0],
    )
    ci = out["crop_intelligence"]
    assert ci["phenology"]["method"] == "weather_gdd_daily_override_compat"
    assert "canonical_gdd_product_missing" in ci["limitations"]


def test_no_pending_weather_delegation_markers_remain():
    src = inspect.getsource(crop_twin_state)
    assert "legacy_local_gdd_pending_weather_delegation" not in src
    assert "gdd_pending_weather_engine_delegation" not in src
