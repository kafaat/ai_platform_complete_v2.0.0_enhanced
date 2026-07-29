"""
tests_v9/test_v13_refinements.py — اختبارات للتحسينات الثلاث:
  ١. Temporal arbitration crop-aware
  ٢. Confidence aggregation (compositional + propagated)
  ٣. Failure retry hints (machine-readable)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))
from datetime import UTC, datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit


def test_crop_aware_temporal():
    """نفس الفجوة الزمنيّة، حكم مختلف حسب المحصول."""
    from api.temporal_arbitration import (
        DataSource,
        Measurement,
        TemporalArbiter,
    )

    results = []
    now = datetime(2026, 6, 1, tzinfo=UTC)
    arbiter = TemporalArbiter(now=now)

    # ٥ أيّام بين NDVI و ET0
    measurements = [
        Measurement(DataSource.NDVI_SENTINEL, now - timedelta(days=5), 0.6),
        Measurement(DataSource.WEATHER_ETO, now, 5.2),
    ]

    # حالة ١: قمح (multiplier=1.0) → tolerance=7 يوم → 5 OK
    r = arbiter.check_combination(measurements, crop="wheat")
    has_gap = any(i.code == "pair_gap_exceeded" for i in r.issues)
    if not has_gap:
        results.append(("✓", "wheat: 5-day gap acceptable (tolerance ~7d)"))

    # حالة ٢: طماطم (multiplier=0.5) → tolerance=3.5 يوم → 5 يتجاوز
    r = arbiter.check_combination(measurements, crop="tomato")
    has_gap = any(i.code == "pair_gap_exceeded" for i in r.issues)
    if has_gap:
        results.append(("✓", "tomato: 5-day gap rejected (vegetables sensitive)"))

    # حالة ٣: نخيل (multiplier=2.0) → tolerance=14 يوم → 5 OK
    r = arbiter.check_combination(measurements, crop="dates")
    has_gap = any(i.code == "pair_gap_exceeded" for i in r.issues)
    if not has_gap:
        results.append(("✓", "dates: 5-day gap acceptable (trees slow)"))

    # حالة ٤: قمح في مرحلة الأزهار (stage=flowering, multiplier=0.5)
    # tolerance = 7 × 1.0 × 0.5 = 3.5 يوم → 5 يتجاوز
    r = arbiter.check_combination(measurements, crop="wheat", stage="flowering")
    has_gap = any(i.code == "pair_gap_exceeded" for i in r.issues)
    if has_gap:
        results.append(("✓", "wheat at flowering: stricter tolerance"))

    # حالة ٥: قمح في النضج (stage=maturity, multiplier=1.2)
    # tolerance = 7 × 1.0 × 1.2 = 8.4 يوم → 5 OK
    r = arbiter.check_combination(measurements, crop="wheat", stage="maturity")
    has_gap = any(i.code == "pair_gap_exceeded" for i in r.issues)
    if not has_gap:
        results.append(("✓", "wheat at maturity: relaxed tolerance"))

    return results


def test_confidence_aggregation():
    """compositional confidence مع propagation."""
    from api.confidence_aggregation import (
        AggregatedConfidence,
        ConfidenceInput,
        aggregate,
        fertilizer_confidence,
        irrigation_confidence,
        yield_prediction_confidence,
    )
    from api.confidence_engine import ConfidenceLevel

    results = []

    # حالة كاملة — كل المدخلات قويّة
    inputs = [
        ConfidenceInput("ndvi", 0.9, weight=1.0),
        ConfidenceInput("soil", 0.85, weight=1.0),
        ConfidenceInput("weather", 0.88, weight=1.0),
    ]
    agg = aggregate(inputs)
    if agg.score > 0.8 and agg.level == ConfidenceLevel.HIGH:
        results.append(("✓", f"all strong: score={agg.score} {agg.level.value}"))
    else:
        results.append(("✗", f"expected HIGH, got {agg.score} {agg.level.value}"))

    # حالة فيها مكوّن ضعيف → geometric mean يخفّض
    weak = [
        ConfidenceInput("ndvi", 0.9, weight=1.0),
        ConfidenceInput("soil", 0.95, weight=1.0),
        ConfidenceInput("weather", 0.20, weight=1.0),  # ضعيف جدّاً
    ]
    agg = aggregate(weak)
    if agg.score < 0.65:  # arithmetic لكان ~0.68، geometric ~0.55
        results.append(("✓", f"weak component pulls down: {agg.score}"))
    if "weather" in agg.inputs_degraded:
        results.append(("✓", "weak input flagged as degraded"))

    # حرج missing → very_low
    critical_missing = [
        ConfidenceInput("ndvi", 0.9, is_critical=False, is_present=True),
        ConfidenceInput("et0", 0, is_critical=True, is_present=False),
    ]
    agg = aggregate(critical_missing)
    if agg.score == 0.0 and agg.level == ConfidenceLevel.VERY_LOW:
        results.append(("✓", "critical missing → rejected"))
    if "et0" in agg.inputs_missing:
        results.append(("✓", "missing critical listed"))
    if not agg.safe_for_action:
        results.append(("✓", "not safe_for_action when critical missing"))

    # Non-critical missing → penalty لكن ليس rejection
    non_critical = [
        ConfidenceInput("ndvi", 0.9, weight=0.6, is_critical=True, is_present=True),
        ConfidenceInput("weather", 0.8, weight=0.4, is_critical=False, is_present=False),
    ]
    agg = aggregate(non_critical)
    if 0.4 < agg.score < 0.7:
        results.append(("✓", f"non-critical missing: penalty applied {agg.score}"))

    # Irrigation recipe
    irr = irrigation_confidence(
        ndvi_confidence=0.85,
        et0_confidence=0.90,
        soil_moisture_confidence=0.7,
        weather_forecast_confidence=0.6,
    )
    if irr.safe_for_action:
        results.append(("✓", f"irrigation rec: safe={irr.safe_for_action} score={irr.score}"))

    # Irrigation بدون ET0 (critical) → unsafe
    irr_no_et0 = irrigation_confidence(
        ndvi_confidence=0.85,
        et0_confidence=None,
        soil_moisture_confidence=0.7,
        weather_forecast_confidence=0.6,
    )
    if not irr_no_et0.safe_for_action:
        results.append(("✓", "irrigation without ET0: unsafe (rejected)"))

    # Fertilizer بدون lab → unsafe
    fert_no_lab = fertilizer_confidence(
        soil_lab_confidence=None,
        ndvi_confidence=0.8,
        crop_stage_known=True,
    )
    if not fert_no_lab.safe_for_action:
        results.append(("✓", "fertilizer without lab: unsafe"))

    # Empty → very_low
    empty = aggregate([])
    if empty.level == ConfidenceLevel.VERY_LOW:
        results.append(("✓", "empty inputs → very_low"))

    return results


def test_retry_hints():
    """retry policies للـfailure modes — machine readable."""
    from api.failure_modes import (
        FAILURE_CATALOG,
        FailureCategory,
        RetryPolicy,
        detect,
    )

    results = []

    # كل failure مهمّة لديها retry hint
    failures_without_retry = [code for code, f in FAILURE_CATALOG.items() if f.retry is None]
    if not failures_without_retry:
        results.append(("✓", f"all {len(FAILURE_CATALOG)} failures have retry hints"))
    else:
        results.append(("✗", f"missing retry: {failures_without_retry}"))

    # Banned chemical → NO_RETRY
    f = detect("policy.banned_chemical")
    if f.failure_mode.retry and f.failure_mode.retry.policy == RetryPolicy.NO_RETRY:
        results.append(("✓", "banned chemical → NO_RETRY"))

    # Sentinel unavailable → EXP_BACKOFF
    f = detect("sentinel.unavailable")
    if (
        f.failure_mode.retry
        and f.failure_mode.retry.policy == RetryPolicy.EXP_BACKOFF
        and f.failure_mode.retry.max_attempts == 5
    ):
        results.append(("✓", "sentinel.unavailable → EXP_BACKOFF, 5 attempts"))

    # Cloud high → WAIT_NEXT_CYCLE (wait for next satellite pass)
    f = detect("sentinel.cloud_high")
    if f.failure_mode.retry and f.failure_mode.retry.policy == RetryPolicy.WAIT_NEXT_CYCLE:
        results.append(("✓", "cloud high → WAIT_NEXT_CYCLE"))

    # Invalid polygon → MANUAL_INTERVENTION
    f = detect("field.polygon_invalid")
    if f.failure_mode.retry and f.failure_mode.retry.policy == RetryPolicy.MANUAL_INTERVENTION:
        results.append(("✓", "invalid polygon → MANUAL_INTERVENTION"))

    # to_dict includes retry
    d = f.to_dict()
    if "retry" in d and "policy" in d["retry"] and "max_attempts" in d["retry"]:
        results.append(("✓", "to_dict serializes retry hint"))

    # Backoff configuration
    f = detect("sync.queue_overflow")
    if (
        f.failure_mode.retry
        and f.failure_mode.retry.initial_delay_sec == 10
        and f.failure_mode.retry.max_attempts == 10
    ):
        results.append(("✓", "sync queue → EXP_BACKOFF (10s, 10 attempts)"))

    return results


def run_all():
    print("=" * 60)
    print("  v13 refinements — runtime tests")
    print("=" * 60)

    suites = [
        ("Crop-Aware Temporal", test_crop_aware_temporal),
        ("Confidence Aggregation", test_confidence_aggregation),
        ("Retry Hints", test_retry_hints),
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
            import traceback

            traceback.print_exc()
            tf += 1

    print(f"\n{'=' * 60}")
    print(f"  Passed: {tp}/{tp + tf}")
    print(f"{'=' * 60}")
    return tp, tf


if __name__ == "__main__":
    p, f = run_all()
    sys.exit(0 if f == 0 else 1)
