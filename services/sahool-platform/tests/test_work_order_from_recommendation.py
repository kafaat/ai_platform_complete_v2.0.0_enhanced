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


# ── G3 (F-D06/F-D09): سلسلة المعرّفات توصية ⇐ قرار ⇐ أمر عمل ⇐ مهمّة ⇐ نتيجة ──


def test_decision_id_rides_on_the_work_order_payload() -> None:
    """معرّف القرار لا يسقط عند التحويل: يُحمَل في الحمولة بجوار recommendation_id."""
    rec = {"id": "rec-1", "decision_id": "dec_abc", "action": "irrigate"}
    wo = recommendation_to_work_order(rec, field_id="f1", tenant_id="t1")
    assert wo is not None
    assert wo["recommendation_id"] == "rec-1"
    assert wo["payload"]["decision_id"] == "dec_abc"


def test_field_task_draft_from_a_work_order_is_minimal_and_linked() -> None:
    """مسوّدة المهمّة تنقل النوع والحقل فقط (لا محتوى زراعيّ مُخترَع) وتُعلن مصدرها."""
    from core.work_order_from_recommendation import work_order_to_field_task

    wo = {"field_id": "f1", "wo_type": "irrigation", "status": "planned"}
    assert work_order_to_field_task(wo) == {
        "field_id": "f1",
        "task_type": "irrigation",
        "status": "pending",
        "source_event_type": "WORK_ORDER_CREATED",
        "source_agent": "work-order",
    }


@pytest.mark.parametrize("status", ["done", "verified", "cancelled"])
def test_no_field_task_draft_from_a_closed_work_order(status: str) -> None:
    from core.work_order_from_recommendation import work_order_to_field_task

    wo = {"field_id": "f1", "wo_type": "irrigation", "status": status}
    assert work_order_to_field_task(wo) is None


def test_outcome_needs_an_explicit_result_and_its_evidence() -> None:
    """إغلاقٌ إداريّ بلا نتيجة صريحة ودليلها ⇒ لا سجلّ؛ ومع كليهما ⇒ سجلّ منسوب غير مُتحقَّق."""
    from core.work_order_from_recommendation import build_work_order_outcome

    wo = {"recommendation_id": "rec-1", "payload": {"decision_id": "dec_1"}}

    def build(result, evidence_ref):
        return build_work_order_outcome(
            wo, task_id="t-1", result=result, evidence_ref=evidence_ref, recorded_by="u"
        )

    assert build(None, None) is None
    assert build("achieved", " ") is None
    assert build(None, "photo:1") is None
    assert build("achieved", "photo:1") == {
        "result": "achieved",
        "evidence_ref": "photo:1",
        "task_id": "t-1",
        "recommendation_id": "rec-1",
        "decision_id": "dec_1",
        "recorded_by": "u",
        "source": "task_close",
        "verified": False,
    }


def test_task_close_request_accepts_exactly_the_core_outcome_results() -> None:
    """نموذج الإغلاق يقبل قيم OUTCOME_RESULTS نفسها، والنتيجة ودليلها معاً مع الإنجاز فقط."""
    from typing import get_args

    from api.api_models import TaskUpdateRequest
    from core.work_order_from_recommendation import OUTCOME_RESULTS
    from pydantic import ValidationError

    annotation = TaskUpdateRequest.model_fields["outcome_result"].annotation
    literal = next(a for a in get_args(annotation) if a is not type(None))
    assert set(get_args(literal)) == set(OUTCOME_RESULTS)

    ok = TaskUpdateRequest(status="completed", outcome_result="achieved", outcome_evidence_ref="e")
    assert ok.outcome_evidence_ref == "e"
    for bad in (
        {"status": "completed", "outcome_result": "achieved"},
        {"status": "completed", "outcome_evidence_ref": "e"},
        {"status": "completed", "outcome_result": "achieved", "outcome_evidence_ref": "  "},
        {"status": "in_progress", "outcome_result": "achieved", "outcome_evidence_ref": "e"},
        {"status": "completed", "outcome_result": "verified", "outcome_evidence_ref": "e"},
    ):
        with pytest.raises(ValidationError):
            TaskUpdateRequest(**bad)
