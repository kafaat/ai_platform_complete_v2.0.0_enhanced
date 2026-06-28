"""Human feedback learning loop for recommendations.

Accept/reject signals are learning data, not proof that a recommendation was
agronomically correct. Outcome metrics must be compared against the field state
snapshot that existed when the recommendation was issued.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean
from typing import Literal

FeedbackKind = Literal["accepted", "rejected", "modified", "outcome"]


@dataclass(frozen=True)
class RecommendationFeedback:
    rec_id: str
    field_state_hash: str
    kind: FeedbackKind
    predicted_value: float | None = None
    actual_value: float | None = None
    note: str | None = None


def feedback_summary(items: list[RecommendationFeedback]) -> dict[str, float | int | None]:
    total = len(items)
    accepted = sum(1 for i in items if i.kind == "accepted")
    rejected = sum(1 for i in items if i.kind == "rejected")
    modified = sum(1 for i in items if i.kind == "modified")
    paired = [i for i in items if i.predicted_value is not None and i.actual_value is not None]
    if not paired:
        rmse = mape = None
    else:
        errors = [float(i.actual_value) - float(i.predicted_value) for i in paired]
        rmse = sqrt(mean([e * e for e in errors]))
        mape = (
            mean(
                [
                    abs((float(i.actual_value) - float(i.predicted_value)) / float(i.actual_value))
                    for i in paired
                    if float(i.actual_value) != 0
                ]
            )
            if any(float(i.actual_value) != 0 for i in paired)
            else None
        )
    return {
        "total": total,
        "accepted": accepted,
        "rejected": rejected,
        "modified": modified,
        "acceptance_rate": accepted / total if total else None,
        "revision_rate": modified / total if total else None,
        "rmse": rmse,
        "mape": mape,
        "outcome_pairs": len(paired),
    }


def should_retrain(
    items: list[RecommendationFeedback], min_outcomes: int = 30, max_mape: float = 0.25
) -> bool:
    summary = feedback_summary(items)
    if int(summary["outcome_pairs"] or 0) < min_outcomes:
        return False
    mape = summary["mape"]
    return bool(mape is not None and mape > max_mape)
