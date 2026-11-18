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


class TestPhysicalNdviRange:
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 1.01, -1.01])
    def test_non_finite_or_out_of_range_samples_do_not_become_crop_health(self, bad):
        r = analyze_ndvi_series(_series([0.45, bad, 0.65]))
        assert r["n_points"] == 2
        assert r["trend"] == "insufficient"
        assert r["health_class"] == "unknown"
        assert r["latest"] == 0.65

    def test_only_invalid_values_are_explicitly_insufficient(self):
        r = analyze_ndvi_series(_series([float("nan"), float("inf"), 2.0]))
        assert r["n_points"] == 0
        assert r["latest"] is None
        assert r["mean"] is None
        assert r["health_class"] == "unknown"

    def test_physical_ndvi_boundaries_remain_valid(self):
        r = analyze_ndvi_series(_series([-1.0, 0.0, 1.0]))
        assert r["n_points"] == 3
        assert r["latest"] == 1.0


def test_chronology_is_independent_of_delivery_order():
    series = _series([0.2, 0.45, 0.7])
    series[-1]["date"] = "2026-02-15"
    result = analyze_ndvi_series(series)
    assert (result["latest"], result["trend"], result["health_class"]) == (
        0.7,
        "greening",
        "healthy",
    )
    assert result["trend_slope"] == 0.25  # Published unit is per reading.
    assert analyze_ndvi_series(series[::-1]) == result


@pytest.mark.parametrize("bad_date", [None, "", "2026-02-30", "yesterday", "2026-01-01"])
def test_unresolved_chronology_withholds_temporal_claims(bad_date):
    series = _series([0.2, 0.45, 0.7])
    if bad_date is None:
        del series[-1]["date"]
    else:
        series[-1]["date"] = bad_date
    result = analyze_ndvi_series(series)
    assert result["latest"] is None
    assert result["trend_slope"] is None
    assert result["trend"] == "insufficient"
    assert result["health_class"] == "unknown"
    assert result["note_ar"]


def test_offset_timestamps_compare_by_instant():
    series = [
        {"date": "2026-01-02T00:00:00+03:00", "ndvi": 0.2},
        {"date": "2026-01-01T22:00:00Z", "ndvi": 0.4},
        {"date": "2026-01-01T23:00:00Z", "ndvi": 0.7},
    ]
    assert analyze_ndvi_series(series[::-1])["latest"] == 0.7
    for ambiguous in ("2026-01-01T21:00:00Z", "2026-01-02", "2026-01-01T23:00:00"):
        series[-1]["date"] = ambiguous
        assert analyze_ndvi_series(series)["latest"] is None


@pytest.mark.parametrize("value", [10**400, -(10**400)], ids=["positive", "negative"])
def test_out_of_range_integer_is_discarded_before_float_conversion(value):
    result = analyze_ndvi_series(_series([0.45, value, 0.65]))
    assert result["n_points"] == 2
    assert result["latest"] == 0.65


def test_api_does_not_coerce_boolean_to_ndvi():
    import api.main  # noqa: F401
    from api.routers.ndvi_analysis import NdviAnalysisRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="ndvi"):
        NdviAnalysisRequest.model_validate({"series": [{"date": "2026-01-01", "ndvi": True}]})

    request = NdviAnalysisRequest.model_validate(
        {"series": [{"date": "2026-01-01", "ndvi": "0.45"}]}
    )
    assert request.series[0].ndvi == 0.45
