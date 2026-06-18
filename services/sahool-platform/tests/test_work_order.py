"""tests/test_work_order.py — اختبارات آلة حالات أمر العمل (نقيّة، وحدة)."""

import pytest
from core.work_order import (
    STATUSES,
    WO_TYPES,
    WorkOrder,
    can_transition,
    is_terminal,
    next_states,
    transition,
)

pytestmark = pytest.mark.unit


def test_legal_transitions_allowed():
    """الانتقالات الشرعيّة عبر دورة الحياة الكاملة مسموحة وتُعيد الحالة الصحيحة."""
    assert transition("planned", "assigned") == "assigned"
    assert transition("assigned", "in_progress") == "in_progress"
    assert transition("in_progress", "done") == "done"
    assert transition("done", "verified") == "verified"
    # إعادة عمل (rework): done → in_progress
    assert transition("done", "in_progress") == "in_progress"
    # الإلغاء مسموح من كلّ الحالات غير النهائيّة
    assert transition("planned", "cancelled") == "cancelled"
    assert transition("assigned", "cancelled") == "cancelled"
    assert transition("in_progress", "cancelled") == "cancelled"


def test_illegal_transition_skips_states_raises():
    """قفز الحالات (planned → done) ممنوع ويرفع ValueError برسالة عربيّة."""
    with pytest.raises(ValueError) as exc:
        transition("planned", "done")
    assert "غير مسموح" in str(exc.value)


def test_transition_from_terminal_raises():
    """أيّ انتقال من حالة نهائيّة (verified/cancelled) ممنوع."""
    with pytest.raises(ValueError):
        transition("verified", "in_progress")
    with pytest.raises(ValueError):
        transition("verified", "done")
    with pytest.raises(ValueError):
        transition("cancelled", "planned")


def test_unknown_status_raises():
    """الحالات المجهولة تُرفض في كلا الطرفين."""
    with pytest.raises(ValueError):
        transition("frozen", "assigned")
    with pytest.raises(ValueError):
        transition("planned", "teleported")


def test_is_terminal():
    """verified وcancelled نهائيّتان؛ البقيّة لا."""
    assert is_terminal("verified") is True
    assert is_terminal("cancelled") is True
    assert is_terminal("planned") is False
    assert is_terminal("assigned") is False
    assert is_terminal("in_progress") is False
    assert is_terminal("done") is False


def test_next_states():
    """next_states يُعيد مجموعة الحالات الجائزة، وفارغة للنهائيّة."""
    assert next_states("planned") == {"assigned", "cancelled"}
    assert next_states("done") == {"verified", "in_progress"}
    assert next_states("verified") == set()
    assert next_states("cancelled") == set()
    assert next_states("غير-موجود") == set()


def test_can_transition_matches_graph():
    """can_transition يطابق الرسم: يسمح بالشرعيّ ويمنع غيره دون رفع استثناء."""
    assert can_transition("planned", "assigned") is True
    assert can_transition("planned", "verified") is False
    assert can_transition("done", "in_progress") is True
    assert can_transition("cancelled", "planned") is False


def test_workorder_dataclass_and_with_status():
    """WorkOrder (frozen) يتحقّق من النوع/الحالة، وwith_status يُطبّق آلة الحالات."""
    assert "irrigation" in WO_TYPES
    assert "planned" in STATUSES

    wo = WorkOrder(
        id="wo-1",
        field_id="field-42",
        tenant_id="11111111-1111-1111-1111-111111111111",
        wo_type="irrigation",
        recommendation_id="rec-9",
    )
    assert wo.status == "planned"

    assigned = wo.with_status("assigned")
    assert assigned.status == "assigned"
    assert wo.status == "planned"  # الأصل لم يتغيّر (frozen)

    # انتقال غير مسموح عبر النسخة يرفع
    with pytest.raises(ValueError):
        wo.with_status("done")

    # نوع غير معروف يُرفض عند الإنشاء
    with pytest.raises(ValueError):
        WorkOrder(id="x", field_id="f", tenant_id="t", wo_type="dancing")
