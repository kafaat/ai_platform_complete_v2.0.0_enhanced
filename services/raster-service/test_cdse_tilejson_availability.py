"""حارس صدق توافر TileJSON (V54) — لا «جاهز» كاذب لمؤشّر غير مُصيَّر.

التوافر يشترط أن يكون المؤشّر مُصيَّراً: إمّا ضمن ``INDEX_EXPR`` (بعد المرادفات) أو
الصورة الخام ``truecolor`` (تُصيَّر الآن RGBA عبر evalscript ألوان طبيعيّة B04/B03/B02).
مؤشّر غير مُصيَّر مع ضبط CDSE يُبلَّغ ``available=False`` بسبب ``index_not_rendered``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _fn():
    # استيراد كسول داخل الاختبار: يتجنّب تلويث هويّة وحدة ``routers.cdse_tiles`` أثناء
    # الجمع (collection) الذي يكسر حارس التفكيك المعتمد على تطابق كائن الراوتر.
    from routers.cdse_tiles import _tilejson_availability

    return _tilejson_availability


def test_truecolor_is_reported_available_when_configured():
    # بعد إضافة تصيير RGB الحقيقيّ: الصورة الخام مُصيَّرة ⇒ متاحة (لا رسالة «غير جاهزة»).
    available, reason, message = _fn()(True, "truecolor")
    assert available is True
    assert reason is None
    assert message is None


def test_unrendered_index_is_not_reported_available_even_when_configured():
    available, reason, message = _fn()(True, "no_such_index")
    assert available is False
    assert reason == "index_not_rendered"
    assert message


def test_rendered_indices_available_when_configured():
    for index in ("ndvi", "ndmi", "ndsi", "evi", "savi"):
        available, reason, _ = _fn()(True, index)
        assert available is True, index
        assert reason is None


def test_index_aliases_resolve_to_rendered_expression():
    # salinity/moisture/vegetation مرادفات لمؤشّرات مُصيَّرة (ndsi/ndmi/ndvi).
    for index in ("salinity", "moisture", "vegetation"):
        available, _, _ = _fn()(True, index)
        assert available is True, index


def test_not_configured_is_unavailable_with_reason():
    available, reason, message = _fn()(False, "ndvi")
    assert available is False
    assert reason == "cdse_not_configured"
    assert message
