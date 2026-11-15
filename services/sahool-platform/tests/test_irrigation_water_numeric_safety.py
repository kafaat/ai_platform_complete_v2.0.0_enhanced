"""Overflow guard for irrigation-water SAR/RSC (model-only, no DB/services)."""

import math
import random

import pytest
from core.irrigation_water_analysis import (
    WaterSample,
    analyze_water_sample,
    compute_rsc,
    compute_sar,
)
from fastapi.responses import JSONResponse

pytestmark = pytest.mark.unit


def test_sar_combining_finite_ions_never_forges_zero_from_infinity():
    assert compute_sar(1e308, 1e308, 1e308) == pytest.approx(1e154)


def test_rsc_combining_finite_ions_never_returns_nan():
    assert compute_rsc(1e308, 1e308, 1e308, 1e308) == 0.0


def test_sar_finite_tiny_denominator_never_yields_infinity():
    assert compute_sar(1e308, 1e-300, 1e-300) is None


def test_accepted_individually_finite_sample_is_json_serializable():
    sample = WaterSample(
        sample_id="extreme-finite",
        na=1e308,
        ca=1e308,
        mg=1e308,
        co3=1e308,
        hco3=1e308,
        ec_dsm=1,
    )
    response = analyze_water_sample(sample)
    assert response["verdict"] == "needs_treatment"
    assert response["indices"]["sar"] == pytest.approx(1e154)
    assert response["indices"]["rsc_meq_l"] == 0.0
    assert JSONResponse(response).status_code == 200


def test_seeded_numeric_stress_does_not_produce_nonfinite_indices():
    rng = random.Random(20261114)
    samples = 2000
    for i in range(samples):
        # Include tiny and huge finite values without inventing a physical range.
        vals = [10.0 ** rng.uniform(-300, 308) for _ in range(5)]
        sample = WaterSample(
            sample_id=f"stress-{i}",
            na=vals[0],
            ca=vals[1],
            mg=vals[2],
            co3=vals[3],
            hco3=vals[4],
            ec_dsm=1.0,
        )
        result = analyze_water_sample(sample)
        for key in ("sar", "rsc_meq_l"):
            n = result["indices"][key]
            assert n is None or math.isfinite(n), f"nonfinite {key} in case {i}"
        JSONResponse(result)


def test_rsc_preserves_small_remainder_across_large_cancellation():
    assert compute_rsc(1e308, 1.0, 0.0, 1e308) == 1.0


def test_real_rsc_overflow_remains_uncomputable_and_json_safe():
    assert compute_rsc(1e308, 1e308, 0.0, 0.0) is None


def test_arbitrarily_large_integer_fails_closed_without_uncaught_overflow():
    with pytest.raises(ValueError, match="na"):
        WaterSample(sample_id="x", na=10**1000)
    assert compute_sar(10**1000, 1, 1) is None
    assert compute_rsc(10**1000, 1, 1, 1) is None


def test_large_finite_python_integers_are_still_computable():
    x = 10**308
    assert compute_sar(x, x, x) == pytest.approx(1e154)
    assert compute_rsc(x, x, x, x) == 0.0


def test_subnormal_calcium_plus_magnesium_not_halved_to_zero():
    tiny = 5e-324
    assert compute_sar(1.0, tiny, tiny) is not None


# "river" is a v168 source type (owner decision 2026-11-14), so it is accepted now;
# "ocean" stands for a clearly unknown kind.
@pytest.mark.parametrize("source", ["field:North", "well:123", "ocean", "mixed", ""])
def test_water_sample_core_refuses_unconstrained_source_kind(source):
    with pytest.raises(ValueError, match="source"):
        WaterSample(sample_id="x", source=source)


@pytest.mark.parametrize("source", ["well", "river", "rainwater", "other"])
def test_water_sample_core_accepts_the_v168_source_kinds(source):
    assert WaterSample(sample_id="x", source=source).source == source


def test_blend_rejects_huge_integer_ratio_without_500():
    from core.irrigation_water_analysis import compute_blend_water_quality

    result = compute_blend_water_quality([{"source_id": "x", "mixing_ratio": 10**1000}])
    assert result["status"] == "not_computable"
    assert result["reason"] == "mixing_ratio_invalid"


def test_direct_ec_classification_rejects_unrepresentable_integer():
    from core.irrigation_water_analysis import classify_ec

    assert classify_ec(10**1000)["class"] is None
