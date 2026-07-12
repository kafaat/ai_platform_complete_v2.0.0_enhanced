"""Production truth closure: no synthetic vegetation values on any serving path."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytestmark = pytest.mark.unit


def test_no_synthetic_timeseries_generator_remains():
    src = (Path(__file__).resolve().parent / "vegetation_runtime.py").read_text()
    assert "def _generate_timeseries" not in src
    assert "synthetic_estimate" not in src


def test_current_ndvi_reads_authoritative_raster_only():
    src = (Path(__file__).resolve().parent / "routers" / "analysis.py").read_text()
    assert "_current_ndvi_from_raster" in src
    section = src.split('@router.get("/v1/ndvi/current/{field_id}")', 1)[1].split(
        '@router.get("/v1/all_fields")', 1
    )[0]
    assert "run_analysis(field_id" not in section
    assert "لم يتم إنشاء قيمة تركيبيّة" in src


def test_current_ndvi_helper_never_fabricates():
    import vegetation_runtime as vr

    assert callable(vr._current_ndvi_from_raster)
    src = (Path(__file__).resolve().parent / "vegetation_runtime.py").read_text()
    helper = src.split("async def _current_ndvi_from_raster", 1)[1].split("\ndef ", 1)[0]
    for forbidden in ("_realistic_bands", "_compute_indices", "_deterministic_seed"):
        assert forbidden not in helper


def test_production_readiness_depends_on_raster():
    src = (Path(__file__).resolve().parent / "routers" / "health.py").read_text()
    assert "authoritative-raster-only" in src
    assert "RASTER_SERVICE_URL" in src
