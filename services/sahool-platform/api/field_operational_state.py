"""
api/field_operational_state.py — الحالة التشغيليّة الموحّدة للحقل

الفجوة التي يسدّها (من المراجعة المعماريّة العميقة، المستند ٩):
  المنصّة تملك فحوصاً ممتازة لكن **متفرّقة**: النضارة (temporal)، الثقة
  (confidence)، التناقض (agronomic_consistency) — كلّ منها يعمل محليّاً
  ويُقرأ منفصلاً. لا توجد طبقة **تركّبها في حالة تشغيليّة واحدة رسميّة**
  تُجيب: "ما وضع هذا القرار الآن — صالح؟ متدهور؟ يحتاج مراجعة؟".

ما يفعله (وما لا يفعله — صدق):
  ✓ يركّب المكوّنات الموجودة (لا يكرّرها) في DecisionValidity واحدة
  ✓ يحوّل العتبات المبعثرة إلى حالات رسميّة صريحة (VALID/DEGRADED/...)
  ✓ يحدّد نمط التنفيذ المناسب (تلقائي/مراجعة/حظر)
  ✗ ليس "جبر حالات" كامل ولا نظريّة تشغيل صوريّة — تلك مبالغة للحجم الحالي
  ✗ لا ذاكرة تشغيليّة تاريخيّة ولا نمذجة سببيّة — توسّعات سابقة لأوانها
  ✗ لا يستبدل المكوّنات — يقرأ نتائجها ويجمعها

مبنيّ على: ConfidenceLevel (confidence_engine) + ConsistencyResult
(agronomic_consistency) + فحص النضارة. تركيب شفّاف بقواعد صريحة.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .agronomic_consistency import (
    ConflictSeverity,
    ConsistencyResult,
    check_decision_freshness,
    check_irrigation_consistency,
)


class DecisionValidity(str, Enum):  # noqa: UP042 (intentional str-mixin for JSON/Pydantic value serialization)
    """الحالة التشغيليّة الرسميّة للقرار — تركيب موحّد للعوامل."""

    VALID = "valid"  # ثقة كافية + بيانات حديثة + لا تناقض → نفّذ
    DEGRADED = "degraded"  # ثقة/نضارة منقوصة → نفّذ بحذر أو راجع
    CONFLICTED = "conflicted"  # تناقض زراعي → مراجعة بشريّة قبل التنفيذ
    INSUFFICIENT = "insufficient"  # بيانات ناقصة لاتّخاذ قرار موثوق


class ExecutionMode(str, Enum):  # noqa: UP042 (intentional str-mixin for JSON/Pydantic value serialization)
    """كيف يُعامَل القرار تنفيذيّاً (Policy Enforcement)."""

    AUTO = "auto"  # يمكن عرضه/تنفيذه مباشرة
    HUMAN_REVIEW = "human_review"  # يتطلّب تأكيد المهندس/المزارع
    BLOCKED = "blocked"  # لا يُنفّذ حتّى تُحلّ المشكلة


@dataclass
class FieldOperationalState:
    """الحالة التشغيليّة الموحّدة — تجمع كلّ العوامل في كيان واحد."""

    field_id: str
    validity: DecisionValidity
    execution_mode: ExecutionMode
    confidence_level: str | None = None
    reasons_ar: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    freshness_warnings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "field_id": self.field_id,
            "validity": self.validity.value,
            "execution_mode": self.execution_mode.value,
            "confidence_level": self.confidence_level,
            "reasons_ar": self.reasons_ar,
            "conflicts": self.conflicts,
            "freshness_warnings": self.freshness_warnings,
            "note_ar": (
                "حالة تشغيليّة موحّدة — تركيب شفّاف للنضارة والثقة والتناقض. "
                "تُعلِم بنمط التنفيذ المناسب؛ حكم المهندس يبقى المرجع النهائي."
            ),
        }


# خريطة مستوى الثقة النصّي → هل كافٍ للتنفيذ التلقائي؟
_CONFIDENCE_OK = {"high", "medium"}


def resolve_field_state(
    field_id: str,
    confidence_level: str | None = None,
    irrigation_delta_pct: float | None = None,
    rain_forecast_mm: float | None = None,
    soil_moisture_ratio: float | None = None,
    et0_mm: float | None = None,
    ndvi_age_days: float | None = None,
    soil_age_days: float | None = None,
    weather_age_hours: float | None = None,
) -> FieldOperationalState:
    """يركّب العوامل في حالة تشغيليّة واحدة رسميّة.

    الأولويّة (الأخطر يحكم):
      تناقض BLOCK → CONFLICTED/BLOCKED
      بيانات ناقصة جوهريّاً → INSUFFICIENT
      ثقة منخفضة أو نضارة متدهورة أو تحذير → DEGRADED/HUMAN_REVIEW
      غير ذلك → VALID/AUTO
    """
    reasons: list[str] = []

    # ١. افحص التناقض الزراعي (الموجود)
    consistency: ConsistencyResult = check_irrigation_consistency(
        irrigation_delta_pct,
        rain_forecast_mm,
        soil_moisture_ratio,
        et0_mm,
        _level_to_scalar(confidence_level),
    )
    # ٢. افحص النضارة (الموجود)
    freshness: ConsistencyResult = check_decision_freshness(
        ndvi_age_days, soil_age_days, weather_age_hours
    )

    has_block = any(c.severity == ConflictSeverity.BLOCK for c in consistency.conflicts)
    has_warn = (
        any(c.severity == ConflictSeverity.WARN for c in consistency.conflicts)
        or len(freshness.conflicts) > 0
    )
    conf_ok = confidence_level in _CONFIDENCE_OK if confidence_level else None

    # ٣. ركّب الحالة (الأخطر يحكم)
    if has_block:
        validity = DecisionValidity.CONFLICTED
        mode = ExecutionMode.BLOCKED
        reasons.append("تناقض زراعي صريح — يتطلّب مراجعة بشريّة قبل التنفيذ.")
    elif confidence_level is None and irrigation_delta_pct is None:
        validity = DecisionValidity.INSUFFICIENT
        mode = ExecutionMode.HUMAN_REVIEW
        reasons.append("بيانات غير كافية لاتّخاذ قرار موثوق.")
    elif conf_ok is False or has_warn:
        validity = DecisionValidity.DEGRADED
        mode = ExecutionMode.HUMAN_REVIEW
        if conf_ok is False:
            reasons.append(f"مستوى الثقة ({confidence_level}) دون عتبة التنفيذ التلقائي.")
        if has_warn:
            reasons.append("تحذيرات نضارة/تناقض تستوجب حذراً.")
    else:
        validity = DecisionValidity.VALID
        mode = ExecutionMode.AUTO
        reasons.append("ثقة كافية + بيانات حديثة + لا تناقض.")

    return FieldOperationalState(
        field_id=field_id,
        validity=validity,
        execution_mode=mode,
        confidence_level=confidence_level,
        reasons_ar=reasons,
        conflicts=[c.to_dict() for c in consistency.conflicts],
        freshness_warnings=[c.to_dict() for c in freshness.conflicts],
    )


def _level_to_scalar(level: str | None) -> float | None:
    """يحوّل مستوى الثقة النصّي لتقدير عددي (للفحص الداخلي فقط)."""
    return {"high": 0.85, "medium": 0.65, "low": 0.45, "very_low": 0.25}.get(level or "")
