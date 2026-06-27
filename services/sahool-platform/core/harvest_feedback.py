"""Harvest-grounded feedback learning.

Acceptance and rejection are behavioural signals.  Actual weighed harvest is the
truth source for model/recommendation evaluation.  Calibration remains disabled
until minimum real outcomes are available.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean


@dataclass(frozen=True)
class HarvestOutcome:
    field_id: str
    season_id: str
    field_state_hash: str
    actual_yield_t_ha: float
    area_ha: float
    weighed: bool = True

    def __post_init__(self) -> None:
        if self.actual_yield_t_ha < 0 or self.area_ha <= 0:
            raise ValueError("harvest outcome values must be positive")


@dataclass(frozen=True)
class RecommendationPrediction:
    rec_id: str
    field_id: str
    season_id: str
    field_state_hash: str
    predicted_yield_t_ha: float | None


@dataclass(frozen=True)
class FeedbackEvaluation:
    n_pairs: int
    rmse: float | None
    mape: float | None
    r2: float | None
    calibration_ready: bool
    note_ar: str


def evaluate_harvest_feedback(
    predictions: list[RecommendationPrediction],
    outcomes: list[HarvestOutcome],
    *,
    min_calibration_pairs: int = 30,
) -> FeedbackEvaluation:
    outcome_index = {
        (o.field_id, o.season_id, o.field_state_hash): o for o in outcomes if o.weighed
    }
    pairs: list[tuple[float, float]] = []
    for pred in predictions:
        if pred.predicted_yield_t_ha is None:
            continue
        out = outcome_index.get((pred.field_id, pred.season_id, pred.field_state_hash))
        if out is not None:
            pairs.append((float(pred.predicted_yield_t_ha), float(out.actual_yield_t_ha)))
    if not pairs:
        return FeedbackEvaluation(
            0, None, None, None, False, "لا توجد أزواج حصاد موزون كافية للتقييم."
        )
    errors = [actual - predicted for predicted, actual in pairs]
    rmse = sqrt(mean([e * e for e in errors]))
    non_zero_actuals = [(p, a) for p, a in pairs if a != 0]
    mape = mean([abs(a - p) / abs(a) for p, a in non_zero_actuals]) if non_zero_actuals else None
    r2 = _r2(pairs) if len(pairs) >= 3 else None
    ready = len(pairs) >= min_calibration_pairs
    note = (
        "جاهز لمراجعة المعايرة." if ready else "البيانات الحقيقية غير كافية؛ يبقى zone_factor=null."
    )
    return FeedbackEvaluation(len(pairs), rmse, mape, r2, ready, note)


def _r2(pairs: list[tuple[float, float]]) -> float | None:
    actuals = [a for _, a in pairs]
    baseline = mean(actuals)
    ss_tot = sum((a - baseline) ** 2 for a in actuals)
    if ss_tot == 0:
        return None
    ss_res = sum((a - p) ** 2 for p, a in pairs)
    return 1 - ss_res / ss_tot
