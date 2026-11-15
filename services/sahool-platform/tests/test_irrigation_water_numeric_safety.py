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
    assert compute_sar(1e308, 1e308, 1e308) is None


def test_rsc_combining_finite_ions_never_returns_nan():
    assert compute_rsc(1e308, 1e308, 1e308, 1e308) is None


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
    assert response["verdict"] == "insufficient_data"
    assert response["indices"]["sar"] is None
    assert response["indices"]["rsc_meq_l"] is None
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
