"""
tests_v9/test_event_replay_recovery_v66.py — تعافٍ/فشل لإعادة بناء الأحداث (A4).

Pure logic فقط — لا DB. يفحص سلوك التعافي الحقيقيّ لـ`api.event_replay`:
حمولات معطوبة/ناقصة، أنواع أحداث مجهولة، مجرى فارغ، ترتيب إدخال مختلط،
حدود `SnapshotCursor.is_after`، وتطابق إعادة البناء التزايديّة (snapshot+tail)
مع إعادة التشغيل الكاملة. لا يكرّر حتميّة seq في v63 — يوسّع لسيناريوهات أخرى.

الأسماء/التواقيع كلّها مُستخرَجة من الكود الفعليّ (apply_event يقرأ المفاتيح
event_type/payload/occurred_at مباشرةً؛ payload غير القاموس يُعامَل كـ{}).
"""

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from api.event_replay import (  # noqa: E402
    FieldStateReconstructor,
    ReconstructedState,
    SnapshotCursor,
)


def _ev(occurred_at, seq, etype, payload):
    """حدث بالشكل الذي يتوقّعه apply_event (event_type/occurred_at/seq/event_id/payload)."""
    return {
        "event_type": etype,
        "occurred_at": occurred_at,
        "seq": seq,
        "event_id": f"e{seq}",
        "payload": payload,
    }


def _sample_stream():
    """مجرى أحداث واقعيّ متنوّع (أنواع فعليّة يعالجها apply_event)."""
    return [
        _ev(
            "2026-01-01T00:00:00+00:00",
            1,
            "field.created",
            {"name_ar": "حقل", "area_ha": 2.0, "crop": "wheat"},
        ),
        _ev(
            "2026-01-02T00:00:00+00:00",
            2,
            "season.created",
            {"crops": ["barley"], "sowing_date": "2026-01-02"},
        ),
        _ev("2026-01-03T00:00:00+00:00", 3, "operation.irrigation.completed", {"water_m3": 10}),
        _ev(
            "2026-01-04T00:00:00+00:00",
            4,
            "alert.created",
            {"severity": "high", "alert_type": "pest", "field_id": "F"},
        ),
        _ev("2026-01-05T00:00:00+00:00", 5, "operation.irrigation.completed", {}),
    ]


# ── حمولات معطوبة/ناقصة ────────────────────────────────────────────


def test_none_payload_is_handled_safely():
    """payload=None ⇒ يُعامَل كقاموس فارغ؛ لا انهيار، الحقول الإسقاطيّة افتراضيّة."""
    state = ReconstructedState(entity_id="F", entity_type="field")
    out = FieldStateReconstructor.apply_event(
        state,
        {
            "event_type": "field.created",
            "payload": None,
            "occurred_at": "2026-01-01T00:00:00+00:00",
        },
    )
    # apply_event يحرس payload غير القاموس بـ{} → name/area يبقيان None، لكن العدّ يتمّ.
    assert out.total_events == 1
    assert out.field_name is None
    assert out.area_ha is None
    assert out.last_event_at == "2026-01-01T00:00:00+00:00"


def test_non_dict_payload_is_treated_as_empty():
    """payload نصّيّ معطوب (ليس dict) ⇒ يُعامَل كـ{} بأمان، لا استخراج حقول."""
    state = ReconstructedState(entity_id="F", entity_type="field")
    out = FieldStateReconstructor.apply_event(
        state, {"event_type": "field.created", "payload": "CORRUPTED", "occurred_at": "t"}
    )
    assert out.total_events == 1
    assert out.field_name is None


def test_field_created_with_partial_payload_keeps_defaults():
    """حمولة ناقصة (مفاتيح غائبة) ⇒ get يعيد None، لا انهيار."""
    state = ReconstructedState(entity_id="F", entity_type="field")
    out = FieldStateReconstructor.apply_event(
        state, _ev("t", 1, "field.created", {"name_ar": "حقل"})
    )
    assert out.field_name == "حقل"
    assert out.area_ha is None  # مفتاح area_ha غائب
    assert out.crop is None


