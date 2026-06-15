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


# ─── إسقاطات إضافيّة (أحداث حقيقيّة من EventType، payload مؤكَّد من مواقع الإصدار) ─


def test_activity_recorded_counts_and_last_type():
    # حدث ACTIVITY_RECORDED الاحتياطيّ (field_aggregate.activity_event_for) — نشاط لا
    # يُطابَق operation.* محدَّداً. payload الحقيقيّ: {field_id, season_id, activity_type, status}.
    state = _apply(
        [
            _ev(
                "activity.recorded",
                "2026-01-01T00:00:00",
                "e1",
                {
                    "field_id": "F1",
                    "season_id": "s1",
                    "activity_type": "scouting",
                    "status": "done",
                },
            ),
            _ev(
                "activity.recorded",
                "2026-01-09T00:00:00",
                "e2",
                {
                    "field_id": "F1",
                    "season_id": None,
                    "activity_type": "weeding",
                    "status": "planned",
                },
            ),
        ]
    )
    assert state.activity_recorded_count == 2
    assert state.last_activity_type == "weeding"  # الأحدث


def test_trueup_applied_projects_latest_calibration():
    # payload الحقيقيّ من trueup.TrueUpEngine.
    state = _apply(
        [
            _ev(
                "trueup.applied",
                "2026-06-01T00:00:00",
                "e1",
                {
                    "operation_id": "op1",
                    "k_old": 1.0,
                    "k_new": 1.1,
                    "measured_yield_kg_ha": 5000,
                    "adjusted_yield_kg_ha": 5500,
                    "error_pct": 9.1,
                    "moisture_corrected": True,
                },
            ),
            _ev(
                "trueup.applied",
                "2026-06-10T00:00:00",
                "e2",
                {
                    "operation_id": "op2",
                    "k_old": 1.1,
                    "k_new": 1.05,
                    "measured_yield_kg_ha": 5200,
                    "adjusted_yield_kg_ha": 5300,
                    "error_pct": 2.0,
                    "moisture_corrected": False,
                },
            ),
        ]
    )
    assert state.trueup_count == 2
    assert state.last_trueup_error_pct == 2.0  # الأحدث
    assert state.last_adjusted_yield_kg_ha == 5300


def test_soil_lab_published_counter():
    # payload الحقيقيّ: {field_id} (routers/fields._update_soil_test عند النشر).
    state = _apply(
        [
            _ev("soil.sample.recorded", "2026-02-01T00:00:00", "e1", {"field_id": "F1"}),
            _ev("soil.lab.result.published", "2026-02-20T00:00:00", "e2", {"field_id": "F1"}),
        ]
    )
    assert state.soil_samples_count == 1
    assert state.soil_lab_published_count == 1


def test_valve_register_and_state_changed():
    # registered payload: {field_id, valve_type}؛ state_changed payload: {status}.
    state = _apply(
        [
            _ev(
                "irrigation.valve.registered",
                "2026-03-01T00:00:00",
                "e1",
                {"field_id": "F1", "valve_type": "solenoid"},
            ),
            _ev("irrigation.valve.state_changed", "2026-03-02T00:00:00", "e2", {"status": "open"}),
            _ev(
                "irrigation.valve.state_changed", "2026-03-03T00:00:00", "e3", {"status": "closed"}
            ),
        ]
    )
    assert state.valve_registered_count == 1
    assert state.valve_state_changed_count == 2
    assert state.last_valve_status == "closed"  # الأحدث


def test_irrigation_schedule_created_counter():
    # payload الحقيقيّ: {field_id, valve_id} (routers/irrigation.create_schedule).
    state = _apply(
        [
            _ev(
                "irrigation.schedule.created",
                "2026-03-10T00:00:00",
                "e1",
                {"field_id": "F1", "valve_id": "vlv_1"},
            ),
        ]
    )
    assert state.irrigation_schedule_count == 1


