"""اختبارات وحدة لرابط التوصية ⇐ أمر العمل (FOES slice 2) — نقيّ وحتميّ."""

from __future__ import annotations

import pytest
from core.work_order import STATUSES, WO_TYPES
from core.work_order_from_recommendation import (
    _infer_wo_type,
    recommendation_to_work_order,
    recommendations_to_work_orders,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        # إنجليزيّ
        ("irrigate the field", "irrigation"),
        ("apply fertilizer", "fertilization"),
        ("spray pesticide", "spraying"),
        ("scout for pests", "scouting"),
        ("inspect the crop", "scouting"),
        ("harvest now", "harvest"),
        # عربيّ
        ("ابدأ الريّ", "irrigation"),
        ("تسميد الحقل", "fertilization"),
        ("رشّ المبيد", "spraying"),
        ("فحص الإصابة", "scouting"),
        ("حصاد المحصول", "harvest"),
    ],
)
def test_infer_wo_type_english_and_arabic(action: str, expected: str) -> None:
    """استدلال النوع يعمل بالكلمات المفتاحيّة الإنجليزيّة والعربيّة معاً."""
    assert _infer_wo_type({"action": action}) == expected
    assert expected in WO_TYPES


def test_unknown_action_returns_none() -> None:
    """إجراء غير معروف ⇐ لا يُخترَع نوع، تُعاد None في الدالّتين."""
    rec = {"id": "r1", "action": "do something unrelated"}
    assert _infer_wo_type(rec) is None
    assert recommendation_to_work_order(rec, field_id="f1", tenant_id="t1") is None


def test_empty_recommendation_returns_none() -> None:
    """توصية بلا حقول إجراء ⇐ None."""
    assert _infer_wo_type({}) is None
    assert recommendation_to_work_order({}, field_id="f1", tenant_id="t1") is None


def test_produced_dict_shape_and_status() -> None:
    """القاموس المُنتَج: wo_type ضمن WO_TYPES، status=='planned'، والمعرّفات مضبوطة."""
    rec = {"id": "rec-42", "action": "irrigate", "reason_ar": "جفاف", "quantity": 30}
    wo = recommendation_to_work_order(rec, field_id="field-9", tenant_id="tenant-1")
    assert wo is not None
    assert wo["wo_type"] in WO_TYPES
    assert wo["status"] == "planned"
    assert wo["status"] in STATUSES
    assert wo["field_id"] == "field-9"
    assert wo["tenant_id"] == "tenant-1"
    assert wo["recommendation_id"] == "rec-42"
    assert wo["payload"] == {"reason_ar": "جفاف", "quantity": 30}


def test_recommendation_id_from_alternate_key() -> None:
    """يُلتقَط المعرّف من recommendation_id حين غياب id (ويُحوَّل إلى نصّ)."""
    rec = {"recommendation_id": 7, "kind": "تسميد"}
    wo = recommendation_to_work_order(rec, field_id="f1", tenant_id="t1")
    assert wo is not None
    assert wo["wo_type"] == "fertilization"
    assert wo["recommendation_id"] == "7"


def test_list_helper_drops_nones() -> None:
    """مساعد القائمة يُسقِط التوصيات التي تعذّر استنتاج نوعها."""
    recs = [
        {"id": "a", "action": "irrigate"},
        {"id": "b", "action": "unknown thing"},
        {"id": "c", "action": "حصاد"},
        {"id": "d"},  # بلا إجراء
    ]
    work_orders = recommendations_to_work_orders(recs, field_id="f1", tenant_id="t1")
    assert len(work_orders) == 2
    assert [w["wo_type"] for w in work_orders] == ["irrigation", "harvest"]
    assert all(w["status"] == "planned" for w in work_orders)
    assert all(w["wo_type"] in WO_TYPES for w in work_orders)
