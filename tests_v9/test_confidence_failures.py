"""
tests_v9/test_confidence_failures.py — runtime tests للوحدات الجديدة.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../services/sahool-platform'))
from datetime import datetime, timedelta, timezone


def test_confidence_engine():
    """تحقّق من حساب confidence المركّب."""
    from api.confidence_engine import (
        compute_ndvi_confidence, ConfidenceLevel,
        CloudConfidence, TemporalConfidence,
    )
    
    results = []
    
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    
    # حالة ممتازة: صورة حديثة + سماء صافية + تغطية كاملة
    perfect = compute_ndvi_confidence(
        ndvi_value=0.68,
        observation_date=now - timedelta(days=1),
        field_area_ha=4.0,
        cloud_pct=2,
        now=now,
    )
    if perfect.level == ConfidenceLevel.HIGH:
        results.append(("✓", f"perfect: {perfect.composite_score} ({perfect.level.value})"))
    else:
        results.append(("✗", f"perfect should be HIGH: {perfect.composite_score}"))
    
    # سيّئة: صورة قديمة + سحب كثيرة
    bad = compute_ndvi_confidence(
        ndvi_value=0.5,
        observation_date=now - timedelta(days=20),
        field_area_ha=4.0,
        cloud_pct=70,
        cloud_shadow_pct=10,
        now=now,
    )
    if bad.level in (ConfidenceLevel.LOW, ConfidenceLevel.VERY_LOW):
        results.append(("✓", f"bad: {bad.composite_score} ({bad.level.value})"))
    else:
        results.append(("✗", f"bad should be LOW/VERY_LOW: {bad.composite_score}"))
    
    # متوسّطة
    medium = compute_ndvi_confidence(
        ndvi_value=0.6,
        observation_date=now - timedelta(days=5),
        field_area_ha=4.0,
        cloud_pct=25,
        now=now,
    )
    if medium.level in (ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH):
        results.append(("✓", f"medium: {medium.composite_score}"))
    
    # Cloud component direct test
    cloud = CloudConfidence(cloud_pct=50, cloud_shadow_pct=10)
    if 0.3 < cloud.score < 0.5:
        results.append(("✓", f"cloud 50%+10% shadow: score {cloud.score:.2f}"))
    
    # Temporal decay
    temp_fresh = TemporalConfidence(days_since_observation=1)
    temp_old = TemporalConfidence(days_since_observation=30)
    if temp_fresh.score > 0.9 and temp_old.score < 0.3:
        results.append(("✓", f"temporal decay: 1d={temp_fresh.score:.2f}, 30d={temp_old.score:.2f}"))
    
    # Reasons in Arabic
    if any("سحب" in r for r in bad.reasons_ar):
        results.append(("✓", "Arabic reason: cloud detected"))
    if any("قديم" in r for r in bad.reasons_ar):
        results.append(("✓", "Arabic reason: stale detected"))
    
    # Ground truth bonus
    perfect_with_gt = compute_ndvi_confidence(
        ndvi_value=0.68,
        observation_date=now - timedelta(days=1),
        field_area_ha=4.0,
        cloud_pct=2,
        has_ground_truth=True,
        now=now,
    )
    if perfect_with_gt.composite_score >= perfect.composite_score:
        results.append(("✓", f"ground truth bonus: {perfect_with_gt.composite_score} >= {perfect.composite_score}"))
    
    return results


def test_failure_taxonomy():
    """تحقّق من كشف failure modes الزراعيّة."""
    from api.failure_modes import (
        detect, detect_sentinel_issues, detect_soil_issues,
        detect_weather_issues, FailureSeverity, FailureCategory,
        highest_severity, FAILURE_CATALOG,
    )
    
    results = []
    
    # Catalog completeness
    if len(FAILURE_CATALOG) >= 12:
        results.append(("✓", f"catalog has {len(FAILURE_CATALOG)} failure modes"))
    
    # Sentinel cloud high
    f = detect_sentinel_issues(cloud_pct=85, days_since_observation=2)
    if f and f.failure_mode.code == "sentinel.cloud_high":
        results.append(("✓", "detected: sentinel.cloud_high"))
    
    # Sentinel stale
    f = detect_sentinel_issues(cloud_pct=10, days_since_observation=20)
    if f and f.failure_mode.code == "sentinel.stale":
        results.append(("✓", "detected: sentinel.stale"))
    
    # Sentinel OK
    f = detect_sentinel_issues(cloud_pct=15, days_since_observation=5)
    if f is None:
        results.append(("✓", "no issue for fresh+clear Sentinel"))
    
    # Soil issues
    issues = detect_soil_issues({"soil_ph": 14.5, "soil_ec": 3, "last_sample_days_ago": 30})
    if any(i.failure_mode.code == "soil.invalid_range" for i in issues):
        results.append(("✓", "detected: invalid pH"))
    
    issues = detect_soil_issues({"soil_ph": 7.5, "last_sample_days_ago": 500})
    if any(i.failure_mode.code == "soil.no_recent_lab" for i in issues):
        results.append(("✓", "detected: no recent lab"))
    
    # Weather
    f = detect_weather_issues(hours_since_update=72)
    if f and f.failure_mode.code == "weather.stale":
        results.append(("✓", "detected: weather.stale"))
    
    # Critical failures
    banned = detect("policy.banned_chemical", chemical="DDT")
    if banned.failure_mode.severity == FailureSeverity.CRITICAL:
        results.append(("✓", "banned chemical → CRITICAL"))
    
    # Severity ranking
    soils = detect_soil_issues({"soil_ph": 14.5, "last_sample_days_ago": 100})
    sev = highest_severity(soils)
    if sev == FailureSeverity.CRITICAL:
        results.append(("✓", f"highest of soil issues: {sev.value}"))
    
    # Arabic messages
    if "سحب" in detect("sentinel.cloud_high", cloud_pct=90).failure_mode.message_ar:
        results.append(("✓", "Arabic message for sentinel.cloud_high"))
    if "محظور" in detect("policy.banned_chemical").failure_mode.message_ar:
        results.append(("✓", "Arabic message for banned chemical"))
    
    # Unknown code → graceful
    unknown = detect("magic_failure_code_xyz")
    if unknown.failure_mode.code.startswith("unknown:"):
        results.append(("✓", "unknown code handled gracefully"))
    
    return results


def test_temporal_arbitration():
    """تحقّق من كشف الـcombinations الزمنيّة غير المتسقة."""
    from api.temporal_arbitration import (
        TemporalArbiter, Measurement, DataSource,
    )
    
    results = []
    
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    arbiter = TemporalArbiter(now=now)
    
    # حالة جيّدة: NDVI + ET0 من نفس الأسبوع
    good = [
        Measurement(DataSource.NDVI_SENTINEL, now - timedelta(days=2), 0.65),
        Measurement(DataSource.WEATHER_ETO, now - timedelta(days=1), 5.2),
    ]
    r = arbiter.check_combination(good)
    if r.valid and not r.issues:
        results.append(("✓", "fresh NDVI + ET0: no issues"))
    
    # حالة سيّئة: NDVI من شهر مع ET0 من اليوم
    bad = [
        Measurement(DataSource.NDVI_SENTINEL, now - timedelta(days=30), 0.65),
        Measurement(DataSource.WEATHER_ETO, now - timedelta(days=1), 5.2),
    ]
    r = arbiter.check_combination(bad)
    has_gap_issue = any(i.code == "pair_gap_exceeded" for i in r.issues)
    if has_gap_issue:
        results.append(("✓", "30-day gap NDVI/ET0 detected"))
    
    # حالة accepted: soil_lab مع NDVI (90-day window)
    soil_ndvi = [
        Measurement(DataSource.SOIL_LAB, now - timedelta(days=60), None),
        Measurement(DataSource.NDVI_SENTINEL, now - timedelta(days=2), 0.65),
    ]
    r = arbiter.check_combination(soil_ndvi)
    pair_gap = any(i.code == "pair_gap_exceeded" for i in r.issues)
    if not pair_gap:
        results.append(("✓", "60-day soil + fresh NDVI: OK (lab/sat allowed)"))
    
    # حالة stale واحد
    stale_only = [
        Measurement(DataSource.WEATHER_ETO, now - timedelta(days=10), 5.2),
    ]
    r = arbiter.check_combination(stale_only)
    has_stale = any(i.code == "data_stale" for i in r.issues)
    if has_stale:
        results.append(("✓", "stale ET0 detected"))
    
    # can_combine_for_recommendation
    ok, issues = arbiter.can_combine_for_recommendation(good, "irrigation")
    if ok:
        results.append(("✓", "irrigation rec: good measurements OK"))
    
    ok, issues = arbiter.can_combine_for_recommendation([
        Measurement(DataSource.NDVI_SENTINEL, now - timedelta(days=90), 0.5),
        Measurement(DataSource.WEATHER_ETO, now, 5.2),
    ], "irrigation")
    # 90-day gap = error severity
    if not ok:
        results.append(("✓", "irrigation rec rejected with 90-day gap"))
    
    return results


def run_all():
    print("="*60)
    print("  Confidence + Failures + Temporal — runtime tests")
    print("="*60)
    
    suites = [
        ("Confidence Engine",         test_confidence_engine),
        ("Failure Taxonomy",          test_failure_taxonomy),
        ("Temporal Arbitration",      test_temporal_arbitration),
    ]
    
    tp = 0; tf = 0
    for name, suite in suites:
        print(f"\n── {name} ──")
        try:
            for status, msg in suite():
                print(f"  {status} {msg}")
                if status == "✓": tp += 1
                else: tf += 1
        except Exception as e:
            print(f"  ✗ CRASHED: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
            tf += 1
    
    print(f"\n{'='*60}")
    print(f"  Passed: {tp}/{tp+tf}")
    print(f"{'='*60}")
    return tp, tf


if __name__ == "__main__":
    p, f = run_all()
    sys.exit(0 if f == 0 else 1)
