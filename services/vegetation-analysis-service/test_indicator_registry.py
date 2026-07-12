"""Guards for the canonical indicator registry (pure logic, no services)."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from indicator_registry import build_feature_manifest, definition, validate_observation

pytestmark = pytest.mark.unit


def test_registry_has_core_indices():
    assert definition("ndvi")["decision_eligible"] is True
    assert definition("lai")["kind"] == "derived"


def test_unknown_indicator_is_rejected():
    with pytest.raises(KeyError):
        definition("bogus")


def test_observed_requires_complete_provenance():
    errors = validate_observation(
        "ndvi",
        {
            "value": 0.6,
            "source": "raster-service",
            "estimated": False,
            "valid_pixel_pct": 80,
            "provenance": {
                "scene_id": "s",
                "acquisition_datetime": "2026-01-01T00:00:00Z",
                "algorithm_version": "1",
            },
        },
    )
    assert "ndvi_provenance_qa_mask_version_missing" in errors
    assert "ndvi_data_available_at_missing" in errors


def test_valid_pixel_threshold_enforced():
    errors = validate_observation(
        "ndvi",
        {
            "value": 0.6,
            "source": "raster-service",
            "estimated": False,
            "valid_pixel_pct": 30,
            "data_available_at": "2026-01-01T01:00:00Z",
            "provenance": {
                "scene_id": "s",
                "acquisition_datetime": "2026-01-01T00:00:00Z",
                "algorithm_version": "1",
                "qa_mask_version": "scl-v1",
            },
        },
    )
    assert errors == ["ndvi_valid_pixel_pct_below_threshold"]


def test_manifest_is_stable_and_classified():
    m = build_feature_manifest({"lai": {"source": "vegetation-model", "algorithm_version": "1"}})
    assert m["id"] == "vegetation-core"
    assert m["features"][0]["kind"] == "derived"
    assert m["features"][0]["decision_eligible"] is False
