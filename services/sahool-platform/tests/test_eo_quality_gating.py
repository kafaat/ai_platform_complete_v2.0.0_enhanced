"""Quality and dependence are different from value presence and agreement."""

import json

import pytest
from core.crop_intelligence.spectral import build_canonical_spectral_state
from core.engines.spectral_stress_bridge import (
    assess_water_stress_msi,
    assess_water_stress_ndmi,
    fuse_water_stress,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "quality",
    [
        None,
        "unknown",
        "invalid",
        "unavailable",
        "insufficient",
        "degraded",
        "estimated",
        "raster_service_authoritative",
        "inconsistent_inputs",
        "VALIDATED",
        [],
        {},
    ],
)
def test_quality_allowlist_is_required(quality):
    out = build_canonical_spectral_state(
        ndmi=-0.1, msi=1.3, temporal_compatible=True, quality_status=quality
    )
    assert out["water_stress"]["confirmation_available"] is False
    assert out["water_stress"]["confirmed"] is None
    assert out["water_stress"]["signal"] == "unknown"


def test_explicit_validated_compatible_pair_can_confirm():
    out = build_canonical_spectral_state(
        ndmi=-0.1, msi=1.3, temporal_compatible=True, quality_status="validated"
    )
    assert out["water_stress"]["confirmed"] is True
    assert out["water_stress"]["independent_evidence_count"] == 1


def test_missing_quality_never_synthesizes_validation():
    out = build_canonical_spectral_state(ndvi=0.4)
    assert out["quality_status"] == "unknown"
    assert out["status"] == "degraded"


@pytest.mark.parametrize("key", ["ndvi", "ndre", "ndmi", "msi"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 10**400, True, "0.3"])
def test_invalid_numbers_are_missing(key, bad):
    out = build_canonical_spectral_state(**{key: bad})
    assert out["indices"][key] is None
    json.dumps(out, allow_nan=False)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 10**400, True, "bad", [], {}])
def test_bridge_direct_entry_points_fail_safe(bad):
    assert assess_water_stress_ndmi(bad)["signal"] == "unknown"
    assert assess_water_stress_msi(bad)["signal"] == "unknown"


@pytest.mark.parametrize("ndmi,msi", [(0.6, 0.25), (-0.5, 3.0), (0.0, 1.0)])
def test_redundant_indices_are_not_two_independent_observations(ndmi, msi):
    out = fuse_water_stress(ndmi, msi)
    assert out["confidence"] != "high"
    assert out["independent_evidence_count"] == 1
    assert out["dependency_groups"] == ["nir_swir1_ratio"]


def test_absent_evidence_has_zero_count():
    out = fuse_water_stress()
    assert out["independent_evidence_count"] == 0
    assert out["fused_signal"] == "unknown"


def test_range_invalid_spectral_values_cannot_confirm():
    out = build_canonical_spectral_state(
        ndmi=2, msi=-1, temporal_compatible=True, quality_status="validated"
    )
    assert out["water_stress"]["confirmed"] is None
    assert out["status"] == "unavailable"
