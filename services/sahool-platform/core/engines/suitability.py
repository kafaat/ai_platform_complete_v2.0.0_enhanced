"""
sahool_core.engines.suitability
================================
Crop suitability via the GATE FUNNEL discussed across the design:

  Gate 1 (Agronomic): governing factors (knock-out). One fail => N.
  Gate 2 (Seasonal):  flowering must fall in safe-temperature window.
  Gate 3 (Yield):     WOFOST/history ranks survivors (NO fake numbers).
  Gate 4 (Market):    CV-based price risk + gap (NO fake price forecast).

Governing vs modifying (limiting-factor principle, Liebig's law):
  - governing  : pH, salinity, chilling hours, drainage -> can KILL the crop
  - modifying  : NPK, organic matter -> reduce yield but treatable

Suitability classes follow FAO land evaluation (FAO, 1976, Bulletin 32):
  S1 excellent | S2 suitable | S3 marginal | N not suitable

Confidence is CATEGORICAL (high/medium/low) tied to measurement error,
never a fabricated percentage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from core.engines.fuzzy import (
    TrapezoidParams, trapezoidal_score, descending_score, ascending_score,
)
from core.engines.fusion import Confidence


class SuitabilityClass(str, Enum):
    S1 = "S1"  # excellent
    S2 = "S2"  # suitable
    S3 = "S3"  # marginal
    N = "N"    # not suitable


@dataclass
class GoverningFactor:
    """Knock-out factor. Outside acceptable => crop fails (N)."""
    name: str
    name_ar: str
    value: float
    min_acceptable: float
    max_acceptable: float
    measurement_error: float        # for confidence
    source: str

    def passes(self) -> bool:
        return self.min_acceptable <= self.value <= self.max_acceptable


@dataclass
class ModifyingFactor:
    """Weighted, treatable factor scored by fuzzy membership."""
    name: str
    name_ar: str
    value: float
    trapezoid: TrapezoidParams
    weight: float
    measurement_error: float
    source: str

    def score(self) -> float:
        return trapezoidal_score(self.value, self.trapezoid)


@dataclass
class SuitabilityResult:
    crop_id: str
    suitability: SuitabilityClass
    score: float                    # 0-100 (from modifying factors)
    confidence: Confidence
    failed_governing: list[str] = field(default_factory=list)
    breakdown: list[dict] = field(default_factory=list)
    reason_ar: str = ""


def _confidence_from_errors(errors: list[float]) -> Confidence:
    """Weakest link: confidence driven by the largest measurement error."""
    if not errors:
        return Confidence.LOW
    worst = max(errors)
    if worst <= 0.10:
        return Confidence.HIGH
    if worst <= 0.25:
        return Confidence.MEDIUM
    return Confidence.LOW


def evaluate_suitability(
    crop_id: str,
    governing: list[GoverningFactor],
    modifying: list[ModifyingFactor],
) -> SuitabilityResult:
    """Gate 1 (agronomic). Governing first (knock-out), then weighted modifiers."""
    # --- Gate 1a: governing knock-out ---
    failed = [g.name_ar for g in governing if not g.passes()]
    if failed:
        # find the specific failing values for the reason
        details = [
            f"{g.name_ar}={g.value} (المطلوب {g.min_acceptable}-{g.max_acceptable})"
            for g in governing if not g.passes()
        ]
        conf = _confidence_from_errors([g.measurement_error for g in governing])
        return SuitabilityResult(
            crop_id=crop_id,
            suitability=SuitabilityClass.N,
            score=0.0,
            confidence=conf,
            failed_governing=failed,
            reason_ar="غير ملائم — عوامل حاكمة فاشلة: " + "؛ ".join(details),
        )

    # --- Gate 1b: weighted modifying factors ---
    total_w = sum(m.weight for m in modifying) or 1.0
    score = 0.0
    breakdown = []
    for m in modifying:
        s = m.score()
        score += s * m.weight
        breakdown.append({
            "factor": m.name_ar,
            "value": m.value,
            "score": round(s, 2),
            "weight": m.weight,
            "error": m.measurement_error,
            "source": m.source,
        })
    final = (score / total_w) * 100.0

    if final >= 85:
        cls = SuitabilityClass.S1
    elif final >= 60:
        cls = SuitabilityClass.S2
    elif final >= 40:
        cls = SuitabilityClass.S3
    else:
        cls = SuitabilityClass.N

    all_errors = (
        [g.measurement_error for g in governing]
        + [m.measurement_error for m in modifying]
    )
    conf = _confidence_from_errors(all_errors)

    return SuitabilityResult(
        crop_id=crop_id,
        suitability=cls,
        score=round(final, 1),
        confidence=conf,
        breakdown=breakdown,
        reason_ar=f"الملاءمة {cls.value} (درجة {final:.0f}/100)",
    )
