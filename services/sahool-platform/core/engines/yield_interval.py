"""
sahool_core.calibration.yield_interval
=======================================
Yield estimation as an INTERVAL (conformal-style), never a fake point.

The critique: don't output "5.8 t/ha" (fake precision). Output
[4.2, 7.1] t/ha at 90% coverage, or "قيد المعايرة" when no data.

Split-conformal prediction (Vovk et al.; Lei et al. 2018):
  1. fit a base model (here: WOFOST sim or simple regressor) on training set
  2. compute residuals on a held-out calibration set
  3. interval = prediction +/- quantile(residuals, 1-alpha)

Until tenant-specific calibration data exists, this returns status=PENDING and
NO numeric estimate — by design.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class YieldInterval:
    status: str  # "calibrated" | "pending"
    point_estimate: float | None
    lower: float | None
    upper: float | None
    coverage: float | None
    n_calibration: int
    note_ar: str


def conformal_interval(
    point_estimate: float,
    calibration_residuals: list[float],
    coverage: float = 0.90,
) -> YieldInterval:
    """Build a conformal prediction interval from held-out residuals.

    Requires a real calibration set. Refuses to fabricate if too small.
    """
    n = len(calibration_residuals)
    if n < 10:
        return YieldInterval(
            status="pending",
            point_estimate=None,
            lower=None,
            upper=None,
            coverage=None,
            n_calibration=n,
            note_ar="قيد المعايرة — بيانات غير كافية لنطاق موثوق (تحتاج ≥10 نقاط محجوبة)",
        )
    abs_res = sorted(abs(r) for r in calibration_residuals)
    # conformal quantile index
    k = min(n - 1, int((n + 1) * coverage) - 1)
    q = abs_res[max(0, k)]
    return YieldInterval(
        status="calibrated",
        point_estimate=round(point_estimate, 2),
        lower=round(point_estimate - q, 2),
        upper=round(point_estimate + q, 2),
        coverage=coverage,
        n_calibration=n,
        note_ar=f"نطاق إنتاج بتغطية {int(coverage * 100)}% (لا نقطة وهمية)",
    )


def pending_estimate() -> YieldInterval:
    """Explicit 'not yet calibrated' — the honest default before tenant data exists."""
    return YieldInterval(
        status="pending",
        point_estimate=None,
        lower=None,
        upper=None,
        coverage=None,
        n_calibration=0,
        note_ar="قيد المعايرة — لا تقدير إنتاج حتى تتوفر بيانات حصاد محلّية",
    )
