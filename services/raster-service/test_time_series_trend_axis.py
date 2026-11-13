"""linear_trend uses the real month axis and reports how well a line fits.

Lesson from InSAR time series (DefoEye, Houston P2/P3): a fitted rate is not uniform
motion. A missing month must not be folded away, and a single slope must carry its
residuals so a non-linear curve is not read as a steady trend.
"""

from time_series import linear_trend


def _c(*pairs):
    return [{"month": m, "median": v} for m, v in pairs]


def test_a_missing_month_does_not_inflate_the_slope():
    # 0.30 in Jan, 0.36 in Apr: +0.02/month on the real axis (3-month gap)
    out = linear_trend(_c(("2026-01", 0.30), ("2026-04", 0.36)))
    assert out["slope"] == 0.02
    assert out["span_months"] == 3 and out["missing_months"] == 2


def test_the_axis_crosses_a_year_boundary():
    out = linear_trend(_c(("2025-11", 0.40), ("2025-12", 0.42), ("2026-01", 0.44)))
    assert out["slope"] == 0.02
    assert out["span_months"] == 2 and out["missing_months"] == 0


def test_a_rise_then_fall_is_reported_nonlinear_not_just_a_slope():
    out = linear_trend(
        _c(("2026-01", 0.30), ("2026-02", 0.60), ("2026-03", 0.62), ("2026-04", 0.32))
    )
    assert out["fit_quality"] == "nonlinear"
    assert out["residual_rms"] > 0.1


def test_a_steady_rise_is_linear_with_small_residuals():
    out = linear_trend(
        _c(("2026-01", 0.30), ("2026-02", 0.32), ("2026-03", 0.34), ("2026-04", 0.36))
    )
    assert out["fit_quality"] == "linear" and out["r2"] == 1.0
    assert out["residual_rms"] == 0.0 and out["direction"] == "improving"


def test_first_and_last_are_the_first_and_last_observed_values():
    out = linear_trend(_c(("2026-01", None), ("2026-02", 0.4), ("2026-03", 0.5), ("2026-04", None)))
    assert (out["first"], out["last"]) == (0.4, 0.5)
    assert (out["first_month"], out["last_month"]) == ("2026-02", "2026-03")


def test_too_few_points_and_bad_months_stay_honest():
    assert linear_trend(_c(("2026-01", 0.3)))["direction"] == "insufficient_data"
    assert linear_trend(_c(("bad", 0.3), ("2026-02", 0.4)))["direction"] == "insufficient_data"
    assert linear_trend(_c(("2026-01", 0.3), ("2026-02", 0.4)))["fit_quality"] == "undetermined"
