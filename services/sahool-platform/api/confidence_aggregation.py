"""
services/sahool-platform/api/confidence_aggregation.py — Compositional Confidence

المرجع: المراجعة:
   "هل الـconfidence:
      - propagated؟
      - compositional؟
      - attached to recommendations؟
    أم فقط local calculations؟"

✅ سؤال مشروع. الـconfidence_engine يحسب confidence لقراءة واحدة (NDVI).
   لكن الـrecommendation تستهلك عدّة قراءات. نحتاج aggregation منهجيّ.

ما يفعله:
   ١. يأخذ مجموعة input confidences (NDVI, soil, weather)
   ٢. يدمجها برياضيّات بسيطة (لا "AI propagation")
   ٣. يضيف penalty لو غاب أحد المدخلات الحرجة
   ٤. يُرفِق الـcombined confidence بكل recommendation

الفلسفة:
   - geometric mean بدل arithmetic (أيّ مكوّن ضعيف يخفّض المجموع)
   - critical inputs تكون required (لو غابت → very_low)
   - non-critical inputs تكون weighted contributions
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .confidence_engine import (
    ConfidenceLevel,
    level_from_score,
)

# ─── Aggregation strategy ───────────────────────────────────────


@dataclass
class ConfidenceInput:
    """input واحد للـaggregation."""

    name: str  # "ndvi" / "soil_ph" / "weather_eto"
    score: float  # 0-1
    weight: float = 1.0
    is_critical: bool = False  # لو missing → recommendation rejected
    is_present: bool = True  # False لو الـinput غير متوفّر


@dataclass
class AggregatedConfidence:
    """نتيجة دمج confidences متعدّدة."""

    score: float  # 0-1
    level: ConfidenceLevel
    inputs_used: list[str]
    inputs_missing: list[str]  # الـmissing critical inputs
    inputs_degraded: list[str]  # < 0.5
    rationale_ar: str

    @property
    def safe_for_action(self) -> bool:
        """هل آمن لتنفيذ action تلقائياً؟"""
        return (
            self.level in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM) and not self.inputs_missing
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level.value,
            "inputs_used": self.inputs_used,
            "inputs_missing": self.inputs_missing,
            "inputs_degraded": self.inputs_degraded,
            "rationale_ar": self.rationale_ar,
            "safe_for_action": self.safe_for_action,
        }


# ─── Aggregator ────────────────────────────────────────────────


def aggregate(inputs: list[ConfidenceInput]) -> AggregatedConfidence:
    """
    Combines confidences using weighted geometric mean.

    Rules:
      ١. لو أيّ input حرج missing → score=0, very_low
      ٢. لو inputs غير حرجة missing → penalty proportional
      ٣. weighted geometric mean على الـpresent inputs
      ٤. arithmetic floor 0.01 لمنع log(0)
    """
    if not inputs:
        return AggregatedConfidence(
            score=0.0,
            level=ConfidenceLevel.VERY_LOW,
            inputs_used=[],
            inputs_missing=[],
            inputs_degraded=[],
            rationale_ar="لا توجد أيّ مدخلات للحساب",
        )

    inputs_used: list[str] = []
    missing_critical: list[str] = []
    degraded: list[str] = []
    weighted_log_sum = 0.0
    total_weight = 0.0
    missing_non_critical_weight = 0.0

    for inp in inputs:
        if not inp.is_present:
            if inp.is_critical:
                missing_critical.append(inp.name)
            else:
                missing_non_critical_weight += inp.weight
            continue

        inputs_used.append(inp.name)
        clamped = max(0.01, min(1.0, inp.score))
        weighted_log_sum += inp.weight * math.log(clamped)
        total_weight += inp.weight

        if inp.score < 0.5:
            degraded.append(inp.name)

    # Critical missing → reject
    if missing_critical:
        return AggregatedConfidence(
            score=0.0,
            level=ConfidenceLevel.VERY_LOW,
            inputs_used=inputs_used,
            inputs_missing=missing_critical,
            inputs_degraded=degraded,
            rationale_ar=f"مدخلات حرجة مفقودة: {', '.join(missing_critical)}",
        )

    if total_weight == 0:
        return AggregatedConfidence(
            score=0.0,
            level=ConfidenceLevel.VERY_LOW,
            inputs_used=[],
            inputs_missing=[],
            inputs_degraded=[],
            rationale_ar="جميع المدخلات مفقودة",
        )

    # Geometric mean
    score = math.exp(weighted_log_sum / total_weight)

    # Penalty للـnon-critical missing (proportional to weight lost)
    if missing_non_critical_weight > 0:
        penalty_factor = total_weight / (total_weight + missing_non_critical_weight)
        score *= penalty_factor

    score = round(max(0.0, min(1.0, score)), 3)
    level = level_from_score(score)

    # Rationale
    parts = [f"دُمِجت {len(inputs_used)} مدخلات (المجموع {score:.0%})"]
    if degraded:
        parts.append(f"ضعيفة: {', '.join(degraded)}")
    if missing_non_critical_weight > 0:
        parts.append(f"نقص {missing_non_critical_weight:.1f} وحدات وزن")

    return AggregatedConfidence(
        score=score,
        level=level,
        inputs_used=inputs_used,
        inputs_missing=missing_critical,
        inputs_degraded=degraded,
        rationale_ar=" · ".join(parts),
    )


# ─── Recipe presets للـcommon recommendations ───────────────────


def irrigation_confidence(
    ndvi_confidence: float | None,
    et0_confidence: float | None,
    soil_moisture_confidence: float | None,
    weather_forecast_confidence: float | None,
) -> AggregatedConfidence:
    """confidence لتوصية ري."""
    return aggregate(
        [
            ConfidenceInput(
                "ndvi",
                ndvi_confidence or 0,
                weight=0.30,
                is_critical=False,
                is_present=ndvi_confidence is not None,
            ),
            ConfidenceInput(
                "et0",
                et0_confidence or 0,
                weight=0.35,
                is_critical=True,
                is_present=et0_confidence is not None,
            ),
            ConfidenceInput(
                "soil_moisture",
                soil_moisture_confidence or 0,
                weight=0.25,
                is_critical=False,
                is_present=soil_moisture_confidence is not None,
            ),
            ConfidenceInput(
                "weather_forecast",
                weather_forecast_confidence or 0,
                weight=0.10,
                is_critical=False,
                is_present=weather_forecast_confidence is not None,
            ),
        ]
    )


def fertilizer_confidence(
    soil_lab_confidence: float | None,
    ndvi_confidence: float | None,
    crop_stage_known: bool,
) -> AggregatedConfidence:
    """confidence لتوصية تسميد."""
    return aggregate(
        [
            ConfidenceInput(
                "soil_lab",
                soil_lab_confidence or 0,
                weight=0.50,
                is_critical=True,
                is_present=soil_lab_confidence is not None,
            ),
            ConfidenceInput(
                "ndvi",
                ndvi_confidence or 0,
                weight=0.30,
                is_critical=False,
                is_present=ndvi_confidence is not None,
            ),
            ConfidenceInput(
                "crop_stage",
                1.0 if crop_stage_known else 0,
                weight=0.20,
                is_critical=False,
                is_present=crop_stage_known,
            ),
        ]
    )


def yield_prediction_confidence(
    ndvi_confidence: float | None,
    lifecycle_complete: bool,
    sample_count: int,
) -> AggregatedConfidence:
    """confidence لتوقّع إنتاج."""
    return aggregate(
        [
            ConfidenceInput(
                "ndvi_history",
                ndvi_confidence or 0,
                weight=0.45,
                is_critical=True,
                is_present=ndvi_confidence is not None,
            ),
            ConfidenceInput(
                "lifecycle_history",
                1.0 if lifecycle_complete else 0.3,
                weight=0.35,
                is_critical=False,
                is_present=True,
            ),
            ConfidenceInput(
                "soil_samples",
                min(1.0, sample_count / 3.0),
                weight=0.20,
                is_critical=False,
                is_present=sample_count > 0,
            ),
        ]
    )