# ── حدث بنوع غير معروف ─────────────────────────────────────────────


def test_unknown_event_type_only_counts():
    """نوع حدث مجهول ⇒ يُعدّ في total_events ويحدّث last_event_at فقط، بلا تغيير إسقاطيّ."""
    state = ReconstructedState(entity_id="F", entity_type="field")
    out = FieldStateReconstructor.apply_event(
        state, _ev("2026-02-02T00:00:00+00:00", 1, "totally.unknown.event", {"foo": "bar"})
    )
    assert out.total_events == 1
    assert out.last_event_at == "2026-02-02T00:00:00+00:00"
    # كل الحقول الإسقاطيّة بقيت على افتراضها.
    assert out.field_name is None
    assert out.lifecycle_stage is None
    assert out.irrigation_count == 0
    assert out.alert_count == 0


def test_unknown_event_does_not_disturb_known_projection():
    """خلط حدث مجهول وسط مجرى صحيح ⇒ لا يفسد الإسقاط، يزيد العدّ فقط."""
    events = _sample_stream()
    events.insert(2, _ev("2026-01-02T12:00:00+00:00", 99, "noise.event", {"junk": 1}))
    state = FieldStateReconstructor.reconstruct("field", "F", events)
    assert state.total_events == 6  # 5 صحيحة + 1 مجهول
    assert state.irrigation_count == 2  # لم يتأثّر
    assert state.alert_count == 1
    assert state.current_crop == "barley"


# ── مجرى أحداث فارغ ────────────────────────────────────────────────


def test_empty_stream_yields_clean_base_state():
    """مجرى فارغ ⇒ حالة أساسيّة سليمة بالهويّة الصحيحة وكل العدّادات صفر."""
    state = FieldStateReconstructor.reconstruct("field", "F1", [])
    assert state.entity_id == "F1"
    assert state.entity_type == "field"
    assert state.total_events == 0
    assert state.last_event_at is None
    assert state.lifecycle_stage is None
    assert state.irrigation_count == 0
    assert state.season_count == 0
    assert state.deleted is False


# ── ترتيب إدخال معكوس/مختلط ⇒ حتميّة ───────────────────────────────


def test_reconstruct_is_deterministic_under_shuffle():
    """ترتيب إدخال مختلف (معكوس/مبعثر) ⇒ نفس الحالة المُعاد بناؤها بالضبط."""
    import random

    events = _sample_stream()
    base = FieldStateReconstructor.reconstruct("field", "F", list(events))

    shuffled = list(events)
    random.Random(1234).shuffle(shuffled)
    s_shuf = FieldStateReconstructor.reconstruct("field", "F", shuffled)
    s_rev = FieldStateReconstructor.reconstruct("field", "F", list(reversed(events)))

    # المساواة الكاملة للـdataclass تثبت تطابق كل الحقول الإسقاطيّة (لا drift).
    assert base == s_shuf == s_rev


def test_reverse_order_preserves_last_event_at():
    """عكس الإدخال ⇒ last_event_at يبقى أحدث حدث (الفرز الزمنيّ يصلح الترتيب)."""
    events = _sample_stream()
    s_fwd = FieldStateReconstructor.reconstruct("field", "F", list(events))
    s_rev = FieldStateReconstructor.reconstruct("field", "F", list(reversed(events)))
    assert s_fwd.last_event_at == s_rev.last_event_at == "2026-01-05T00:00:00+00:00"


# ── حدود SnapshotCursor.is_after ───────────────────────────────────


def test_cursor_empty_is_after_everything():
    """مؤشّر فارغ (last_occurred_at=None) ⇒ كل حدث يُعدّ «بعده» (إعادة بناء كاملة)."""
    cur = SnapshotCursor(last_event_id=None, last_occurred_at=None, last_seq=None, total_events=0)
    assert cur.is_after({"occurred_at": "", "event_id": "a"}) is True
    assert (
        cur.is_after({"occurred_at": "2026-01-01T00:00:00+00:00", "seq": 1, "event_id": "z"})
        is True
    )


