from __future__ import annotations

import pytest
from raster_indicator_product import (
    ValidatedIndicatorProduct,
    from_grid_response,
    from_validated_raster_product,
)


def _real_grid_payload() -> dict:
    return {
        "field_id": "field_001",
        "index": "ndvi",
        "date": "2026-05-01T08:30:00Z",
        "stats": {"min": 0.2, "max": 0.8, "mean": 0.55},
        "source": "sentinel2_l2a",
        "real_data": True,
        "valid_pixel_ratio": 0.93,
        "confidence": 0.87,
    }


def test_schema_and_real_data_envelope():
    out = from_grid_response(_real_grid_payload())
    assert out["schema"] == "sahool.validated_indicator_product/1"
    assert out["source"] == "raster-service"
    assert out["estimated"] is False
    assert out["real_data"] is True
    assert out["quality_gate_passed"] is True
    assert out["quality_score"] == 0.87  # from confidence fallback
    assert out["valid_pixel_ratio"] == 0.93
    assert out["stats"] == {"min": 0.2, "max": 0.8, "mean": 0.55}


def test_simulation_envelope_is_estimated_and_gate_not_passed():
    payload = {
        "field_id": "no_such_field",
        "index": "salinity",
        "date": "latest",
        "stats": {"min": -0.1, "max": 0.4, "mean": 0.1},
        "source": "simulation",
        "real_data": False,
    }
    out = from_grid_response(payload)
    assert out["source"] == "simulation"
    assert out["estimated"] is True
    assert out["real_data"] is False
    assert out["quality_gate_passed"] is False
    # simulation never carries quality/provenance
    assert out["quality_score"] is None
    assert out["valid_pixel_ratio"] is None
    assert out["provenance"] is None


def test_honesty_invariant_simulation_cannot_be_non_estimated():
    with pytest.raises(ValueError):
        ValidatedIndicatorProduct(
            field_id="f",
            index="ndvi",
            date="latest",
            source="simulation",
            estimated=False,
            real_data=False,
        )


def test_honesty_invariant_simulation_cannot_pass_quality_gate():
    with pytest.raises(ValueError):
        ValidatedIndicatorProduct(
            field_id="f",
            index="ndvi",
            date="latest",
            source="simulation",
            estimated=True,
            quality_gate_passed=True,
        )


def test_honesty_invariant_real_data_requires_raster_service():
    with pytest.raises(ValueError):
        ValidatedIndicatorProduct(
            field_id="f",
            index="ndvi",
            date="latest",
            source="simulation",
            estimated=True,
            real_data=True,
        )


def test_provenance_round_trip():
    provenance = {
        "schema": "sahool.raster_provenance/1",
        "source": "sentinel2_l2a",
        "scene_id": "S2A_MSIL2A_20260501",
        "capture_datetime": "2026-05-01T08:30:00Z",
        "source_uri": "file:///tmp/scene.tif",
    }
    out = from_grid_response(_real_grid_payload(), provenance=provenance)
    assert out["provenance"] is not None
    assert out["provenance"]["scene_id"] == "S2A_MSIL2A_20260501"
    assert out["provenance"]["source_uri"] == "file:///tmp/scene.tif"
    assert out["provenance"]["processing_version"] == "sahool.raster_validated_product/1"


def test_no_fabricated_provenance_when_absent():
    payload = _real_grid_payload()  # carries no provenance
    out = from_grid_response(payload)
    assert out["provenance"] is None


def test_from_validated_raster_product_pulls_quality_envelope():
    vrp = {
        "schema": "sahool.validated_raster_product/1",
        "quality_score": 0.82,
        "valid_pixel_ratio": 0.9,
        "provenance": {
            "schema": "sahool.raster_provenance/1",
            "scene_id": "SCENE-XYZ",
        },
    }
    out = from_validated_raster_product(
        field_id="field_001",
        index="ndvi",
        date="latest",
        stats={"min": 0.1, "max": 0.9, "mean": 0.5},
        validated_raster_product=vrp,
    )
    assert out["source"] == "raster-service"
    assert out["estimated"] is False
    assert out["quality_gate_passed"] is True
    assert out["quality_score"] == 0.82
    assert out["valid_pixel_ratio"] == 0.9
    assert out["provenance"]["scene_id"] == "SCENE-XYZ"


def test_quality_score_ignores_bool_confidence():
    payload = _real_grid_payload()
    payload.pop("confidence")
    payload["confidence"] = True  # honest: a bool is not a quality score
    out = from_grid_response(payload)
    assert out["quality_score"] is None
