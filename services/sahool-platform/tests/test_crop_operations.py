"""اختبارات تقويم العمليّات المرتبط بمراحل النموّ (core.crop_operations) — أجزاء صرفة.

تغطّي: عمليّات مرحلة مُسمّاة (مفاتيح + فئة صالحة)، التقويم الكامل لمحصول له فينولوجيا
(4 مراحل، حساسيّة الطور التكاثريّ: ريّ ذروة + مسح IPM)، محصول بلا فينولوجيا ⇒ فارغ،
عمليّات المرحلة الحاليّة، وغمزة العائلة (بقوليّة مقابل حبوب). لا حاجة لقاعدة بيانات.
"""

import pytest
from core.crop_operations import (
    _VALID_CATEGORIES,
    crop_operations_calendar,
    current_stage_operations,
    stage_operations,
)

pytestmark = pytest.mark.unit

_REQUIRED_KEYS = {"category", "category_ar", "operation_ar", "timing_ar", "note_ar"}


def _assert_valid_op(op: dict) -> None:
    assert _REQUIRED_KEYS <= set(op.keys())
    assert op["category"] in _VALID_CATEGORIES
    for key in _REQUIRED_KEYS:
        assert isinstance(op[key], str) and op[key].strip()


def test_stage_operations_initial_well_formed():
    ops = stage_operations("initial")
    assert ops, "initial يجب أن تحوي عمليّات"
    for op in ops:
        _assert_valid_op(op)


def test_stage_operations_unknown_stage_empty():
    assert stage_operations("not_a_stage") == []
    assert stage_operations("") == []


def test_all_named_stages_have_operations():
    for stage in ("initial", "development", "mid", "late"):
        ops = stage_operations(stage)
        assert ops, f"{stage} يجب أن تحوي عمليّات"
        for op in ops:
            _assert_valid_op(op)


def test_calendar_common_bean_four_stages_with_operations():
    cal = crop_operations_calendar("common_bean")
    assert cal["crop_id"] == "common_bean"
    assert cal["crop_family"] == "legume_C3"
    assert cal["source_ar"]
    assert len(cal["stages"]) == 4
    for st in cal["stages"]:
        assert st["operations"], f"المرحلة {st['stage']} يجب أن تحوي عمليّات"
        for op in st["operations"]:
            _assert_valid_op(op)


def test_calendar_mid_stage_has_protection_and_peak_irrigation():
    cal = crop_operations_calendar("common_bean")
    mid = next(st for st in cal["stages"] if st["stage"] == "mid")
    categories = {op["category"] for op in mid["operations"]}
    # الطور التكاثريّ: مسح/مكافحة آفات (IPM) + ريّ ذروة بلا إجهاد.
    assert "protection" in categories
    irrigation_ops = [op for op in mid["operations"] if op["category"] == "irrigation"]
    assert irrigation_ops
    text = " ".join(op["operation_ar"] + op["note_ar"] for op in irrigation_ops)
    assert ("ذروة" in text) or ("إجهاد" in text)


def test_calendar_crop_without_phenology_empty_stages():
    # cranberry بطاقة بلا كتلة phenology ⇒ مراحل فارغة (صدق، لا تلفيق).
    cal = crop_operations_calendar("cranberry")
    assert cal["stages"] == []


def test_calendar_unknown_crop_empty_stages():
    cal = crop_operations_calendar("__no_such_crop__")
    assert cal["stages"] == []
    assert cal["crop_family"] is None


def test_current_stage_operations_common_bean_mid_at_day_60():
    res = current_stage_operations("common_bean", 60)
    assert res["available"] is True
    assert res["stage"] == "mid"
    assert res["operations"]
    for op in res["operations"]:
        _assert_valid_op(op)


def test_current_stage_operations_unknown_unavailable():
    # عمر يتجاوز آخر مرحلة (دورة الفاصولياء 110 يوم) ⇒ غير متاح.
    assert current_stage_operations("common_bean", 999)["available"] is False
    # محصول مجهول ⇒ غير متاح.
    assert current_stage_operations("__no_such_crop__", 10)["available"] is False
    # عمر None ⇒ غير متاح.
    assert current_stage_operations("common_bean", None)["available"] is False


def test_family_nuance_legume_vs_cereal_differs():
    legume = stage_operations("development", "legume_C3")
    cereal = stage_operations("development", "cereal_C3")
    none = stage_operations("development", None)
    # كلّ غمزة تضيف عمليّة تسميد إضافيّة فوق الأساس.
    assert len(legume) == len(none) + 1
    assert len(cereal) == len(none) + 1
    legume_text = " ".join(op["operation_ar"] for op in legume)
    cereal_text = " ".join(op["operation_ar"] for op in cereal)
    # البقوليّة: خفض النيتروجين (تثبيت Rhizobium). الحبوب: تسميد تعلويّ عند التفريع.
    assert "Rhizobium" in legume_text or "خفض" in legume_text
    assert "top-dressing" in cereal_text or "تعلويّ" in cereal_text
    assert legume_text != cereal_text


def test_family_nuance_only_in_development_stage():
    # الغمزة محصورة بمرحلة النموّ الخضري فقط.
    assert stage_operations("mid", "legume_C3") == stage_operations("mid", None)
    assert stage_operations("initial", "cereal_C3") == stage_operations("initial", None)
