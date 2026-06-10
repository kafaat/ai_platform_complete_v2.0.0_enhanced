"""Unit tests: real RVI (Radar Vegetation Index) from Sentinel-1 VV/VH."""

from __future__ import annotations

import importlib.util
import os

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _load():
    spec = importlib.util.spec_from_file_location(
        "sar_rvi", os.path.join(ROOT, "services/raster-service/sar_rvi.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_rvi_monotonic_and_saturates():
    sr = _load()

    def rvi(vv, vh):
        return sr.rvi_from_vv_vh([[vv]], [[vh]])[0][0]

    assert rvi(0.1, 0.005) < rvi(0.1, 0.02) < 1.0  # bare < moderate
    assert rvi(0.1, 0.1) == 1.0  # dense volume scattering saturates


@pytest.mark.unit
def test_db_input_matches_linear():
    sr = _load()
    db = sr.rvi_from_vv_vh([[-10.0]], [[-16.0]], in_db=True)[0][0]
    lin = sr.rvi_from_vv_vh([[0.1]], [[10 ** (-1.6)]])[0][0]
    assert abs(db - lin) < 1e-9


@pytest.mark.unit
def test_nan_honesty_and_coverage():
    sr = _load()
    res = sr.compute_rvi([[0.1, None], [0.1, 0.08]], [[0.05, 0.02], [None, 0.04]])
    assert res["valid_pixels"] == 2 and res["total_pixels"] == 4
    assert res["coverage_pct"] == 50.0
    assert res["rvi_grid"][0][1] is None and res["rvi_grid"][1][0] is None


@pytest.mark.unit
def test_shape_guard_and_endpoint_wired():
    sr = _load()
    with pytest.raises(ValueError):
        sr.rvi_from_vv_vh([[0.1, 0.2]], [[0.1]])
    main = open(os.path.join(ROOT, "services/raster-service/main.py"), encoding="utf-8").read()
    assert '@app.post("/sar/rvi")' in main, "نقطة /sar/rvi مفقودة"
    assert "_rvi_from_sar_cog" in main, "مسار RVI من COG الرادار مفقود في /indices"
    assert "status_code=413" in main