def test_cursor_not_after_itself():
    """المؤشّر لا «بعد» الحدث الذي يقف عنده بالضبط (occurred_at و seq متطابقان)."""
    ts = "2026-03-01T10:00:00+00:00"
    cur = SnapshotCursor(last_event_id="e3", last_occurred_at=ts, last_seq=3, total_events=1)
    assert cur.is_after({"occurred_at": ts, "seq": 3, "event_id": "e3"}) is False


def test_cursor_fallback_when_event_seq_missing():
    """seq غائب في الحدث ⇒ تراجُع متوافق إلى مقارنة (occurred_at, event_id) رغم وجود last_seq."""
    ts = "2026-03-01T10:00:00+00:00"
    cur = SnapshotCursor(last_event_id="m", last_occurred_at=ts, last_seq=5, total_events=1)
    # الحدث بلا seq → لا يُسلَك المسار الحتميّ، يُقارَن event_id معجميّاً.
    assert cur.is_after({"occurred_at": ts, "event_id": "z"}) is True  # z > m
    assert cur.is_after({"occurred_at": ts, "event_id": "a"}) is False  # a < m


def test_cursor_later_timestamp_is_after_regardless_of_seq():
    """طابع زمنيّ أحدث ⇒ «بعد» المؤشّر حتّى لو كان seq الحدث أصغر."""
    cur = SnapshotCursor(
        last_event_id="e9", last_occurred_at="2026-01-01T00:00:00+00:00", last_seq=9, total_events=1
    )
    assert (
        cur.is_after({"occurred_at": "2026-01-02T00:00:00+00:00", "seq": 1, "event_id": "a"})
        is True
    )


# ── إعادة البناء التزايديّة (snapshot + tail) == إعادة التشغيل الكاملة ──


def test_incremental_matches_full_replay():
    """لقطة عند k + إعادة تشغيل الباقي == إعادة التشغيل الكاملة (نفس الحالة تماماً)."""
    events = _sample_stream()
    full = FieldStateReconstructor.reconstruct("field", "F", events)

    head = events[:2]
    base = FieldStateReconstructor.reconstruct("field", "F", head)
    cursor = FieldStateReconstructor.cursor_of(base, head)
    # نمرّر المجرى الكامل؛ المؤشّر يتخطّى ما قبله ويطبّق الذيل فقط.
    incremental = FieldStateReconstructor.apply_incremental(base, events, cursor)

    assert incremental == full
    assert incremental.total_events == full.total_events == 5
    assert incremental.irrigation_count == 2


def test_incremental_with_empty_tail_equals_snapshot():
    """لا أحداث بعد المؤشّر (الذيل فارغ) ⇒ الحالة تبقى مطابقة للقطة الأساس."""
    events = _sample_stream()
    base = FieldStateReconstructor.reconstruct("field", "F", events)
    cursor = FieldStateReconstructor.cursor_of(base, events)
    # تمرير نفس المجرى كاملاً: كل حدث ليس «بعد» المؤشّر الأخير ⇒ لا تطبيق إضافيّ.
    out = FieldStateReconstructor.apply_incremental(base, events, cursor)
    assert out == base


def test_incremental_without_cursor_replays_all():
    """apply_incremental بلا مؤشّر (None) ⇒ يطبّق كل الأحداث = إعادة تشغيل كاملة."""
    events = _sample_stream()
    full = FieldStateReconstructor.reconstruct("field", "F", events)
    fresh = ReconstructedState(entity_id="F", entity_type="field")
    out = FieldStateReconstructor.apply_incremental(fresh, events, cursor=None)
    assert out == full


def test_cursor_of_empty_events_has_null_boundary():
    """cursor_of على مجرى فارغ ⇒ مؤشّر بلا حدّ (last_event_id=None) ⇒ is_after للجميع True."""
    base = ReconstructedState(entity_id="F", entity_type="field")
    cursor = FieldStateReconstructor.cursor_of(base, [])
    assert cursor.last_event_id is None
    assert cursor.last_seq is None
    assert (
        cursor.is_after({"occurred_at": "2026-01-01T00:00:00+00:00", "seq": 1, "event_id": "a"})
        is True
    )


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(pytest.main([__file__, "-q"]))
