"""v26 workstream 03: wizard crop aliases resolve; an unsupported crop has no estimate (None)."""

import pytest
from api.yield_heuristics import (
    LifecycleFeatures,
    detect_anomalies,
    estimate_yield,
    yield_crop_key,
)


@pytest.mark.unit
@pytest.mark.parametrize("crop", ["قمح", "Wheat", " wheat ", "wheat"])
def test_wheat_aliases_do_not_return_false_zero(crop):
    result = estimate_yield(LifecycleFeatures(field_id="f", crop=crop))
    assert result.estimated_yield_kg_ha == 2800
    assert result.crop == "wheat"
    assert result.yield_status == "estimated"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "key"), [("corn", "corn"), ("maize", "corn"), ("ذرة رفيعة", "sorghum")]
)
def test_shared_identity_maps_onto_the_table_keys(raw, key):
    assert yield_crop_key(raw) == key


@pytest.mark.unit
@pytest.mark.parametrize("crop", ["unknown-crop", "", "تنين"])
def test_unsupported_crop_has_null_estimate(crop):
    result = estimate_yield(LifecycleFeatures(field_id="f", crop=crop))
    assert result.estimated_yield_kg_ha is None
    assert result.confidence == 0
    assert result.yield_status == "unavailable_unrecognized_crop"
    assert "unsupported_crop_no_yield_estimate" in result.warnings


@pytest.mark.unit
def test_arabic_wheat_gets_the_same_duration_anomaly_as_english():
    # Before the alias reached detect_anomalies, «قمح» silently skipped the duration check.
    def kinds(crop):
        return [
            a.type
            for a in detect_anomalies(
                LifecycleFeatures(field_id="f", crop=crop, days_in_growing=200)
            )
        ]

    assert kinds("قمح") == kinds("wheat") != []
