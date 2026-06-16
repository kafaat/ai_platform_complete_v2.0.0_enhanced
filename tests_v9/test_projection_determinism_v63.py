"""
tests_v9/test_projection_determinism_v63.py — يُثبت إصلاح Projection Drift.

Pure logic فقط — لا DB. يتحقّق أنّ إعادة بناء الحالة حتميّة حتّى عند تصادم
occurred_at (نفس الطابع الزمنيّ لحدثين)، بفضل كاسر التعادل seq (v63).

قبل v63: الترتيب (occurred_at,) وحده → حدثان بنفس occurred_at ترتيبهما غير
حتميّ → إعادتا بناء مختلفتان من نفس الأحداث = Projection Drift.
بعد v63: الترتيب (occurred_at, seq, event_id) → حتميّ تماماً.
"""

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))


def _events_same_timestamp_out_of_order():
    """حدثان بنفس occurred_at بالضبط، مُمرَّران بترتيب seq معكوس.

    field.updated (seq=2) يجب أن يَغلِب field.created (seq=1) رغم تساوي الوقت.
    نُمرّرهما معكوسَين لإثبات أنّ الفرز يُصحّح الترتيب اعتماداً على seq.
    """
    ts = "2026-03-01T10:00:00.000000+00:00"
    return [
        {
            "event_type": "field.updated",
            "occurred_at": ts,
            "seq": 2,
            "event_id": "aaaa",  # UUID نصّيّ مبسّط للاختبار
            "payload": {"crop": "barley"},  # القيمة النهائيّة الصحيحة
        },
        {
            "event_type": "field.created",
            "occurred_at": ts,
            "seq": 1,
            "event_id": "zzzz",  # event_id أكبر معجميّاً — لو اعتُمد لانقلب الترتيب
            "payload": {"name_ar": "حقل", "area_ha": 1.0, "crop": "wheat"},
        },
    ]


def test_seq_breaks_timestamp_tie_deterministically():
    """seq يكسر تعادل occurred_at: الترتيب النهائيّ حتميّ ومستقلّ عن ترتيب الإدخال."""
    from api.event_replay import FieldStateReconstructor

    events = _events_same_timestamp_out_of_order()
    state = FieldStateReconstructor.reconstruct("field", "F1", events)

    # created (seq=1) يُطبَّق أوّلاً فيضع crop=wheat، ثمّ updated (seq=2) يضعه barley.
    # لو اعتُمد event_id وحده (قبل v63) لاختلّ الترتيب وصار crop=wheat خطأً.
    assert state.crop == "barley", f"الترتيب غير حتميّ: crop={state.crop}"
    assert state.area_ha == 1.0
    assert state.total_events == 2


def test_reconstruct_independent_of_input_order():
    """إعادة البناء تُعطي نفس النتيجة مهما كان ترتيب إدخال الأحداث (حتميّة)."""
    from api.event_replay import FieldStateReconstructor

    events = _events_same_timestamp_out_of_order()
    s1 = FieldStateReconstructor.reconstruct("field", "F1", list(events))
    s2 = FieldStateReconstructor.reconstruct("field", "F1", list(reversed(events)))

    # نفس النتيجة بغضّ النظر عن ترتيب الإدخال ⇒ لا Projection Drift.
    assert s1.crop == s2.crop == "barley"
    assert s1.area_ha == s2.area_ha


def test_snapshot_cursor_uses_seq_when_available():
    """SnapshotCursor.is_after يستعمل seq الحتميّ متى توفّر في الطرفين."""
    from api.event_replay import SnapshotCursor

    # مؤشّر عند (ts, seq=5). حدث بنفس ts و seq=6 ⇒ بعده. seq=4 ⇒ قبله.
    ts = "2026-03-01T10:00:00+00:00"
    cur = SnapshotCursor(last_event_id="x", last_occurred_at=ts, last_seq=5, total_events=1)
    assert cur.is_after({"occurred_at": ts, "seq": 6, "event_id": "a"}) is True
    assert cur.is_after({"occurred_at": ts, "seq": 4, "event_id": "z"}) is False


def test_snapshot_cursor_backward_compat_no_seq():
    """تراجُع متوافق رجعيّاً: لقطة قديمة (last_seq=None) تعتمد event_id كقبل v63."""
    from api.event_replay import SnapshotCursor

    ts = "2026-03-01T10:00:00+00:00"
    cur = SnapshotCursor(last_event_id="m", last_occurred_at=ts, last_seq=None, total_events=1)
    # بلا seq في المؤشّر → يسقط لمقارنة (occurred_at, event_id).
    assert cur.is_after({"occurred_at": ts, "event_id": "z"}) is True  # z > m
    assert cur.is_after({"occurred_at": ts, "event_id": "a"}) is False  # a < m


if __name__ == "__main__":
    test_seq_breaks_timestamp_tie_deterministically()
    test_reconstruct_independent_of_input_order()
    test_snapshot_cursor_uses_seq_when_available()
    test_snapshot_cursor_backward_compat_no_seq()
    print("✓ كل اختبارات الحتميّة (v63) نجحت")
