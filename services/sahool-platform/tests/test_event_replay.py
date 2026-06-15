"""اختبارات Event Replay (offline، نقيّة) — تغطية الإسقاط + استراتيجيّة اللقطة.

يتحقّق من:
  • حالات apply_event الجديدة (أحداث operation.*.started/completed، season.*،
    alert.created، field.state_changed، field.deleted) — أحداث حقيقيّة من EventType
    بمفاتيح payload مؤكَّدة من مواقع الإصدار (field_aggregate / main / event_catalog).
  • جولة ذهاب-إياب للقطة: to_snapshot_dict → from_snapshot == الأصل.
  • التزايديّة == إعادة التشغيل الكاملة: لقطة-عند-k + إعادة تشغيل الباقي == بناء
    كامل لكلّ الأحداث (المؤشّر الحتميّ يضمن التطابق).

لا قاعدة بيانات للأجزاء النقيّة (apply_event / serialization صرفة).
"""

from __future__ import annotations

from api.event_replay import (
    FieldStateReconstructor,
    ReconstructedState,
    SnapshotCursor,
)


def _ev(event_type, occurred_at, event_id, payload=None, seq=None):
    """مولّد قاموس حدث بالشكل الذي يعيده bus.query_entity_history."""
    d = {
        "event_type": event_type,
        "occurred_at": occurred_at,
        "event_id": event_id,
        "payload": payload or {},
    }
    if seq is not None:
        d["seq"] = seq
    return d


def _apply(events):
    """يبني state بإعادة تشغيل كاملة لقائمة أحداث."""
    return FieldStateReconstructor.reconstruct("field", "F1", events)


# ─── Task 1: حالات apply_event الجديدة ──────────────────────────────


def test_planting_started_and_completed():
    state = _apply(
        [
            _ev("operation.planting.started", "2026-01-01T00:00:00", "e1", {"field_id": "F1"}),
            _ev("operation.planting.completed", "2026-01-05T00:00:00", "e2", {"field_id": "F1"}),
        ]
    )
    assert state.planting_started_count == 1
    assert state.planting_completed_count == 1
    # إكمال البذر يُثبت تاريخ الزراعة من زمن الحدث (لا مفتاح تاريخ في payload الحقيقيّ).
    assert state.planting_date == "2026-01-05T00:00:00"


def test_irrigation_started_separate_from_completed():
    state = _apply(
        [
            _ev("operation.irrigation.started", "2026-02-01T00:00:00", "e1"),
            _ev("operation.irrigation.completed", "2026-02-01T06:00:00", "e2"),
            _ev("operation.irrigation.completed", "2026-02-08T06:00:00", "e3"),
        ]
    )
    assert state.irrigation_started_count == 1
    assert state.irrigation_count == 2  # العدّاد القائم لـcompleted


def test_harvest_started_and_completed():
    state = _apply(
        [
            _ev("operation.harvest.started", "2026-06-01T00:00:00", "e1"),
            _ev("operation.harvest.completed", "2026-06-03T00:00:00", "e2"),
        ]
    )
    assert state.harvest_started_count == 1
    assert state.harvest_completed_count == 1
    assert state.harvest_date == "2026-06-03T00:00:00"


def test_season_created_projects_crop_and_sowing():
    state = _apply(
        [
            _ev(
                "season.created",
                "2026-01-01T00:00:00",
                "e1",
                {
                    "field_id": "F1",
                    "crops": ["wheat", "barley"],
                    "cultivar": "saber",
                    "irrigation_type": "drip",
                    "sowing_date": "2026-01-02",
                },
            ),
        ]
    )
    assert state.season_count == 1
    assert state.current_crop == "wheat"  # أوّل محصول في القائمة
    assert state.last_sowing_date == "2026-01-02"


def test_season_created_crops_as_string():
    state = _apply([_ev("season.created", "2026-01-01T00:00:00", "e1", {"crops": "maize"})])
    assert state.current_crop == "maize"


def test_season_closed_counts():
    state = _apply(
        [
            _ev("season.created", "2026-01-01T00:00:00", "e1", {"crops": ["wheat"]}),
            _ev("season.closed", "2026-06-01T00:00:00", "e2", {"field_id": "F1"}),
        ]
    )
    assert state.season_count == 1
    assert state.season_closed_count == 1


def test_alert_created_projects_latest():
    state = _apply(
        [
            _ev(
                "alert.created",
                "2026-03-01T00:00:00",
                "e1",
                {"severity": "low", "alert_type": "moisture", "field_id": "F1"},
            ),
            _ev(
                "alert.created",
                "2026-03-05T00:00:00",
                "e2",
                {"severity": "high", "alert_type": "pest", "field_id": "F1"},
            ),
        ]
    )
    assert state.alert_count == 2
    assert state.last_alert_severity == "high"  # الأحدث
    assert state.last_alert_type == "pest"


def test_field_state_changed_projects_validity_and_mode():
    state = _apply(
        [
            _ev(
                "field.state_changed",
                "2026-04-01T00:00:00",
                "e1",
                {"validity": "valid", "execution_mode": "auto", "trigger": "activity.recorded"},
            ),
        ]
    )
    assert state.validity == "valid"
    assert state.execution_mode == "auto"


def test_field_deleted_sets_flag():
    state = _apply(
        [
            _ev("field.created", "2026-01-01T00:00:00", "e1", {"name": "حقل", "crop": "wheat"}),
            _ev("field.deleted", "2026-12-01T00:00:00", "e2", {"name": "حقل", "crop": "wheat"}),
        ]
    )
    assert state.deleted is True


