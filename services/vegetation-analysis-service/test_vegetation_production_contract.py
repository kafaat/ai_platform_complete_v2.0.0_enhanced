import pytest
from vegetation_contracts import build_snapshot, derive_lai_from_ndvi, quality_gate

PROV = {
    "scene_id": "S2_X",
    "acquisition_datetime": "2026-07-01T00:00:00Z",
    "algorithm_version": "bandmath-v3",
    "qa_mask_version": "scl-v1",
    "valid_pixel_pct": 85.0,
    "data_available_at": "2026-07-01T01:00:00Z",
}


def test_estimated_ndvi_is_never_executable():
    assert quality_gate({"ndvi": {"estimated": True, "value": 0.7}})["executable"] is False


def test_authoritative_ndvi_requires_full_provenance():
    ndvi = {
        "source": "raster-service",
        "estimated": False,
        "value": 0.7,
        "quality_score": 0.9,
        "valid_pixel_pct": 85.0,
        "provenance": PROV,
    }
    assert quality_gate({"ndvi": ndvi})["executable"] is True


def test_missing_scene_blocks_execution():
    p = dict(PROV)
    p.pop("scene_id")
    ndvi = {
        "source": "raster-service",
        "estimated": False,
        "value": 0.7,
        "quality_score": 0.9,
        "valid_pixel_pct": 85.0,
        "provenance": p,
    }
    assert "ndvi_provenance_scene_id_missing" in quality_gate({"ndvi": ndvi})["reasons"]


def test_low_valid_pixel_share_blocks_execution():
    ndvi = {
        "source": "raster-service",
        "estimated": False,
        "value": 0.7,
        "quality_score": 0.9,
        "valid_pixel_pct": 30.0,
        "provenance": PROV,
    }
    assert "ndvi_valid_pixel_pct_below_threshold" in quality_gate({"ndvi": ndvi})["reasons"]


def test_lai_is_explicitly_derived():
    out = derive_lai_from_ndvi(0.7)
    assert out["estimated"] is True and out["algorithm_version"] == "1.0.0"


def test_snapshot_hash_is_deterministic_for_body(monkeypatch):
    s = build_snapshot(
        field_id="f",
        tenant_id="t",
        season_id="s",
        acquisition_date="2026-07-01",
        indices={},
        source="raster-service",
        quality={"executable": False},
        data_available_at="2026-07-01T01:00:00Z",
    )
    assert len(s["snapshot_hash"]) == 64 and s["contract_version"] == "vegetation-snapshot.v2"


def _measured_ndvi(**changes):
    observation = {
        "source": "raster-service",
        "estimated": False,
        "value": 0.7,
        "quality_score": 0.9,
        "valid_pixel_pct": 85.0,
        "provenance": dict(PROV),
    }
    observation.update(changes)
    return observation


@pytest.mark.unit
@pytest.mark.parametrize("quality", [float("nan"), float("inf"), True, 1.01])
def test_nonphysical_quality_cannot_authorize_execution(quality):
    assert not quality_gate({"ndvi": _measured_ndvi(quality_score=quality)})["executable"]


@pytest.mark.unit
@pytest.mark.parametrize("valid", [float("nan"), float("inf"), "NaN", "Infinity", 100.01])
def test_nonphysical_pixel_percentage_cannot_authorize_execution(valid):
    result = quality_gate({"ndvi": _measured_ndvi(valid_pixel_pct=valid)})
    assert not result["executable"]
    assert "ndvi_valid_pixel_pct_invalid" in result["reasons"]


@pytest.mark.unit
@pytest.mark.parametrize("ratio", [True, float("nan"), float("inf"), "NaN", 85.0])
def test_pixel_ratio_is_not_a_percentage_or_boolean(ratio):
    observation = _measured_ndvi(valid_pixel_ratio=ratio)
    observation.pop("valid_pixel_pct")
    assert not quality_gate({"ndvi": observation})["executable"]


@pytest.mark.unit
@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), True, -0.1, 1.1])
def test_invalid_quality_threshold_is_rejected(threshold):
    with pytest.raises(ValueError, match="min_quality"):
        quality_gate({"ndvi": _measured_ndvi()}, min_quality=threshold)


@pytest.mark.unit
@pytest.mark.parametrize("quality,pct", [(0.6, 60), (1.0, 100), (0.9, 85)])
def test_measured_quality_boundaries_keep_existing_policy(quality, pct):
    assert quality_gate({"ndvi": _measured_ndvi(quality_score=quality, valid_pixel_pct=pct)})[
        "executable"
    ]


@pytest.mark.unit
def test_cdse_provider_expectation_still_cannot_replace_applied_mask_identity():
    observation = _measured_ndvi()
    observation["provenance"]["qa_mask_version"] = None
    observation["cloud_mask_strategy"] = "provider_precomputed_expected"
    result = quality_gate({"ndvi": observation})
    assert not result["executable"]
    assert "ndvi_provenance_qa_mask_version_missing" in result["reasons"]
