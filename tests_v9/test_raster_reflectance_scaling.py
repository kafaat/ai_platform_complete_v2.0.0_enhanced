"""صحّة تحويل DN→انعكاس للمؤشّرات المعتمِدة على المقياس (مراجعة GIS، المحور C).

الفجوة: صيغ EVI/SAVI/MSAVI تفترض انعكاساً [0,1] (يوثّقه test_evi_known_value)، لكن مسار
قراءة النطاق في raster-service كان يمرّر قيم DN الخام (Sentinel-2 L2A = انعكاس×10000)
دون تطبيق scale/offset ⇒ تشويه صامت لهذه المؤشّرات (المؤشّرات النسبيّة كـNDVI غير متأثّرة).

(A) وحدة band_math.to_reflectance (تُحمّل بالمسار، numpy فقط).
(B) حُرّاس مصدر: band() يطبّق التحويل، وProcessRequest يقبل التجاوز اليدويّ.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
RASTER = os.path.join(ROOT, "services/raster-service")


@pytest.fixture(scope="module")
def bm():
    np = pytest.importorskip("numpy")
    spec = importlib.util.spec_from_file_location(
        "band_math_refl_test", os.path.join(RASTER, "band_math.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m._np = np
    return m


# ── (A) وحدة to_reflectance ──
def test_identity_when_unit_scale(bm):
    np = bm._np
    arr = np.array([1000.0, 3000.0])
    # هويّة: (None,None) و(1.0,0.0) ⇒ لا تغيير (لا انحدار للمصادر غير المُعلِنة)
    assert np.array_equal(bm.to_reflectance(arr, None, None, np), arr)
    assert np.array_equal(bm.to_reflectance(arr, 1.0, 0.0, np), arr)


def test_applies_scale(bm):
    np = bm._np
    arr = np.array([1000.0, 3000.0])  # DN
    out = bm.to_reflectance(arr, 0.0001, 0.0, np)
    assert np.allclose(out, [0.1, 0.3])  # انعكاس [0,1]


def test_applies_scale_and_offset(bm):
    np = bm._np
    arr = np.array([2000.0])  # DN، baseline offset −1000 ثمّ مقياس 1e-4
    # reflectance = DN*scale + offset
    out = bm.to_reflectance(arr, 0.0001, -0.1, np)
    assert np.allclose(out, [0.1])  # 2000*1e-4 - 0.1 = 0.1


def test_evi_correct_after_scaling(bm):
    np = bm._np
    # DN لـnir/red/blue (انعكاس 0.3/0.1/0.05 ×10000) ⇒ بعد المقياس = EVI الصحيح
    nir = bm.to_reflectance(np.array([3000.0]), 0.0001, 0.0, np)
    red = bm.to_reflectance(np.array([1000.0]), 0.0001, 0.0, np)
    blue = bm.to_reflectance(np.array([500.0]), 0.0001, 0.0, np)
    out = bm.evi(blue, red, nir, np)
    expected = 2.5 * (0.3 - 0.1) / (0.3 + 6 * 0.1 - 7.5 * 0.05 + 1)
    assert abs(float(out[0]) - expected) < 1e-6


def test_nan_preserved_through_scaling(bm):
    np = bm._np
    arr = np.array([np.nan, 2000.0])
    out = bm.to_reflectance(arr, 0.0001, 0.0, np)
    assert np.isnan(out[0]) and abs(float(out[1]) - 0.2) < 1e-9


# ── (B) حُرّاس المصدر (بعد تفكيك phase10) ──
def _src(*names: str) -> str:
    parts = []
    for name in names:
        with open(os.path.join(RASTER, name), encoding="utf-8") as f:
            parts.append(f.read())
    return "\n".join(parts)


def test_band_applies_reflectance():
    # قارئ band() ومنطق البكسل/النطاق انتقلا إلى raster_pixel_processing.py.
    src = _src("raster_pixel_processing.py")
    assert "band_math.to_reflectance(" in src, "band() لا يطبّق تحويل الانعكاس"
    assert "src.scales" in src and "src.offsets" in src, "لا يحترم scale/offset المُعلَن في الراستر"


def test_process_request_has_reflectance_override():
    # حقول ProcessRequest في raster_api_models.py، وتُستهلَك في raster_pixel_processing.py.
    src = _src("raster_api_models.py", "raster_pixel_processing.py")
    assert "reflectance_scale" in src and "reflectance_offset" in src, (
        "ProcessRequest لا يقبل تجاوز المقياس اليدويّ"
    )