def test_crop_rotation_added_projects_last_crop():
    # payload الحقيقيّ: {field_id, crop} (routers/fields.add_crop_rotation).
    state = _apply(
        [
            _ev(
                "crop_rotation.added",
                "2026-01-01T00:00:00",
                "e1",
                {"field_id": "F1", "crop": "wheat"},
            ),
            _ev(
                "crop_rotation.added",
                "2026-07-01T00:00:00",
                "e2",
                {"field_id": "F1", "crop": "maize"},
            ),
        ]
    )
    assert state.crop_rotation_count == 2
    assert state.last_rotation_crop == "maize"  # الأحدث


def test_season_updated_counter():
    # payload الحقيقيّ: {field_id, changed_fields} (routers/fields._update_season).
    state = _apply(
        [
            _ev("season.created", "2026-01-01T00:00:00", "e1", {"crops": ["wheat"]}),
            _ev(
                "season.updated",
                "2026-02-01T00:00:00",
                "e2",
                {"field_id": "F1", "changed_fields": ["irrigation_type"]},
            ),
        ]
    )
    assert state.season_count == 1
    assert state.season_updated_count == 1
    # تحديث الموسم لا يُغيّر المحصول المُسقَط (لا اشتقاق زائف من حمولة لا تحمله).
    assert state.current_crop == "wheat"


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
            # إسقاطات إضافيّة (أحداث حقيقيّة) — لتغطية الحقول الجديدة في جولة اللقطة.
            _ev(
                "activity.recorded",
                "2026-04-10T00:00:00",
                "e6",
                {"field_id": "F1", "activity_type": "scouting", "status": "done"},
            ),
            _ev(
                "trueup.applied",
                "2026-04-15T00:00:00",
                "e7",
                {"k_new": 1.05, "adjusted_yield_kg_ha": 5300, "error_pct": 2.0},
            ),
            _ev("soil.lab.result.published", "2026-04-20T00:00:00", "e8", {"field_id": "F1"}),
            _ev(
                "irrigation.valve.registered",
                "2026-04-22T00:00:00",
                "e9",
                {"field_id": "F1", "valve_type": "solenoid"},
            ),
            _ev("irrigation.valve.state_changed", "2026-04-23T00:00:00", "e10", {"status": "open"}),
            _ev(
                "irrigation.schedule.created",
                "2026-04-24T00:00:00",
                "e11",
                {"field_id": "F1", "valve_id": "vlv_1"},
            ),
            _ev(
                "crop_rotation.added",
                "2026-04-25T00:00:00",
                "e12",
                {"field_id": "F1", "crop": "maize"},
            ),
            _ev(
                "season.updated",
                "2026-04-26T00:00:00",
                "e13",
                {"field_id": "F1", "changed_fields": ["irrigation_type"]},
            ),
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
        # أحداث الإسقاط الإضافيّة (حقيقيّة) — لتشمل التزايديّة الحقول الجديدة أيضاً.
        "activity.recorded",
        "trueup.applied",
        "soil.lab.result.published",
        "irrigation.valve.registered",
        "irrigation.valve.state_changed",
        "irrigation.schedule.created",
        "crop_rotation.added",
        "season.updated",
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
        if et == "activity.recorded":
            payload.update({"activity_type": "scouting", "status": "done"})
        if et == "trueup.applied":
            payload.update(
                {"k_new": 1.0 + i / 100, "adjusted_yield_kg_ha": 5000 + i, "error_pct": i}
            )
        if et == "irrigation.valve.registered":
            payload["valve_type"] = "solenoid"
        if et == "irrigation.valve.state_changed":
            payload["status"] = "open" if i % 2 == 0 else "closed"
        if et == "irrigation.schedule.created":
            payload["valve_id"] = "vlv_1"
        if et == "crop_rotation.added":
            payload["crop"] = "maize"
        if et == "season.updated":
            payload["changed_fields"] = ["irrigation_type"]
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
