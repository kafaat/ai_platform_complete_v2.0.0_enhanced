"""اختبار وحدة لمنطق CDSE النقيّ (evalscript / الأبعاد / الفحص) — بلا شبكة.

CDSE هو المزوّد الافتراضيّ للصور (raster-service) مع fallback إلى Element84. هذا الاختبار
يقفل **الدوالّ النقيّة** فقط (تُبنى evalscript صحيحة لكلّ مؤشّر، الأبعاد مقيَّدة، الفحص يحترم
البيئة) — لا يضرب CDSE حيّاً (لا اعتمادات/شبكة في CI). المسار الحيّ يؤكّده المشغّل ببيئته.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_RASTER = Path(__file__).resolve().parent.parent / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import cdse_client  # noqa: E402


def test_supported_includes_default_indicators():
    """المؤشّرات الافتراضيّة للأتمتة (ndvi/ndre/ndsi) مدعومة في CDSE — وإلّا انكسر المسار الافتراضيّ."""
    supported = cdse_client.supported_indices()
    for ind in ("ndvi", "ndre", "ndsi"):
        assert ind in supported, f"{ind} مفقود من دعم CDSE"


# مؤشّرات أحاديّة النطاق FLOAT32 فقط (truecolor مستثنًى — RGBA UINT8، يُختبَر أدناه).
@pytest.mark.parametrize("index", sorted(cdse_client.INDEX_EXPR))
def test_build_evalscript_is_valid_v3(index):
    """كلّ مؤشّر أحاديّ النطاق يُنتج evalscript V3 صالحاً: إصدار + setup + FLOAT32 + قناع dataMask."""
    script = cdse_client.build_evalscript(index)
    assert "//VERSION=3" in script
    assert "function setup()" in script
    assert "function evaluatePixel(s)" in script
    assert '"FLOAT32"' in script
    assert "dataMask" in script  # القناع يحوّل بكسلات بلا بيانات إلى NaN (لا تلوّث الإحصاء)
    # كلّ نطاق يظهر في تعبير المؤشّر يجب أن يُعلَن في input bands.
    bands, _expr = cdse_client.INDEX_EXPR[index]
    for band in bands:
        assert f'"{band}"' in script


def test_build_truecolor_evalscript_is_valid_v3_rgba():
    """الصورة الخام truecolor تُنتج evalscript V3 صالحاً بـRGBA UINT8 (لا FLOAT32 أحاديّ)،
    وتقنّع الغيوم/بلا-البيانات إلى شفّاف. build_evalscript يُوجّهها تلقائيّاً."""
    for script in (
        cdse_client.build_truecolor_evalscript(),
        cdse_client.build_evalscript("truecolor"),
    ):
        assert "//VERSION=3" in script
        assert "function setup()" in script
        assert "function evaluatePixel(s)" in script
        assert "bands: 4" in script and '"UINT8"' in script
        for band in ('"B04"', '"B03"', '"B02"', '"SCL"', '"dataMask"'):
            assert band in script
    assert "truecolor" in cdse_client.supported_indices()


def test_ndvi_expression_uses_correct_bands():
    """NDVI = (B08 - B04)/(B08 + B04) — يطابق مصدر الحقيقة (band_math) لا تلفيق."""
    bands, expr = cdse_client.INDEX_EXPR["ndvi"]
    assert set(bands) == {"B04", "B08"}
    assert "s.B08 - s.B04" in expr


def test_build_evalscript_rejects_unsupported():
    """مؤشّر غير معرَّف ⇒ ValueError (لا evalscript مُلفَّق)."""
    with pytest.raises(ValueError):
        cdse_client.build_evalscript("not_an_index")


def test_bbox_dims_clamped_and_positive():
    """الأبعاد موجبة ومقيَّدة بـ[16, max_px]؛ مستطيل صغير لا ينزل تحت 16، وكبير لا يتجاوز السقف."""
    # مستطيل صغير جدّاً (~10م) ⇒ الحدّ الأدنى 16.
    w, h = cdse_client.bbox_dims([44.0, 15.0, 44.0001, 15.0001])
    assert w >= 16 and h >= 16
    # مستطيل كبير ⇒ مقيَّد بالسقف.
    w2, h2 = cdse_client.bbox_dims([44.0, 15.0, 45.0, 16.0], max_px=2500)
    assert w2 <= 2500 and h2 <= 2500
    assert w2 > 0 and h2 > 0


def test_is_configured_reflects_env(monkeypatch):
    """is_configured: True فقط مع اعتمادين و CDSE_ENABLED≠false — وإلّا fallback إلى Element84."""
    monkeypatch.setenv("CDSE_CLIENT_ID", "x")
    monkeypatch.setenv("CDSE_CLIENT_SECRET", "y")
    monkeypatch.delenv("CDSE_ENABLED", raising=False)
    assert cdse_client.is_configured() is True

    # تعطيل صريح ⇒ False (تحكّم المشغّل).
    monkeypatch.setenv("CDSE_ENABLED", "false")
    assert cdse_client.is_configured() is False

    # غياب الاعتمادات ⇒ False (السلوك القائم: Element84).
    monkeypatch.delenv("CDSE_ENABLED", raising=False)
    monkeypatch.delenv("CDSE_CLIENT_SECRET", raising=False)
    assert cdse_client.is_configured() is False
