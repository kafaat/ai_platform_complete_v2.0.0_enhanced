"""
core.learning.calibration_loop
==============================
المكوّن الأول للتعلّم: حلقة المعايرة (Feedback Loop).

يُغلق الحلقة التي كانت مفتوحة:
    توصية → تنفيذ → حصاد فعلي → معايرة → توصية أدق

المنهج (يتبع الأساليب المعتمدة، لا يخترع):
  1. اقرأ الغلة الفعلية من tenants/<id>/yield_history.csv (مصدر الحقيقة G1).
  2. قارن بتوقّع WOFOST/النموذج الأساسي → احسب البواقي (residuals).
  3. عاير zone_factor = متوسط (الفعلي / المتوقّع) — ضبط فيزيائي بسيط.
  4. حدّث districts/<region>/climate.yaml (إن اكتمل حد المزارع).
  5. لا معايرة بأقل من حد أدنى → تبقى "قيد المعايرة" (لا رقم وهمي).

القاعدة الذهبية: zone_factor مُخرَج من المعايرة، لا مُدخَل مخترع.
حد المزارع (farms_required) قابل للتعديل — تقدير الفريق.

ملاحظة إحصائية صادقة: مع حقل واحد (pseudoreplication)، المعايرة تعطي
zone_factor استرشادياً بثقة منخفضة. الثقة ترتفع مع تنوّع المزارع.
"""

from __future__ import annotations

import csv
import statistics
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class CalibrationResult:
    district_id: str
    status: str  # "calibrated" | "pending" | "insufficient"
    zone_factor: float | None  # OUTPUT — null until enough data
    n_seasons: int
    n_farms: int
    farms_required: int
    method: str
    confidence: str  # high | medium | low (pseudoreplication-aware)
    note_ar: str


def read_yield_history(tenant_dir: Path) -> list[dict]:
    """Read actual weighed-harvest records (ground truth G1)."""
    path = tenant_dir / "yield_history.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("verified") == "true"]


def _detect_trend(ratios: list[float]) -> str:
    """Is the series stable, rising, or falling? Determines calibration method.
    Honest: with <3 points we cannot assert a trend."""
    if len(ratios) < 3:
        return "insufficient"
    # simple monotonic check
    rising = all(ratios[i] <= ratios[i + 1] for i in range(len(ratios) - 1))
    falling = all(ratios[i] >= ratios[i + 1] for i in range(len(ratios) - 1))
    if rising and ratios[-1] > ratios[0] * 1.1:
        return "rising"
    if falling and ratios[-1] < ratios[0] * 0.9:
        return "falling"
    return "stable"


def calibrate_zone_factor(
    actual_yields: list[float],
    model_predicted: list[float],
) -> float | None:
    """Calibrate zone_factor, choosing method by data character.

    - stable series      -> simple mean (standard)
    - trending series     -> exponentially weighted (recent matters more)
    Returns None if inputs invalid (no fabrication)."""
    if not actual_yields or len(actual_yields) != len(model_predicted):
        return None
    ratios = [a / p for a, p in zip(actual_yields, model_predicted, strict=True) if p and p > 0]
    if not ratios:
        return None

    trend = _detect_trend(ratios)
    if trend in ("rising", "falling"):
        # exponential weights — recent seasons weighted higher
        weights = [i + 1 for i in range(len(ratios))]
        zf = sum(r * w for r, w in zip(ratios, weights, strict=True)) / sum(weights)
    else:
        zf = statistics.mean(ratios)  # stable or insufficient -> simple mean
    return round(zf, 3)


def calibration_method_used(actual_yields: list[float], model_predicted: list[float]) -> str:
    """Report which method was applied + honest data-sufficiency note."""
    ratios = [a / p for a, p in zip(actual_yields, model_predicted, strict=True) if p and p > 0]
    trend = _detect_trend(ratios)
    if trend == "insufficient":
        return "simple_mean (⚠️ <3 نقاط — لا يمكن تأكيد اتجاه)"
    if trend in ("rising", "falling"):
        return f"exponential_weighted (اتجاه {trend} مكتشف — الأحدث أهم)"
    return "simple_mean (سلسلة مستقرة)"


def _confidence(n_farms: int, n_seasons: int) -> str:
    """Honest confidence: single-farm data is pseudoreplicated."""
    if n_farms >= 5 and n_seasons >= 3:
        return "high"
    if n_farms >= 2:
        return "medium"
    return "low"  # single farm — indicative only


def run_calibration(
    district_dir: Path,
    tenant_dirs: list[Path],
    model_predict_fn,
) -> CalibrationResult:
    """Calibrate a region from its tenant farms' actual harvests.

    model_predict_fn(record) -> predicted yield (from WOFOST/base model).
    Caller supplies it so this stays decoupled from the physics engine.
    """
    climate = yaml.safe_load(open(district_dir / "climate.yaml", encoding="utf-8"))
    district_id = climate["district_id"]
    farms_required = climate["calibration"].get("farms_required", 5)

    all_actual: list[float] = []
    all_pred: list[float] = []
    farms_with_data = 0
    seasons = 0
    for td in tenant_dirs:
        recs = read_yield_history(td)
        if recs:
            farms_with_data += 1
            for r in recs:
                seasons += 1
                all_actual.append(float(r["yield_t_ha"]))
                all_pred.append(model_predict_fn(r))

    # not enough farms -> stay pending (no fake number)
    if farms_with_data < farms_required:
        return CalibrationResult(
            district_id=district_id,
            status="pending",
            zone_factor=None,
            n_seasons=seasons,
            n_farms=farms_with_data,
            farms_required=farms_required,
            method="awaiting_threshold",
            confidence=_confidence(farms_with_data, seasons),
            note_ar=(
                f"قيد المعايرة — {farms_with_data}/{farms_required} مزارع. "
                f"النواة العامة فقط حتى يكتمل الحد (تقدير الفريق)."
            ),
        )

    zf = calibrate_zone_factor(all_actual, all_pred)
    if zf is None:
        return CalibrationResult(
            district_id=district_id,
            status="insufficient",
            zone_factor=None,
            n_seasons=seasons,
            n_farms=farms_with_data,
            farms_required=farms_required,
            method="ratio_mean",
            confidence="low",
            note_ar="بيانات غير صالحة للمعايرة",
        )

    return CalibrationResult(
        district_id=district_id,
        status="calibrated",
        zone_factor=zf,
        n_seasons=seasons,
        n_farms=farms_with_data,
        farms_required=farms_required,
        method="zone_factor = mean(actual/predicted) [standard physical calibration]",
        confidence=_confidence(farms_with_data, seasons),
        note_ar=f"zone_factor={zf} من {seasons} مواسم، {farms_with_data} مزارع",
    )


def write_calibration(district_dir: Path, result: CalibrationResult) -> None:
    """Persist calibration OUTPUT to districts/<region>/climate.yaml."""
    path = district_dir / "climate.yaml"
    climate = yaml.safe_load(open(path, encoding="utf-8"))
    climate["calibration"].update(
        {
            "status": result.status.upper(),
            "farms_calibrated": result.n_farms,
            "zone_factor": result.zone_factor,
            "method": result.method,
            "confidence": result.confidence,
            "n_seasons": result.n_seasons,
        }
    )
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(climate, f, allow_unicode=True, sort_keys=False)
