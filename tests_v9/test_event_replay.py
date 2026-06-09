"""
tests_v9/test_event_replay.py — runtime tests for event replay logic.

Pure logic فقط — لا DB. الـDB tests منفصلة.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))


def test_state_reconstruction():
    """يتأكّد أنّ apply_event يبني state من events بترتيب صحيح."""
    from api.event_replay import FieldStateReconstructor, _summarize_ar

    results = []

    # حقل تمرّ عبر دورة كاملة
    events = [
        {
            "event_type": "field.created",
            "occurred_at": "2026-01-01T08:00:00+00:00",
            "payload": {"name_ar": "حقل القمح", "area_ha": 4.2, "crop": "wheat"},
        },
        {
            "event_type": "lifecycle.transitioned",
            "occurred_at": "2026-01-15T07:00:00+00:00",
            "payload": {"from_stage": "CREATED", "to_stage": "PREPARED"},
        },
        {
            "event_type": "lifecycle.transitioned",
            "occurred_at": "2026-02-01T06:30:00+00:00",
            "payload": {"to_stage": "PLANTED"},
        },
        {
            "event_type": "operation.irrigation.completed",
            "occurred_at": "2026-02-05T18:00:00+00:00",
            "payload": {"water_m3": 320},
        },
        {
            "event_type": "operation.irrigation.completed",
            "occurred_at": "2026-02-12T18:00:00+00:00",
            "payload": {"water_m3": 280},
        },
        {
            "event_type": "operation.fertilizer.applied",
            "occurred_at": "2026-02-18T07:00:00+00:00",
            "payload": {"nitrogen_kg": 60, "phosphorus_kg": 20},
        },
        {
            "event_type": "remote_sensing.ndvi.observed",
            "occurred_at": "2026-03-01T10:00:00+00:00",
            "payload": {"ndvi_mean": 0.68},
        },
        {
            "event_type": "lifecycle.transitioned",
            "occurred_at": "2026-05-15T06:00:00+00:00",
            "payload": {"to_stage": "HARVESTED"},
        },
    ]

    state = FieldStateReconstructor.reconstruct("field", "fld-test", events)

    if state.field_name == "حقل القمح":
        results.append(("✓", f"field_name reconstructed: {state.field_name}"))
    else:
        results.append(("✗", f"name wrong: {state.field_name}"))

    if state.area_ha == 4.2:
        results.append(("✓", f"area: {state.area_ha}"))
    else:
        results.append(("✗", f"area: {state.area_ha}"))

    if state.crop == "wheat":
        results.append(("✓", f"crop: {state.crop}"))

    if state.lifecycle_stage == "HARVESTED":
        results.append(("✓", f"final stage: {state.lifecycle_stage}"))
    else:
        results.append(("✗", f"stage: {state.lifecycle_stage}"))

    if state.irrigation_count == 2:
        results.append(("✓", f"irrigation count: {state.irrigation_count}"))
    else:
        results.append(("✗", f"irrigation: {state.irrigation_count}"))

    if state.fertilizer_count == 1:
        results.append(("✓", f"fertilizer count: {state.fertilizer_count}"))

    if state.last_ndvi == 0.68:
        results.append(("✓", f"last NDVI: {state.last_ndvi}"))

    if state.planting_date and "2026-02-01" in state.planting_date:
        results.append(("✓", "planting date set on PLANTED transition"))

    if state.harvest_date and "2026-05-15" in state.harvest_date:
        results.append(("✓", "harvest date set on HARVESTED transition"))

    if state.total_events == 8:
        results.append(("✓", f"total events: {state.total_events}"))
    else:
        results.append(("✗", f"total events: {state.total_events}"))

    return results


def test_event_ordering():
    """events بترتيب عكسي يجب أن تُرتَّب أوّلاً ثمّ تُطبَّق."""
    from api.event_replay import FieldStateReconstructor

    results = []

    # Events بترتيب عكسي عمداً
    events_reversed = [
        {
            "event_type": "lifecycle.transitioned",
            "occurred_at": "2026-05-01T06:00:00+00:00",
            "payload": {"to_stage": "HARVESTED"},
        },
        {
            "event_type": "field.created",
            "occurred_at": "2026-01-01T08:00:00+00:00",
            "payload": {"name_ar": "حقل", "area_ha": 2.0},
        },
    ]

    state = FieldStateReconstructor.reconstruct("field", "fld", events_reversed)

    # رغم الترتيب العكسي في الإدخال، النتيجة يجب أن تكون صحيحة
    if state.field_name == "حقل":
        results.append(("✓", "events sorted by occurred_at before apply"))
    if state.lifecycle_stage == "HARVESTED":
        results.append(("✓", "final state correct after sort"))

    return results


def test_arabic_summaries():
    """تحقّق أنّ ملخّصات العربيّة تعمل."""
    from api.event_replay import _summarize_ar

    results = []

    cases = [
        ("field.created", {}, "أُنشئ الحقل"),
        ("lifecycle.transitioned", {"to_stage": "PLANTED"}, "زُرع"),
        ("lifecycle.transitioned", {"to_stage": "HARVESTED"}, "حُصِد"),
        ("operation.irrigation.completed", {"water_m3": 350}, "350 م³"),
        ("operation.fertilizer.applied", {"nitrogen_kg": 80, "phosphorus_kg": 40}, "N=80"),
        ("remote_sensing.ndvi.observed", {"ndvi_mean": 0.72}, "NDVI=0.72"),
    ]

    for etype, payload, expected_substring in cases:
        summary = _summarize_ar(etype, payload)
        if expected_substring in summary:
            results.append(("✓", f"{etype}: '{summary}'"))
        else:
            results.append(("✗", f"{etype}: expected '{expected_substring}' in '{summary}'"))

    return results


def test_event_types_catalog():
    """تحقّق أنّ الـEventType enum مكتمل ولا duplicates."""
    from api.event_bus import EventSource, EventType

    results = []

    values = [e.value for e in EventType]
    if len(values) == len(set(values)):
        results.append(("✓", f"EventType has {len(values)} unique types"))
    else:
        results.append(("✗", "EventType has duplicates"))

    # تحقّق أنّ كل event مُغطّى في _EVENT_SUMMARY_AR
    from api.event_replay import _EVENT_SUMMARY_AR

    missing = [e.value for e in EventType if e.value not in _EVENT_SUMMARY_AR]
    if not missing:
        results.append(("✓", "all EventTypes have Arabic summaries"))
    else:
        results.append(("✗", f"missing summaries: {missing}"))

    # EventSources count
    sources = [s.value for s in EventSource]
    if len(sources) == 7:
        results.append(("✓", f"EventSource has 7 values: {sources}"))

    return results


def run_all():
    print("=" * 60)
    print("  Event Replay + Bus — runtime tests")
    print("=" * 60)

    suites = [
        ("State Reconstruction", test_state_reconstruction),
        ("Event Ordering (sort)", test_event_ordering),
        ("Arabic Summaries", test_arabic_summaries),
        ("Event Types Catalog", test_event_types_catalog),
    ]

    tp = 0
    tf = 0
    for name, suite in suites:
        print(f"\n── {name} ──")
        try:
            for status, msg in suite():
                print(f"  {status} {msg}")
                if status == "✓":
                    tp += 1
                else:
                    tf += 1
        except Exception as e:
            print(f"  ✗ CRASHED: {type(e).__name__}: {e}")
            tf += 1

    print(f"\n{'=' * 60}")
    print(f"  Passed: {tp}/{tp + tf}")
    print(f"{'=' * 60}")
    return tp, tf


if __name__ == "__main__":
    p, f = run_all()
    sys.exit(0 if f == 0 else 1)
