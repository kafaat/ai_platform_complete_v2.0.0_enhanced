"""Unit tests: Fractional Vegetation Cover (FVC) — raster-service.

يحرس الفجوة المُسدَّة: النظام يحسب LAI (كثافة الأوراق 3D) لكن ليس FVC (نسبة تغطية
الأرض 2D). هذه الاختبارات تُثبت دقّة صيغة نموذج البكسل الثنائي، الطرق الثلاث،
كشف التصحّر، وصدق فجوات السحاب — وأنّ نقطة /fvc/compute مربوطة بحدّ حجم.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _load_fvc():
    spec = importlib.util.spec_from_file_location(
        "fvc", os.path.join(ROOT, "services/raster-service/fvc.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_formula_exact_dimidiate():
    """soil→0، mid→0.5، veg→1 (نموذج البكسل الثنائي)."""
    fvc = _load_fvc()
    res = fvc.compute_fvc([[0.1, 0.5, 0.9]], method="dynamic_range", ndvi_soil=0.1, ndvi_veg=0.9)
    assert res["fvc_grid"][0] == [0.0, 0.5, 1.0]


@pytest.mark.unit
def test_cumulative_frequency_adaptive_endmembers():
    fvc = _load_fvc()
    grid = [[round(0.05 + 0.8 * ((r * 8 + c) / 63), 3) for c in range(8)] for r in range(8)]
    res = fvc.compute_fvc(grid, method="cumulative_frequency")
    assert res["ndvi_soil"] < res["ndvi_veg"]  # 5% < 95%
    assert 0.0 <= res["stats"]["min"] and res["stats"]["max"] <= 1.0


@pytest.mark.unit
def test_desertification_detection():
    fvc = _load_fvc()
    res = fvc.compute_fvc([[0.08] * 8 for _ in range(8)], method="global_constant")
    assert res["classification"] == "low_cover"
    assert res["areas"]["desertification_pct"] > 50
    assert "تصحّر" in res["interpretation_ar"]


@pytest.mark.unit
def test_cloud_gap_honesty_and_low_contrast_note():
    fvc = _load_fvc()
    res = fvc.compute_fvc([[0.5, None, 0.6], [None, 0.55, 0.5]], method="global_constant")
    assert res["valid_pixels"] == 4
    assert res["fvc_grid"][0][1] is None  # الفجوة محفوظة
    uniform = fvc.compute_fvc([[0.4] * 4 for _ in range(4)], method="cumulative_frequency")
    assert uniform["note"] is not None  # حقل موحّد ⇒ note صريحة


@pytest.mark.unit
def test_deterministic_and_input_validation():
    fvc = _load_fvc()
    grid = [[0.2, 0.7], [0.3, 0.8]]
    assert fvc.compute_fvc(grid) == fvc.compute_fvc(grid)
    with pytest.raises(ValueError):
        fvc.compute_fvc(grid, method="nope")
    with pytest.raises(ValueError):
        fvc.compute_fvc(grid, method="dynamic_range")  # بلا قيم طرفيّة


@pytest.mark.unit
def test_endpoint_wired_with_size_cap():
    # بعد تفكيك main.py: النقطة قد تكون @router في routers/ — نمسح main + routers معاً.
    from raster_route_source import raster_combined_source

    main = raster_combined_source(ROOT)
    assert '@router.post("/fvc/compute")' in main or '@app.post("/fvc/compute")' in main, (
        "نقطة /fvc/compute مفقودة"
    )
    assert "MAX_CHANGE_GRID_CELLS" in main and "status_code=413" in main, "حدّ الحجم مفقود"
