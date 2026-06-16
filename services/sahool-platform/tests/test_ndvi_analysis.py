"""اختبارات وحدة (pure) لمحلّل سلسلة NDVI — core.ndvi_analysis.

لا خدمات، لا قاعدة بيانات: منطق صرف على core.time_series + stdlib.
"""

import pytest
from core.ndvi_analysis import analyze_ndvi_series

pytestmark = pytest.mark.unit


def _series(values):
    """يبني سلسلة بتواريخ متتالية من قائمة قيم NDVI."""
    return [{"date": f"2026-01-{i + 1:02d}", "ndvi": v} for i, v in enumerate(values)]


class TestTrend:
    def test_declining_series(self):
        r = analyze_ndvi_series(_series([0.7, 0.65, 0.55, 0.45, 0.35]))
        assert r["trend"] == "declining"
        assert r["trend_slope"] < 0
        assert r["health_class"] == "stressed"  # أحدث 0.35 < 0.40
        assert r["latest"] == 0.35

    def test_greening_series(self):
        r = analyze_ndvi_series(_series([0.30, 0.40, 0.50, 0.60, 0.70]))
        assert r["trend"] == "greening"
        assert r["trend_slope"] > 0

    def test_flat_series_stable(self):
        r = analyze_ndvi_series(_series([0.50, 0.50, 0.50, 0.50, 0.50]))
        assert r["trend"] == "stable"
        assert r["trend_slope"] == 0.0


class TestAnomaly:
    def test_clear_outlier_flagged(self):
        # سلسلة ناعمة مع قفزة شاذّة واحدة (>= min_samples = 5 نقاط)
        r = analyze_ndvi_series(
            _series([0.50, 0.51, 0.49, 0.99, 0.50, 0.52, 0.48, 0.50, 0.51, 0.49])
        )
        assert r["anomaly"]["has_anomaly"] is True
        assert len(r["anomaly"]["points"]) >= 1
        assert any(p["value"] == 0.99 for p in r["anomaly"]["points"])

    def test_smooth_series_no_anomaly(self):
        r = analyze_ndvi_series(_series([0.50, 0.51, 0.49, 0.50, 0.52, 0.48, 0.50]))
        assert r["anomaly"]["has_anomaly"] is False


class TestHonesty:
    def test_empty_series(self):
        r = analyze_ndvi_series([])
        assert r["n_points"] == 0
        assert r["trend"] == "insufficient"
        assert r["health_class"] == "unknown"
        assert r["latest"] is None
        assert r["note_ar"]  # رسالة صريحة

    def test_short_series_insufficient(self):
        r = analyze_ndvi_series(_series([0.5, 0.6]))  # نقطتان < MIN_POINTS=3
        assert r["trend"] == "insufficient"
        assert r["health_class"] == "unknown"
        assert r["n_points"] == 2
        # mean/latest محسوبان بصدق دون اختراع اتجاه
        assert r["latest"] == 0.6
        assert r["note_ar"]

    def test_malformed_point_skipped(self):
        # نقطة بلا ndvi تُتجاهَل دون crash
        series = [
            {"date": "2026-01-01", "ndvi": 0.5},
            {"date": "2026-01-02"},  # malformed: missing ndvi
            {"date": "2026-01-03", "ndvi": 0.55},
            {"date": "2026-01-04", "ndvi": 0.6},
        ]
        r = analyze_ndvi_series(series)
        assert r["n_points"] == 3  # النقطة المعطوبة مُتجاهَلة
        assert r["trend"] in {"greening", "stable", "declining"}

    def test_non_numeric_ndvi_skipped(self):
        series = [
            {"date": "d", "ndvi": "abc"},
            {"date": "d", "ndvi": None},
            {"date": "d", "ndvi": True},  # bool مُستبعَد صراحةً
        ]
        r = analyze_ndvi_series(series)
        assert r["n_points"] == 0
        assert r["health_class"] == "unknown"

    def test_garbage_input_no_exception(self):
        for bad in (None, "string", 42, {"series": 1}):
            r = analyze_ndvi_series(bad)
            assert r["n_points"] == 0
            assert r["trend"] == "insufficient"


class TestHealthBands:
    def test_latest_healthy(self):
        r = analyze_ndvi_series(_series([0.5, 0.6, 0.65, 0.68, 0.70]))
        assert r["latest"] == 0.70
        assert r["health_class"] == "healthy"  # >= 0.60

    def test_latest_moderate(self):
        r = analyze_ndvi_series(_series([0.45, 0.48, 0.49, 0.50, 0.50]))
        assert r["latest"] == 0.50
        assert r["health_class"] == "moderate"  # 0.40 <= x < 0.60

    def test_latest_stressed(self):
        r = analyze_ndvi_series(_series([0.45, 0.40, 0.35, 0.32, 0.30]))
        assert r["latest"] == 0.30
        assert r["health_class"] == "stressed"  # < 0.40
