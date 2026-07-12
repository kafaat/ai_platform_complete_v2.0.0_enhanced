"""اختبارات وحدة لأداة مستكشف المؤشّرات بعد توحيد RIV — أداة حدوديّة fail-closed.

الحساب الطيفيّ مملوك حصراً لخدمة Raster (band_math النسخة المرجعيّة الوحيدة).
الأداة تحتفظ بمعرّفها للتوافق لكنّها لا تنفّذ band-math محلّيّاً أبداً: تعيد
value=None و available=False وتوجّه إلى منتج Raster الموثَّق بالمشهد والجودة.
"""

import pytest
from core.agri_tools.tools.index_explorer import compute

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("index", ["NDVI", "NDRE", "EVI", "MSAVI"])
def test_boundary_never_computes_locally(index):
    """كلّ مؤشّر مدعوم يعيد حدود الملكيّة لا قيمة محسوبة — حتى مع نطاقات كاملة."""
    out = compute({"index": index, "nir": 0.5, "red": 0.1, "red_edge": 0.3, "blue": 0.05})
    assert out["index"] == index
    assert out["value"] is None
    assert out["available"] is False
    assert out["owner_service"] == "raster-service"
    assert out["reason"] == "validated_raster_product_required"
    assert isinstance(out["interpretation_ar"], str) and "Raster" in out["interpretation_ar"]


def test_index_is_case_insensitive():
    out = compute({"index": "ndvi"})
    assert out["index"] == "NDVI" and out["value"] is None


def test_unsupported_index_raises():
    with pytest.raises(ValueError, match="غير مدعوم"):
        compute({"index": "BOGUS", "nir": 0.5, "red": 0.1})


def test_missing_index_raises():
    with pytest.raises(ValueError, match="غير مدعوم"):
        compute({})


def test_no_band_inputs_required():
    """الحدود لا تتطلّب نطاقات إطلاقاً — لا اختراع حساب من مدخلات جزئيّة."""
    out = compute({"index": "EVI"})
    assert out["value"] is None and out["available"] is False


def test_no_local_band_math_in_module_source():
    """حارس ساكن: لا صيغ طيفيّة تنفيذيّة في وحدة الأداة (ملكيّة Raster حصراً)."""
    import inspect

    import core.agri_tools.tools.index_explorer as mod

    src = inspect.getsource(mod)
    executable = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith(("#", '"', "'"))
    )
    assert "nir - red" not in executable and "2.5 *" not in executable
