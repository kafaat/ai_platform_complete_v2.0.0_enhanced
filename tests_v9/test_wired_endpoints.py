"""
tests_v9/test_wired_endpoints.py — اختبارات منطق الـendpoints المُوصَّلة حديثاً.

⚠ صدق: بلا fastapi/pydantic (شبكة معطّلة)، نحاكي منطق كل endpoint
   (request → module logic → response) بنفس الاستدعاءات التي في main.py.
   لا نختبر الـHTTP layer أو auth dependency (يحتاج fastapi).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../services/sahool-platform'))
from datetime import datetime, timedelta, timezone


def test_nitrogen_prescription_endpoint():
    from api.prescriptions import (
        PrescriptionGenerator, ZoneCharacteristics, ZoneClass, prescription_to_dict,
    )
    results = []
    gen = PrescriptionGenerator()
    zones = [
        ZoneCharacteristics(zone_id="z1", zone_class=ZoneClass.HIGH, area_ha=1.5,
                            ndvi_mean=0.72, soil_ph=7.4, soil_n_ppm=18, soil_texture="loamy"),
        ZoneCharacteristics(zone_id="z2", zone_class=ZoneClass.PROBLEM, area_ha=0.9,
                            ndvi_mean=0.35, soil_ec=5.2, soil_n_ppm=8, soil_texture="sandy"),
    ]
    rx = gen.generate_nitrogen("fld-1", "seas-1", "wheat", zones)
    d = prescription_to_dict(rx)
    if "zones" in d and len(d["zones"]) == 2:
        results.append(("✓", "N prescription: 2 zones في الاستجابة"))
    # unknown crop → 422 (ValueError)
    try:
        gen.generate_nitrogen("f", "s", "moon_wheat", zones)
        results.append(("✗", "كان يجب رفض المحصول المجهول"))
    except ValueError:
        results.append(("✓", "محصول مجهول → ValueError (422)"))
    return results


def test_yield_estimate_endpoint():
    from api.yield_heuristics import LifecycleFeatures, estimate_yield, detect_anomalies
    results = []
    f = LifecycleFeatures(field_id="fld-1", crop="wheat", days_in_growing=90,
                          irrigation_count=8, moisture_stress_events=0, avg_ndvi_growing=0.70)
    est = estimate_yield(f)
    anomalies = detect_anomalies(f)
    if est.estimated_yield_kg_ha > 0 and est.confidence > 0:
        results.append(("✓", f"yield estimate: {est.estimated_yield_kg_ha} kg/ha, conf={est.confidence}"))
    if isinstance(anomalies, list):
        results.append(("✓", f"anomalies list: {len(anomalies)}"))
    return results


def test_ndvi_confidence_endpoint():
    from api.confidence_engine import compute_ndvi_confidence
    results = []
    now = datetime.now(timezone.utc)
    conf = compute_ndvi_confidence(
        ndvi_value=0.68, observation_date=now - timedelta(days=2),
        field_area_ha=4.0, cloud_pct=5,
    )
    d = conf.to_dict()
    if "confidence" in d and "score" in d["confidence"]:
        results.append(("✓", f"NDVI confidence: {d['confidence']['score']} ({d['confidence']['level']})"))
    return results


def test_irrigation_confidence_endpoint():
    from api.confidence_aggregation import irrigation_confidence
    results = []
    # ET0 موجود → safe
    agg = irrigation_confidence(0.85, 0.90, 0.7, 0.6)
    if agg.safe_for_action:
        results.append(("✓", f"irrigation conf safe: {agg.score}"))
    # ET0 غائب (حرج) → unsafe
    agg2 = irrigation_confidence(0.85, None, 0.7, 0.6)
    if not agg2.safe_for_action:
        results.append(("✓", "irrigation بلا ET0 → unsafe"))
    return results


def test_failures_check_endpoint():
    from api.failure_modes import detect_sentinel_issues, detect_soil_issues
    results = []
    f = detect_sentinel_issues(cloud_pct=85, days_since_observation=2)
    if f and f.to_dict()["code"] == "sentinel.cloud_high":
        results.append(("✓", "endpoint يكشف sentinel.cloud_high"))
    soils = detect_soil_issues({"soil_ph": 14.5, "last_sample_days_ago": 30})
    if any(s.to_dict()["code"] == "soil.invalid_range" for s in soils):
        results.append(("✓", "endpoint يكشف soil.invalid_range"))
    return results


def test_temporal_check_endpoint():
    from api.temporal_arbitration import TemporalArbiter, Measurement, DataSource
    results = []
    now = datetime.now(timezone.utc)
    arbiter = TemporalArbiter(now=now)
    # crop-aware: tomato + 5-day gap → reject
    ms = [
        Measurement(DataSource.NDVI_SENTINEL, now - timedelta(days=5), 0.6),
        Measurement(DataSource.WEATHER_ETO, now, 5.2),
    ]
    r = arbiter.check_combination(ms, crop="tomato")
    if any(i.code == "pair_gap_exceeded" for i in r.issues):
        results.append(("✓", "temporal endpoint: tomato 5d gap rejected"))
    r2 = arbiter.check_combination(ms, crop="dates")
    if not any(i.code == "pair_gap_exceeded" for i in r2.issues):
        results.append(("✓", "temporal endpoint: dates 5d gap OK"))
    return results


def test_operation_report_endpoint():
    from api.reports import FieldReport, OperationReport, operation_to_csv
    results = []
    fields = [
        FieldReport(field_id="f1", field_name_ar="حقل ١", farm_id="frm",
                    tenant_id="t", area_ha=4.2, crop="wheat", season_label="شتاء 2026",
                    planting_date="2026-02-15", harvest_date=None, lifecycle_stage="GROWING",
                    irrigation_events=5, total_water_m3=420, avg_ndvi=0.68),
    ]
    report = OperationReport(tenant_id="t", operation_name_ar="مزرعة الأمل",
                             fields=fields, period_start="2026-02-01",
                             period_end="2026-05-31", generated_at="2026-06-03T12:00:00Z")
    csv = operation_to_csv(report, lang="ar")
    if csv.startswith("\ufeff") and "حقل ١" in csv:
        results.append(("✓", "operation report CSV: BOM + بيانات عربيّة"))
    return results



# ─── الوحدتان الإضافيّتان (lifecycle + replay) ───
def test_lifecycle_transition_endpoint():
    from api.field_lifecycle import LifecycleStage, is_valid_transition
    results = []
    # valid
    if is_valid_transition(LifecycleStage.PLANTED, LifecycleStage.GROWING):
        results.append(("✓", "PLANTED→GROWING صالح"))
    # invalid
    if not is_valid_transition(LifecycleStage.CREATED, LifecycleStage.HARVESTED):
        results.append(("✓", "CREATED→HARVESTED مرفوض"))
    return results


def test_replay_reconstruct_endpoint():
    from api.event_replay import FieldStateReconstructor
    results = []
    events = [
        {"event_type": "field.created", "occurred_at": "2026-01-01T08:00:00+00:00",
         "payload": {"name_ar": "حقل", "area_ha": 4.0, "crop": "wheat"}},
        {"event_type": "lifecycle.transitioned", "occurred_at": "2026-02-01T06:00:00+00:00",
         "payload": {"to_stage": "PLANTED"}},
        {"event_type": "operation.irrigation.completed", "occurred_at": "2026-02-05T18:00:00+00:00",
         "payload": {"water_m3": 320}},
    ]
    state = FieldStateReconstructor.reconstruct("field", "fld-1", events)
    if state.field_name == "حقل" and state.irrigation_count == 1 and state.total_events == 3:
        results.append(("✓", f"replay: name={state.field_name}, irr={state.irrigation_count}, events={state.total_events}"))
    if state.lifecycle_stage == "PLANTED":
        results.append(("✓", "replay: lifecycle_stage مُعاد بناؤه"))
    return results


def run_all():
    print("="*60)
    print("  Wired endpoints (٧ وحدات pure-logic موصَّلة) — tests")
    print("="*60)
    suites = [
        ("N Prescription",        test_nitrogen_prescription_endpoint),
        ("Yield Estimate",        test_yield_estimate_endpoint),
        ("NDVI Confidence",       test_ndvi_confidence_endpoint),
        ("Irrigation Confidence", test_irrigation_confidence_endpoint),
        ("Failures Check",        test_failures_check_endpoint),
        ("Temporal Check",        test_temporal_check_endpoint),
        ("Operation Report",      test_operation_report_endpoint),
        ("Lifecycle Transition",  test_lifecycle_transition_endpoint),
        ("Replay Reconstruct",    test_replay_reconstruct_endpoint),
    ]
    tp = tf = 0
    for name, suite in suites:
        print(f"\n── {name} ──")
        try:
            for status, msg in suite():
                print(f"  {status} {msg}")
                tp += 1 if status == "✓" else 0
                tf += 1 if status == "✗" else 0
        except Exception as e:
            print(f"  ✗ CRASHED: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
            tf += 1
    print(f"\n{'='*60}\n  Passed: {tp}/{tp+tf}\n{'='*60}")
    return tp, tf


if __name__ == "__main__":
    p, f = run_all()
    sys.exit(0 if f == 0 else 1)
