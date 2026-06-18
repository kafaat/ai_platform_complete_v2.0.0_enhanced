"""اختبارات وحدة لأداة مستكشف مؤشّرات الغطاء النباتيّ (index_explorer).

نقيّة حتميّة: تتحقّق من الصيغ على قيم ملموسة، ومن أخطاء النطاق المفقود وحالة
المقام الصفريّ. كما تؤكّد تطابق النتائج مع صيغ band_math (نفس المرجع العلميّ).
"""

import math

import pytest
from core.agri_tools.tools.index_explorer import compute

pytestmark = pytest.mark.unit


def test_ndvi_concrete():
    out = compute({"index": "NDVI", "nir": 0.5, "red": 0.1})
    assert out["index"] == "NDVI"
    assert out["value"] == 0.6667  # (0.5-0.1)/(0.5+0.1) = 0.4/0.6
    assert isinstance(out["interpretation_ar"], str) and out["interpretation_ar"]


def test_ndre_concrete():
    # NDRE = (NIR - RedEdge)/(NIR + RedEdge) = (0.6-0.3)/(0.6+0.3) = 0.3333
    out = compute({"index": "NDRE", "nir": 0.6, "red_edge": 0.3})
    assert out["index"] == "NDRE"
    assert out["value"] == 0.3333


def test_evi_concrete():
    # EVI = 2.5*(NIR-RED)/(NIR + 6*RED - 7.5*BLUE + 1)
    nir, red, blue = 0.5, 0.1, 0.05
    expected = round(2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1), 4)
    out = compute({"index": "EVI", "nir": nir, "red": red, "blue": blue})
    assert out["index"] == "EVI"
    assert out["value"] == expected


def test_msavi_concrete():
    nir, red = 0.5, 0.1
    term = 2 * nir + 1
    expected = round((term - math.sqrt(term * term - 8 * (nir - red))) / 2, 4)
    out = compute({"index": "MSAVI", "nir": nir, "red": red})
    assert out["value"] == expected


def test_missing_band_raises():
    # NDRE يتطلّب red_edge — غيابه يرفع ValueError برسالة عربيّة.
    with pytest.raises(ValueError, match="الحافة الحمراء"):
        compute({"index": "NDRE", "nir": 0.6})


def test_missing_band_evi_raises():
    # EVI يتطلّب red و blue.
    with pytest.raises(ValueError):
        compute({"index": "EVI", "nir": 0.5, "red": 0.1})


def test_unsupported_index_raises():
    with pytest.raises(ValueError, match="غير مدعوم"):
        compute({"index": "BOGUS", "nir": 0.5, "red": 0.1})


def test_zero_denominator_returns_none():
    # NDVI بمقام صفريّ: nir=red=0 ⇒ القيمة None مع تفسير واضح.
    out = compute({"index": "NDVI", "nir": 0.0, "red": 0.0})
    assert out["value"] is None
    assert "مقام صفريّ" in out["interpretation_ar"]


def test_matches_band_math_formulas():
    """تطابق نتائج الأداة مع صيغ band_math المرجعيّة (على أعداد مفردة)."""
    import importlib.util
    import pathlib

    bm_path = pathlib.Path(__file__).resolve().parents[2] / "raster-service" / "band_math.py"
    if not bm_path.exists():
        pytest.skip("band_math غير متوفّر في هذا الفرع")
    spec = importlib.util.spec_from_file_location("band_math", bm_path)
    bm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bm)

    # وسيط numpy مصغّر للأعداد المفردة (where/sqrt فقط).
    class _Np:
        @staticmethod
        def where(cond, a, b):
            return a if cond else b

        @staticmethod
        def sqrt(x):
            return math.sqrt(x)

    np = _Np()
    nir, red, rededge, blue = 0.5, 0.1, 0.3, 0.05

    assert compute({"index": "NDVI", "nir": nir, "red": red})["value"] == round(
        bm.ndvi(red, nir, np), 4
    )
    assert compute({"index": "NDRE", "nir": nir, "red_edge": rededge})["value"] == round(
        bm.ndre(nir, rededge, np), 4
    )
    assert compute({"index": "EVI", "nir": nir, "red": red, "blue": blue})["value"] == round(
        bm.evi(blue, red, nir, np), 4
    )
    assert compute({"index": "MSAVI", "nir": nir, "red": red})["value"] == round(
        bm.msavi(red, nir, np), 4
    )
