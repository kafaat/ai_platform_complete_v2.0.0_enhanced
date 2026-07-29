"""
tests_v9/test_v10_modules.py — Runtime tests للوحدات الجديدة

١. Lifecycle state machine logic (in-memory)
٢. Prescriptions generator
٣. Yield heuristics
٤. CSV reports

ملاحظة: command_store + field_lifecycle (الـDB layer) يحتاجان PostgreSQL.
        هذه الاختبارات تركّز على الـpure logic بدون DB.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

import asyncio

import pytest

pytestmark = pytest.mark.unit


# Avoid asyncpg dependency at import time
def test_lifecycle_state_machine():
    """تحقّق من valid + invalid transitions logic."""
    # نمرّر import المحلّي لتفادي asyncpg
    from api.field_lifecycle import (
        VALID_TRANSITIONS,
        LifecycleStage,
        is_valid_transition,
    )

    results = []

    # Valid sequences
    valid_cases = [
        (LifecycleStage.CREATED, LifecycleStage.PREPARED),
        (LifecycleStage.PREPARED, LifecycleStage.PLANTED),
        (LifecycleStage.PLANTED, LifecycleStage.GROWING),
        (LifecycleStage.GROWING, LifecycleStage.MATURE),
        (LifecycleStage.MATURE, LifecycleStage.HARVESTED),
        (LifecycleStage.HARVESTED, LifecycleStage.POST_HARVEST),
        (LifecycleStage.POST_HARVEST, LifecycleStage.PREPARED),  # new season
    ]

    for from_s, to_s in valid_cases:
        if is_valid_transition(from_s, to_s):
            results.append(("✓", f"valid: {from_s.value} → {to_s.value}"))
        else:
            results.append(("✗", f"FALSE NEG: {from_s.value} → {to_s.value}"))

    # Invalid sequences (these should ALL be rejected)
    invalid_cases = [
        (LifecycleStage.CREATED, LifecycleStage.HARVESTED),  # skipping stages
        (LifecycleStage.CREATED, LifecycleStage.PLANTED),  # must go via PREPARED
        (LifecycleStage.HARVESTED, LifecycleStage.PLANTED),  # can't replant directly
        (LifecycleStage.PLANTED, LifecycleStage.HARVESTED),  # missing growth phases
        (LifecycleStage.GROWING, LifecycleStage.HARVESTED),  # not mature yet
        (LifecycleStage.MATURE, LifecycleStage.PREPARED),  # backwards
        (LifecycleStage.HARVESTED, LifecycleStage.MATURE),  # backwards
    ]

    for from_s, to_s in invalid_cases:
        if not is_valid_transition(from_s, to_s):
            results.append(("✓", f"rejected: {from_s.value} → {to_s.value}"))
        else:
            results.append(("✗", f"FALSE POS: {from_s.value} → {to_s.value}"))

    # Same-stage (rejected)
    for stage in LifecycleStage:
        if not is_valid_transition(stage, stage):
            pass  # expected
        else:
            results.append(("✗", f"FALSE POS: {stage.value} → {stage.value}"))

    return results


def test_prescriptions():
    """N + Seeding prescriptions."""
    from api.prescriptions import (
        PrescriptionGenerator,
        PrescriptionType,
        ZoneCharacteristics,
        ZoneClass,
        prescription_to_csv,
        prescription_to_dict,
    )

    results = []
    gen = PrescriptionGenerator()

    # Wheat field with 3 zones
    zones = [
        ZoneCharacteristics(
            zone_id="z1",
            zone_class=ZoneClass.HIGH,
            area_ha=1.5,
            ndvi_mean=0.72,
            soil_ph=7.4,
            soil_om=2.5,
            soil_n_ppm=18,
            soil_texture="loamy",
            soil_depth_cm=50,
        ),
        ZoneCharacteristics(
            zone_id="z2",
            zone_class=ZoneClass.MEDIUM,
            area_ha=1.8,
            ndvi_mean=0.52,
            soil_ph=7.8,
            soil_om=1.5,
            soil_n_ppm=10,
            soil_texture="loamy",
            soil_depth_cm=45,
        ),
        ZoneCharacteristics(
            zone_id="z3",
            zone_class=ZoneClass.PROBLEM,
            area_ha=0.9,
            ndvi_mean=0.35,
            soil_ph=8.2,
            soil_ec=5.2,
            soil_n_ppm=8,
            soil_texture="sandy",
            soil_depth_cm=30,
        ),
    ]

    rx = gen.generate_nitrogen(
        field_id="fld-test",
        season_id="seas-1",
        crop="wheat",
        zones=zones,
    )

    # ١. كل zone لها prescription
    if len(rx.zones) == 3:
        results.append(("✓", "N prescription: 3 zones"))
    else:
        results.append(("✗", f"expected 3 zones, got {len(rx.zones)}"))

    # ٢. الـPROBLEM zone (ملوحة عالية) يجب أن تحصل على rate أقلّ
    high_rate = next(z for z in rx.zones if z.zone_id == "z1").rate
    problem_rate = next(z for z in rx.zones if z.zone_id == "z3").rate
    if problem_rate < high_rate:
        results.append(("✓", f"problem zone got lower rate ({problem_rate} < {high_rate})"))
    else:
        results.append(("✗", f"problem zone should be lower: {problem_rate} vs {high_rate}"))

    # ٣. الـsandy soil يحصل على warning
    sandy_zone = next(z for z in rx.zones if z.zone_id == "z3")
    has_split_warning = any("قسّم الجرعة" in w for w in sandy_zone.warnings)
    if has_split_warning:
        results.append(("✓", "sandy soil → split application warning"))
    else:
        results.append(("✗", "sandy soil should have split warning"))

    # ٤. الـconfidence أعلى لما lab data متوفّرة
    z1 = next(z for z in rx.zones if z.zone_id == "z1")
    if z1.confidence >= 0.85:
        results.append(("✓", f"lab data → high confidence ({z1.confidence})"))
    else:
        results.append(("✗", f"confidence should be ≥0.85 with lab: {z1.confidence}"))

    # ٥. CSV export يعمل
    csv_str = prescription_to_csv(rx)
    if "zone_id,rate,unit" in csv_str and "fld-test" in csv_str:
        results.append(("✓", "CSV export works"))
    else:
        results.append(("✗", "CSV export malformed"))

    # ٦. Unknown crop → ValueError
    try:
        gen.generate_nitrogen("fld", "s", "moon_potato", zones)
        results.append(("✗", "should reject unknown crop"))
    except ValueError:
        results.append(("✓", "unknown crop rejected"))

    # ٧. Seeding prescription
    seed_rx = gen.generate_seeding(
        field_id="fld-test",
        season_id="s",
        crop="wheat",
        zones=zones,
    )
    if seed_rx.prescription_type == PrescriptionType.SEED:
        results.append(("✓", "seeding prescription generated"))

    return results


def test_yield_heuristics():
    """Yield estimation + anomalies."""
    from api.yield_heuristics import (
        LifecycleFeatures,
        StressLevel,
        build_features_from_events,
        detect_anomalies,
        estimate_yield,
    )

    results = []

    # حقل صحّي (no stress)
    healthy = LifecycleFeatures(
        field_id="fld-1",
        crop="wheat",
        days_in_growing=90,
        irrigation_count=8,
        moisture_stress_events=0,
        pest_alerts=0,
        avg_ndvi_growing=0.70,
        drought_streak_days=3,
    )
    est = estimate_yield(healthy)
    if est.yield_score >= 0.95 and est.stress_level == StressLevel.NONE:
        results.append(("✓", f"healthy field: yield_score={est.yield_score}, stress=none"))
    else:
        results.append(("✗", f"healthy expected ≥0.95, got {est.yield_score} / {est.stress_level}"))

    # حقل مُجهَد
    stressed = LifecycleFeatures(
        field_id="fld-2",
        crop="wheat",
        days_in_growing=85,
        irrigation_count=3,
        moisture_stress_events=7,
        pest_alerts=2,
        avg_ndvi_growing=0.42,
        drought_streak_days=18,
    )
    est_s = estimate_yield(stressed)
    if est_s.yield_score < 0.70 and est_s.stress_level in (StressLevel.HIGH, StressLevel.CRITICAL):
        results.append(
            (
                "✓",
                f"stressed field: yield_score={est_s.yield_score}, stress={est_s.stress_level.value}",
            )
        )
    else:
        results.append(
            (
                "✗",
                f"stressed expected <0.70/high, got {est_s.yield_score}/{est_s.stress_level.value}",
            )
        )

    # Confidence calculation
    if 0.5 <= est_s.confidence <= 0.92:
        results.append(("✓", f"confidence bounded: {est_s.confidence}"))
    else:
        results.append(("✗", f"confidence out of bounds: {est_s.confidence}"))

    # Anomaly detection
    anomalies = detect_anomalies(stressed)
    if any(a.type == "water_stress_chronic" for a in anomalies):
        results.append(("✓", "detected chronic water stress"))
    else:
        results.append(("✗", "should detect chronic water stress"))
    if any(a.type == "drought_streak" for a in anomalies):
        results.append(("✓", "detected drought streak"))
    else:
        results.append(("✗", "should detect drought streak"))

    # Unknown crop → graceful
    unknown = LifecycleFeatures(field_id="fld", crop="zucchini_xenoplasm")
    est_u = estimate_yield(unknown)
    if est_u.estimated_yield_kg_ha == 0 and "غير معروف" in est_u.rationale_ar:
        results.append(("✓", "unknown crop → graceful zero"))
    else:
        results.append(("✗", "unknown crop should return zero"))

    # Build features from events
    events = [
        {
            "event_type": "lifecycle.transition",
            "timestamp": "2026-02-01T00:00:00+00:00",
            "payload": {"to_stage": "GROWING"},
        },
        {"event_type": "operation.irrigation.completed", "timestamp": "2026-02-05T00:00:00+00:00"},
        {"event_type": "operation.irrigation.completed", "timestamp": "2026-02-12T00:00:00+00:00"},
        {"event_type": "weather.moisture.low", "timestamp": "2026-02-25T00:00:00+00:00"},
        {
            "event_type": "lifecycle.transition",
            "timestamp": "2026-05-01T00:00:00+00:00",
            "payload": {"to_stage": "MATURE"},
        },
    ]
    f = build_features_from_events("fld", "wheat", events)
    if f.irrigation_count == 2 and f.moisture_stress_events == 1 and f.days_in_growing > 85:
        results.append(("✓", f"features from events: irr=2, stress=1, days={f.days_in_growing}"))
    else:
        results.append(
            (
                "✗",
                f"feature extraction: irr={f.irrigation_count}, stress={f.moisture_stress_events}, days={f.days_in_growing}",
            )
        )

    return results


def test_reports_csv():
    """CSV report generation."""
    from api.reports import FieldReport, OperationReport, operation_to_csv

    results = []

    fields = [
        FieldReport(
            field_id="fld-1",
            field_name_ar="حقل الشمال",
            farm_id="frm-1",
            tenant_id="ten-1",
            area_ha=4.2,
            crop="wheat",
            season_label="شتاء 2026",
            planting_date="2026-02-15",
            harvest_date=None,
            lifecycle_stage="GROWING",
            irrigation_events=5,
            total_water_m3=420.0,
            fertilizer_events=2,
            total_nitrogen_kg=80.0,
            avg_ndvi=0.68,
            estimated_yield_kg_ha=2400,
            estimated_yield_total_kg=10080,
            soil_samples_count=2,
            last_soil_ph=7.4,
            anomalies=["تنبيه ري"],
        ),
        FieldReport(
            field_id="fld-2",
            field_name_ar="قطاع المحور",
            farm_id="frm-1",
            tenant_id="ten-1",
            area_ha=2.8,
            crop="corn",
            season_label="شتاء 2026",
            planting_date="2026-03-01",
            harvest_date=None,
            lifecycle_stage="PLANTED",
            irrigation_events=2,
            total_water_m3=180.0,
        ),
    ]

    report = OperationReport(
        tenant_id="ten-1",
        operation_name_ar="مزرعة الأمل",
        fields=fields,
        period_start="2026-02-01",
        period_end="2026-05-31",
        generated_at="2026-06-03T12:00:00Z",
    )

    csv_str = operation_to_csv(report, lang="ar")

    # Checks
    if "field_id" in csv_str and "اسم_الحقل" in csv_str:
        results.append(("✓", "CSV has Arabic header"))
    if "حقل الشمال" in csv_str:
        results.append(("✓", "CSV contains field name"))
    if "4.20" in csv_str and "2.80" in csv_str:
        results.append(("✓", "CSV has formatted areas"))
    if "─ المُجمَل ─" in csv_str:
        results.append(("✓", "CSV has summary row"))
    if csv_str.startswith("\ufeff"):
        results.append(("✓", "CSV has UTF-8 BOM (Excel-friendly)"))

    # English version
    csv_en = operation_to_csv(report, lang="en")
    if "field_id,field_name,area_ha" in csv_en:
        results.append(("✓", "CSV English header works"))

    # Total area
    if report.total_area_ha == 7.0:
        results.append(("✓", f"total_area_ha computed: {report.total_area_ha}"))

    return results


# ─── Runner ─────────────────────────────────────────────────────


def run_all():
    print("=" * 60)
    print("  v10 modules — runtime tests")
    print("=" * 60)

    suites = [
        ("Field Lifecycle State Machine", test_lifecycle_state_machine),
        ("Variable-Rate Prescriptions", test_prescriptions),
        ("Yield Heuristics", test_yield_heuristics),
        ("CSV Reports", test_reports_csv),
    ]

    total_pass = 0
    total_fail = 0

    for name, suite in suites:
        print(f"\n── {name} ──")
        try:
            results = suite()
            for status, msg in results:
                print(f"  {status} {msg}")
                if status == "✓":
                    total_pass += 1
                else:
                    total_fail += 1
        except Exception as e:
            print(f"  ✗ SUITE CRASHED: {type(e).__name__}: {e}")
            total_fail += 1

    print(f"\n{'=' * 60}")
    print(f"  Passed: {total_pass}/{total_pass + total_fail}")
    print(f"{'=' * 60}")
    return total_pass, total_fail


if __name__ == "__main__":
    p, f = run_all()
    sys.exit(0 if f == 0 else 1)
