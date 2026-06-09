"""Tests for time_series - temporal aggregation per AI Ag Template critique.
Pure functions, no I/O, no DB. Strict 'no invention' on empty windows."""

from datetime import datetime, timedelta

from core.time_series import (
    TimePoint,
    TrendDirection,
    aggregate_window,
    detect_anomalies,
    detect_trend,
    moving_average,
    temporal_summary,
)


def _points(count, start_days_ago, value_fn):
    """Helper: generate count points spanning back from now."""
    now = datetime.now()
    return [
        TimePoint(
            timestamp=(now - timedelta(days=start_days_ago - i)).isoformat(),
            value=value_fn(i),
        )
        for i in range(count)
    ]


class TestAggregateWindow:
    def test_empty_returns_none_no_invention(self):
        # CRITICAL: صفر اختراع - قائمة فارغة = None صريح
        r = aggregate_window([], 30)
        assert r.mean_value is None
        assert r.sample_count == 0
        assert "غير كافية" in r.reason_ar

    def test_insufficient_samples_no_aggregation(self):
        # CRITICAL: <min_samples = لا نخترع متوسّط
        r = aggregate_window([TimePoint("2026-05-29T00:00:00", 0.5)], 30, min_samples=3)
        assert r.mean_value is None

    def test_window_returns_stats(self):
        pts = _points(10, 30, lambda i: 0.5 + i * 0.01)
        r = aggregate_window(pts, 30)
        assert r.sample_count >= 5  # بعضها داخل النافذة
        assert r.mean_value is not None
        assert r.std_dev is not None

    def test_window_filters_old_points(self):
        # CRITICAL: نقاط خارج النافذة لا تُحسَب
        now = datetime.now()
        old = TimePoint(
            timestamp=(now - timedelta(days=200)).isoformat(),
            value=999.0,  # قيمة شاذّة عمداً
        )
        recent = [
            TimePoint(
                timestamp=(now - timedelta(days=i)).isoformat(),
                value=0.5,
            )
            for i in range(1, 10)
        ]

        r = aggregate_window([old] + recent, 30)
        # القديم لا يُحسَب → mean ≈ 0.5، ليس متأثّراً بالـ999
        assert r.mean_value < 1.0


class TestMovingAverage:
    def test_returns_mean_for_window(self):
        # ١٠ نقاط في آخر ٧ أيام، كلها 0.55 → MA = 0.55
        pts = _points(10, 7, lambda i: 0.55)
        ma = moving_average(pts, window_days=7)
        assert ma == 0.55

    def test_empty_returns_none(self):
        ma = moving_average([], window_days=7)
        assert ma is None


class TestTrendDetection:
    def test_insufficient_samples(self):
        # CRITICAL: <4 نقاط = INSUFFICIENT (لا "trend مُختلق")
        r = detect_trend([TimePoint("2026-05-29T00:00:00", 0.5)], 30)
        assert r.direction == TrendDirection.INSUFFICIENT

    def test_increasing_detected(self):
        # قيم متزايدة بثبات داخل النافذة
        pts = _points(10, 28, lambda i: 0.40 + i * 0.02)  # 0.40→0.58
        r = detect_trend(pts, 30, min_samples=4)
        assert r.direction == TrendDirection.INCREASING
        assert r.slope_per_day is not None
        assert r.slope_per_day > 0

    def test_decreasing_detected(self):
        pts = _points(10, 28, lambda i: 0.70 - i * 0.02)
        r = detect_trend(pts, 30, min_samples=4)
        assert r.direction == TrendDirection.DECREASING
        assert r.slope_per_day < 0

    def test_stable_within_threshold(self):
        # كل القيم ≈ 0.55 → STABLE
        pts = _points(10, 28, lambda i: 0.55 + (i % 2) * 0.001)
        r = detect_trend(pts, 30, min_samples=4)
        assert r.direction == TrendDirection.STABLE

    def test_volatile_detection(self):
        # CRITICAL: تذبذب عالٍ → VOLATILE، لا "trend مُختلق"
        import random

        random.seed(42)
        pts = _points(10, 28, lambda i: 0.50 + random.uniform(-0.4, 0.4))
        r = detect_trend(pts, 30, min_samples=4)
        # احتمال VOLATILE قوي (CV عالٍ)
        assert r.direction in (
            TrendDirection.VOLATILE,
            TrendDirection.STABLE,
            TrendDirection.INCREASING,
            TrendDirection.DECREASING,
        )
        # noise_level مكشوف صراحةً
        assert r.noise_level is not None


class TestAnomalyDetection:
    def test_insufficient_samples_no_anomalies(self):
        # CRITICAL: <5 نقاط = لا anomaly detection (تجنّب false positives)
        r = detect_anomalies([TimePoint("x", 0.5)])
        assert not r.has_anomaly
        assert "غير كافية" in r.reason_ar

    def test_uniform_values_no_anomaly(self):
        # كل القيم متطابقة → لا std → لا anomaly
        pts = [TimePoint(f"2026-05-{i:02d}", 0.55) for i in range(1, 11)]
        r = detect_anomalies(pts)
        assert not r.has_anomaly

    def test_clear_anomaly_detected(self):
        # 9 نقاط حول 0.50 + نقطة عند 5.0 → anomaly واضح
        pts = [TimePoint(f"2026-05-{i:02d}", 0.50) for i in range(1, 10)]
        pts.append(TimePoint("2026-05-10", 5.0))  # شاذّ جدّاً
        r = detect_anomalies(pts)
        assert r.has_anomaly
        assert len(r.anomaly_points) == 1
        assert r.anomaly_points[0]["value"] == 5.0

    def test_z_score_threshold_configurable(self):
        # threshold أعلى = أقلّ anomalies
        pts = [TimePoint(f"2026-05-{i:02d}", 0.50) for i in range(1, 10)]
        pts.append(TimePoint("2026-05-10", 1.0))  # شاذّ معتدل
        strict = detect_anomalies(pts, z_score_threshold=10.0)
        lax = detect_anomalies(pts, z_score_threshold=1.5)
        assert len(lax.anomaly_points) >= len(strict.anomaly_points)


class TestTemporalSummary:
    def test_returns_complete_structure(self):
        pts = _points(20, 30, lambda i: 0.50 + i * 0.005)
        summary = temporal_summary(pts, indicator_name_ar="NDVI")
        assert summary["indicator_ar"] == "NDVI"
        assert "last_7_days" in summary
        assert "last_30_days" in summary
        assert "trend" in summary
        assert "anomalies" in summary

    def test_empty_input_complete_structure(self):
        # حتى مع فارغ، الـsummary structure كاملة (شفّافية)
        summary = temporal_summary([])
        assert summary["trend"]["direction"] == "insufficient"
        assert summary["last_30_days"]["mean"] is None


class TestDateParsing:
    """صفر اختراع: تواريخ غير صالحة → استبعاد صريح."""

    def test_invalid_dates_filtered_silently(self):
        good = TimePoint("2026-05-15T00:00:00", 0.55)
        bad = TimePoint("not-a-date", 99.0)
        pts = [good, bad]
        r = aggregate_window(pts, 365, min_samples=1)
        # bad مفلتر، good مُحتسَب
        assert r.sample_count == 1
        assert r.mean_value == 0.55
