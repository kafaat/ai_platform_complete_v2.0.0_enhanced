"""
test_band_math_zones.py — تحقّق offline لدوالّ المؤشّرات الموسّعة (Sprint 5b)
وتقسيم مناطق الوصفة (quantile binning).

نقيّ تماماً: لا شبكة، لا rasterio. numpy فقط (مُحقن مثل soil_indices). يغطّي:
  • صيغ band_math (ndre/evi/msavi/moisture) بقيم معروفة + معالجة NaN/المقام صفر.
  • prescription_from_grid: تقسيم كوانتايل + معدّل لكلّ منطقة (VRT).
"""

import band_math
import management_zones as mz
import numpy as np


# ─── band_math: صيغ المؤشّرات الموسّعة ─────────────────────────────
def test_ndre_known_value():
    nir = np.array([3000.0])
    rededge = np.array([1000.0])
    # (3000-1000)/(3000+1000) = 0.5
    out = band_math.ndre(nir, rededge, np)
    assert abs(out[0] - 0.5) < 1e-9


def test_moisture_known_value():
    nir = np.array([3000.0])
    swir1 = np.array([1000.0])
    # (3000-1000)/(3000+1000) = 0.5
    out = band_math.moisture(nir, swir1, np)
    assert abs(out[0] - 0.5) < 1e-9


def test_msi_known_value():
    # MSI = SWIR1/NIR (أعلى = إجهاد أكبر) — 1000/4000 = 0.25.
    nir = np.array([4000.0])
    swir1 = np.array([1000.0])
    out = band_math.msi(nir, swir1, np)
    assert abs(out[0] - 0.25) < 1e-9


def test_msi_via_compute_and_registered_bands():
    # المصدر الأوحد: msi في NEW_INDEX_BANDS + compute() (بدل الفرع السطريّ المُزال).
    assert band_math.NEW_INDEX_BANDS["msi"] == ("nir", "swir1")
    out = band_math.compute("msi", {"nir": np.array([4000.0]), "swir1": np.array([1000.0])}, np)
    assert abs(out[0] - 0.25) < 1e-9


def test_msi_missing_band_raises():
    # صدق: نطاق مطلوب مفقود ⇒ ValueError (لا اختراع نطاق).
    import pytest

    with pytest.raises(ValueError, match="msi"):
        band_math.compute("msi", {"nir": np.array([4000.0])}, np)


def test_evi_known_value():
    # NIR=0.3, RED=0.1, BLUE=0.05 (reflectance) → 2.5*0.2/(0.3+0.6-0.375+1)=0.5/1.525
    blue = np.array([0.05])
    red = np.array([0.1])
    nir = np.array([0.3])
    out = band_math.evi(blue, red, nir, np)
    expected = 2.5 * (0.3 - 0.1) / (0.3 + 6 * 0.1 - 7.5 * 0.05 + 1)
    assert abs(out[0] - expected) < 1e-9


def test_msavi_bounds_and_monotonic():
    # MSAVI لتربة عارية (NIR≈RED) ≈ 0؛ لنبات كثيف (NIR≫RED) أكبر.
    red = np.array([0.1, 0.1])
    nir = np.array([0.1, 0.6])
    out = band_math.msavi(red, nir, np)
    assert out[1] > out[0], "MSAVI يزيد مع كثافة النبات"
    # تربة عارية NIR=RED → القيمة قرب الصفر (لكن موجبة صغيرة)
    assert abs(out[0]) < 0.15


def test_msavi_radicand_clipped_no_nan():
    # قيم شاذّة قد تجعل الجذع تحت الجذر سالباً — يجب ألّا يُنتج NaN.
    red = np.array([5.0])
    nir = np.array([0.0])
    out = band_math.msavi(red, nir, np)
    assert np.isfinite(out[0]), "MSAVI يجب أن يقصّ الجذر السالب لا أن يُنتج NaN"


def test_zero_denominator_safe():
    # NIR+REDEDGE=0 → epsilon يمنع القسمة على صفر (لا inf/NaN غير محكوم)
    nir = np.array([0.0])
    rededge = np.array([0.0])
    out = band_math.ndre(nir, rededge, np)
    assert np.isfinite(out[0])


def test_compute_dispatch_and_missing_band():
    bands = {"nir": np.array([3000.0]), "rededge": np.array([1000.0])}
    out = band_math.compute("ndre", bands, np)
    assert abs(out[0] - 0.5) < 1e-9
    # نطاق ناقص → ValueError صريح (صدق: لا اختراع)
    try:
        band_math.compute("evi", {"nir": np.array([1.0])}, np)
    except ValueError as e:
        assert "evi" in str(e).lower()
    else:
        raise AssertionError("متوقّع ValueError لنطاق ناقص")


def test_new_index_bands_registry_covers_sprint5b():
    # Sprint 5b (ndre/evi/msavi/moisture) + msi (وُحِّد من الفرع السطريّ إلى المصدر الأوحد).
    assert set(band_math.NEW_INDEX_BANDS) == {"ndre", "evi", "msavi", "moisture", "msi"}


# ─── prescription_from_grid: تقسيم الكوانتايل + الوصفة ─────────────
def test_prescription_quantile_three_zones():
    # شبكة 4x3 بقيم متدرّجة + خليّة null (تُتجاهَل)
    grid = [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
        [0.7, 0.8, 0.9],
        [1.0, None, 0.05],
    ]
    res = mz.prescription_from_grid(grid, n_zones=3, base_rate=100.0)
    assert res["n_zones"] == 3
    # 11 قيمة صالحة (12 - 1 null)
    assert res["total_pixels"] == 11
    zones = res["zones"]
    assert [z["zone"] for z in zones] == ["low", "medium", "high"]
    # كلّ منطقة لها إحصاء + معدّل موصى به
    for z in zones:
        assert "pixel_count" in z and "pct" in z and "value_range" in z
        assert "rate" in z and "factor" in z
    # compensate: المنطقة الضعيفة (low) تأخذ أكثر من القويّة (high)
    rate_low = next(z["rate"] for z in zones if z["zone"] == "low")
    rate_high = next(z["rate"] for z in zones if z["zone"] == "high")
    assert rate_low > rate_high
    assert "prescription" in res and len(res["prescription"]) == 3


def test_prescription_protect_strategy_inverts():
    grid = [[0.1, 0.5, 0.9], [0.2, 0.6, 0.95]]
    res = mz.prescription_from_grid(grid, n_zones=3, base_rate=50.0, strategy="protect")
    rate_low = next(z["rate"] for z in res["zones"] if z["zone"] == "low")
    rate_high = next(z["rate"] for z in res["zones"] if z["zone"] == "high")
    # protect: القويّة تأخذ أكثر (استثمار في المنتج)
    assert rate_high > rate_low


def test_prescription_no_base_rate_no_rx():
    grid = [[0.1, 0.5, 0.9], [0.2, 0.6, 0.95]]
    res = mz.prescription_from_grid(grid, n_zones=3)
    # بلا base_rate: لا وصفة معدّل، لكن المناطق + إحصاؤها موجودة
    assert "prescription" not in res
    assert len(res["zones"]) == 3
    for z in res["zones"]:
        assert "rate" not in z


def test_prescription_insufficient_pixels():
    grid = [[None, None], [0.5, None]]  # قيمة واحدة صالحة < 3 مناطق
    res = mz.prescription_from_grid(grid, n_zones=3, base_rate=100.0)
    assert res["zones"] == []
    assert "error" in res


if __name__ == "__main__":
    import sys

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nALL {len(fns)} TESTS PASSED")
    sys.exit(0)