def test_unknown_event_only_increments_total():
    state = _apply(
        [
            _ev("some.unmodeled.event", "2026-01-01T00:00:00", "e1", {"x": 1}),
        ]
    )
    assert state.total_events == 1
    # لا حقول إسقاط تغيّرت
    assert state.season_count == 0
    assert state.alert_count == 0


# ─── Task 2: جولة ذهاب-إياب للقطة (serialization نقيّة) ──────────────


def _rich_state():
    """state بحقول إسقاط متنوّعة لاختبار التسلسل."""
    return _apply(
        [
            _ev(
                "field.created",
                "2026-01-01T00:00:00",
                "e1",
                {"name_ar": "حقلي", "area_ha": 12.5, "crop": "wheat"},
            ),
            _ev(
                "season.created",
                "2026-01-02T00:00:00",
                "e2",
                {"crops": ["wheat"], "sowing_date": "2026-01-03"},
            ),
            _ev("operation.irrigation.completed", "2026-02-01T00:00:00", "e3"),
            _ev(
                "alert.created",
                "2026-03-01T00:00:00",
                "e4",
                {"severity": "high", "alert_type": "pest"},
            ),
            _ev("remote_sensing.ndvi.observed", "2026-04-01T00:00:00", "e5", {"ndvi_mean": 0.71}),
        ]
    )


def test_snapshot_roundtrip_equals_original():
    original = _rich_state()
    snap = original.to_snapshot_dict()
    # entity_id/entity_type لا يُخزَّنان في state JSONB (يُخزَّنان كأعمدة).
    assert "entity_id" not in snap
    assert "entity_type" not in snap

    row = {"entity_type": original.entity_type, "entity_id": original.entity_id, "state": snap}
    rebuilt = ReconstructedState.from_snapshot(row)
    assert rebuilt == original


def test_snapshot_roundtrip_accepts_json_string_state():
    import json

    original = _rich_state()
    row = {
        "entity_type": original.entity_type,
        "entity_id": original.entity_id,
        "state": json.dumps(original.to_snapshot_dict()),
    }
    rebuilt = ReconstructedState.from_snapshot(row)
    assert rebuilt == original


def test_from_snapshot_ignores_unknown_keys():
    original = _rich_state()
    snap = original.to_snapshot_dict()
    snap["a_future_field_not_in_dataclass"] = "ignored"
    row = {"entity_type": "field", "entity_id": "F1", "state": snap}
    rebuilt = ReconstructedState.from_snapshot(row)
    assert rebuilt == original  # المفتاح المجهول يُتجاهَل


# ─── Task 2: التزايديّة == إعادة التشغيل الكاملة ────────────────────


def _stream(n=12):
    """مجرى أحداث حتميّ مختلط (أنواع متعدّدة) بمعرّفات/أوقات صاعدة."""
    types = [
        "field.created",
        "season.created",
        "operation.planting.started",
        "operation.planting.completed",
        "operation.irrigation.completed",
        "operation.fertilizer.applied",
        "alert.created",
        "remote_sensing.ndvi.observed",
        "operation.harvest.completed",
        "season.closed",
    ]
    events = []
    for i in range(n):
        et = types[i % len(types)]
        payload = {"field_id": "F1"}
        if et == "season.created":
            payload["crops"] = ["wheat"]
        if et == "alert.created":
            payload.update({"severity": "low", "alert_type": "moisture"})
        if et == "remote_sensing.ndvi.observed":
            payload["ndvi_mean"] = 0.5 + i / 100
        events.append(_ev(et, f"2026-01-{i + 1:02d}T00:00:00", f"e{i:02d}", payload))
    return events


def test_incremental_equals_full_replay():
    events = _stream(12)
    full = FieldStateReconstructor.reconstruct("field", "F1", events)

    for k in range(0, len(events) + 1):
        head = events[:k]
        snap_state = FieldStateReconstructor.reconstruct("field", "F1", head)
        cursor = FieldStateReconstructor.cursor_of(snap_state, head)

        # محاكاة جولة اللقطة: سلسِل state ثمّ أعِد بناءها (كما يحدث عبر القاعدة).
        row = {
            "entity_type": "field",
            "entity_id": "F1",
            "state": snap_state.to_snapshot_dict(),
        }
        base = ReconstructedState.from_snapshot(row)

        # apply_incremental على كامل المجرى مع المؤشّر يساوي full replay.
        result = FieldStateReconstructor.apply_incremental(base, events, cursor)
        assert result == full, f"عدم تطابق عند k={k}"


def test_apply_incremental_no_cursor_is_full_replay():
    events = _stream(8)
    full = FieldStateReconstructor.reconstruct("field", "F1", events)
    base = ReconstructedState(entity_id="F1", entity_type="field")
    result = FieldStateReconstructor.apply_incremental(base, events, cursor=None)
    assert result == full


def test_cursor_is_after_semantics():
    events = _stream(5)
    state = _apply(events)
    cursor = FieldStateReconstructor.cursor_of(state, events)
    # لا حدث في المجرى الأصليّ «بعد» المؤشّر.
    assert all(not cursor.is_after(e) for e in events)
    # حدث لاحق (وقت أكبر) يقع بعد المؤشّر.
    later = _ev("alert.created", "2026-12-31T00:00:00", "zzz", {"severity": "low"})
    assert cursor.is_after(later)


def test_empty_cursor_after_everything():
    cursor = SnapshotCursor(
        last_event_id=None, last_occurred_at=None, last_seq=None, total_events=0
    )
    assert cursor.is_after(_ev("field.created", "2020-01-01T00:00:00", "e1"))
