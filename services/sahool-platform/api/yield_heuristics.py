"""
services/sahool-platform/api/yield_heuristics.py — Yield Estimation Heuristics

⚠ ملاحظة منهجيّة صريحة:
   هذا الملف يُسمَّى "heuristics" وليس "AI Temporal Intelligence Engine" كما
   اقترح أحد المستندات الخارجيّة. السبب:
     - لا يوجد ML model هنا
     - لا training data
     - لا inference
     - فقط قواعد agronomic + rule-based scoring

   تسميته "AI" تكون مُضلِّلة. هذه heuristics من الكتب الزراعيّة + tuning.

ماذا يفعل الفعلاً:
   ١. يستهلك lifecycle events لحقل ما
   ٢. يستخرج features بسيطة (stress count, irrigation freq, growth duration)
   ٣. يقيس "yield score" بقواعد agronomic
   ٤. يُرجع توقّع مع confidence (الـconfidence منخفض دائماً بدون lab data)

ما لا يفعله:
   ✗ predictive ML
   ✗ deep learning
   ✗ "understanding" الزراعة
   ✗ closed-loop autonomous decisions (هذا خطر، نرفضه)

الـclosed-loop auto-irrigation كما اقترح المستند الخارجي:
   نرفضه في v0.1 — حتّى نختبر ميدانياً مع >50 حقل.
   البديل: نولّد suggestion، يعرضها المزارع، يقرّر هو.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ─── Types ──────────────────────────────────────────────────────


class StressLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class LifecycleFeatures:
    """Features مُستخلَصة من lifecycle events لحقل."""

    field_id: str
    crop: str
    days_in_growing: int = 0
    irrigation_count: int = 0
    moisture_stress_events: int = 0
    pest_alerts: int = 0
    fertilizer_applications: int = 0
    avg_ndvi_growing: float | None = None
    avg_ndvi_mature: float | None = None
    drought_streak_days: int = 0  # أطول فترة بدون ري
    rain_events: int = 0


@dataclass
class YieldEstimate:
    field_id: str
    crop: str
    estimated_yield_kg_ha: float
    yield_score: float  # 0-1 (نسبيّ للحقل الأمثل)
    confidence: float  # 0-1
    stress_level: StressLevel
    rationale_ar: str
    contributors: list[str] = field(default_factory=list)  # ما رفع/خفّض التقدير
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""


# ─── Knowledge: crop max yields (kg/ha) ─────────────────────────
# مرجع: متوسّطات اليمن وفق وزارة الزراعة + FAO
# هذه ليست "world records" — هي target واقعيّة للمزارع اليمني الجيّد
# ⚠ UNVALIDATED DEFAULT — needs agronomist review (جلسة التصحيح الذاتي)
# القيم أدناه تقديريّة ومنطقيّة لكنّها لم تُتحقَّق من مصدر علمي/ميداني موثَّق.
# يجب مراجعتها مع مهندس زراعي يمني قبل الاعتماد عليها في قرارات حقيقيّة.
CROP_TARGET_YIELDS = {
    "wheat": 2_800,
    "barley": 2_400,
    "corn": 6_000,
    "tomato": 50_000,
    "potato": 25_000,
    "onion": 30_000,
    "cotton": 2_200,
    "alfalfa": 12_000,  # fresh, multi-cut
    "sorghum": 3_200,
}

# Days in "GROWING" stage (typical for Yemen, varies by season)
# ⚠ UNVALIDATED DEFAULT — needs agronomist review (جلسة التصحيح الذاتي)
# القيم أدناه تقديريّة ومنطقيّة لكنّها لم تُتحقَّق من مصدر علمي/ميداني موثَّق.
# يجب مراجعتها مع مهندس زراعي يمني قبل الاعتماد عليها في قرارات حقيقيّة.
CROP_TYPICAL_GROWING_DAYS = {
    "wheat": 90,
    "barley": 75,
    "corn": 100,
    "tomato": 80,
    "potato": 95,
    "onion": 120,
    "cotton": 150,
    "sorghum": 110,
}


def vegetative_growing_days(crop: str) -> int | None:
    """أيّام النموّ الخضريّ (init+development+mid) بحلّ طبقيّ نقيّ.

    ترتيب الحلّ (من الأخصّ للأعمّ):
      1) CROP_TYPICAL_GROWING_DAYS[crop] — قاموس التجاوز الموثوق (يحفظ كلّ
         القيم الحاليّة حرفيّاً؛ سلوك مطابق تماماً لكلّ محصول موجود فيه).
      2) sum(stage_days[:3]) من بطاقة المحصول — مجموع المراحل الثلاث الأولى
         (تأسيس + نموّ + منتصف) من `kc.stage_days`، أي يستثني المرحلة الأخيرة
         (النضج/التشيّخ). يُحلّ فقط إن وُجدت بطاقة لها ≥٣ مراحل.
      3) None — لا تجاوز ولا بطاقة صالحة.

    هذا هو مقياس "النموّ الخضريّ" — متمايز عمداً عن
    `crop_cycle.cycle_days_to_maturity` (الدورة الكاملة من البذار للنضج،
    وهي مجموع كلّ المراحل). الكمّيّتان مختلفتان قصداً: الأولى تستثني مرحلة
    النضج النهائيّة، والثانية تشملها. مثال القمح: الخضريّ ٩٠ (15+25+50)
    مقابل الدورة الكاملة ١٢٠ (15+25+50+30).

    نقيّ بالكامل (لا شبكة، لا قاعدة). أيّ خطأ في تحميل البطاقة ⇐ None.
    """
    typical = CROP_TYPICAL_GROWING_DAYS.get(crop)
    if typical is not None:
        return typical
    try:
        from core.crop_cards.loader import load_crop_card

        card = load_crop_card(crop)
        if not card:
            return None
        stage_days = card.get("kc", {}).get("stage_days")
        if not isinstance(stage_days, list) or len(stage_days) < 3:
            return None
        first_three = stage_days[:3]
        if not all(isinstance(d, (int, float)) for d in first_three):
            return None
        return int(sum(first_three))
    except Exception:
        return None


# ─── Feature builder (from events) ──────────────────────────────


def build_features_from_events(
    field_id: str,
    crop: str,
    events: list[dict[str, Any]],
    ndvi_history: list[dict[str, Any]] | None = None,
) -> LifecycleFeatures:
    """
    Events list من field_lifecycle_transitions + events أخرى.
    Each event: {event_type: str, timestamp: ISO str, payload: dict}

    NDVI history (optional): [{date, ndvi_mean, stage}, ...]
    """
    f = LifecycleFeatures(field_id=field_id, crop=crop.lower())

    growing_start = None
    last_irrigation = None
    longest_drought = 0
    current_drought = 0

    for ev in sorted(events, key=lambda e: e.get("timestamp", "")):
        etype = ev.get("event_type", "")
        ts = _parse_ts(ev.get("timestamp"))

        if etype == "lifecycle.transition":
            to_stage = ev.get("payload", {}).get("to_stage")
            if to_stage == "GROWING" and growing_start is None:
                growing_start = ts
            elif to_stage == "MATURE" and growing_start and ts:
                f.days_in_growing = max(0, (ts - growing_start).days)

        elif etype.startswith("operation.irrigation"):
            f.irrigation_count += 1
            if last_irrigation and ts:
                gap_days = (ts - last_irrigation).days
                longest_drought = max(longest_drought, gap_days)
            last_irrigation = ts
            current_drought = 0

        elif "moisture.low" in etype or "drought" in etype:
            f.moisture_stress_events += 1
            current_drought += 1
            longest_drought = max(longest_drought, current_drought)

        elif etype.startswith("pest.") or etype.startswith("disease."):
            f.pest_alerts += 1

        elif etype.startswith("operation.fertilizer"):
            f.fertilizer_applications += 1

        elif etype == "weather.rain":
            f.rain_events += 1

    f.drought_streak_days = longest_drought

    # NDVI averages from history
    if ndvi_history:
        growing_ndvi = [
            n["ndvi_mean"]
            for n in ndvi_history
            if n.get("stage") == "GROWING" and n.get("ndvi_mean") is not None
        ]
        mature_ndvi = [
            n["ndvi_mean"]
            for n in ndvi_history
            if n.get("stage") == "MATURE" and n.get("ndvi_mean") is not None
        ]
        if growing_ndvi:
            f.avg_ndvi_growing = sum(growing_ndvi) / len(growing_ndvi)
        if mature_ndvi:
            f.avg_ndvi_mature = sum(mature_ndvi) / len(mature_ndvi)

    return f


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except (ValueError, AttributeError):
        return None


# ─── Yield estimation (rule-based) ──────────────────────────────


def estimate_yield(features: LifecycleFeatures) -> YieldEstimate:
    """
    Yield estimation بقواعد agronomic.

    الـscore يبدأ من ١.٠ (potential كامل) ثمّ يُخفَّض بناءً على stress events.
    الـconfidence يعتمد على مدى توفّر البيانات (NDVI, lab samples, history).
    """
    crop = features.crop.lower()
    target = CROP_TARGET_YIELDS.get(crop)
    if not target:
        return YieldEstimate(
            field_id=features.field_id,
            crop=crop,
            estimated_yield_kg_ha=0,
            yield_score=0,
            confidence=0,
            stress_level=StressLevel.NONE,
            rationale_ar=f"المحصول '{crop}' غير معروف في قاعدة المعرفة",
            created_at=_now_iso(),
        )

    yield_score = 1.0
    contributors: list[str] = []
    warnings: list[str] = []
    confidence_factors: list[float] = []

    # ١. Moisture stress (penalty)
    stress_penalty = features.moisture_stress_events * 0.04
    if stress_penalty > 0:
        yield_score -= stress_penalty
        contributors.append(
            f"−{stress_penalty:.0%} بسبب {features.moisture_stress_events} حالات إجهاد مائي"
        )

    # ٢. Drought streak (penalty if long)
    if features.drought_streak_days > 7:
        drought_penalty = min(0.20, (features.drought_streak_days - 7) * 0.02)
        yield_score -= drought_penalty
        contributors.append(
            f"−{drought_penalty:.0%} بسبب فترة جفاف ({features.drought_streak_days} يوم بلا ري)"
        )
        if features.drought_streak_days > 14:
            warnings.append(
                f"فترة جفاف طويلة جدّاً ({features.drought_streak_days} يوم) — الإنتاج قد يكون أقلّ كثيراً"
            )

    # ٣. Pest alerts (penalty)
    if features.pest_alerts > 0:
        pest_penalty = min(0.15, features.pest_alerts * 0.05)
        yield_score -= pest_penalty
        contributors.append(f"−{pest_penalty:.0%} بسبب {features.pest_alerts} تنبيهات آفات/أمراض")

    # ٤. Growing duration (anomaly detection)
    # صدق: لا نطبّق فحص المدّة إلّا لمحصول معروف مدّته. الأشجار المعمّرة
    # وغير المعروفة لا مدّة "نموذجيّة" لها — رقم افتراضي يولّد تحذيرات كاذبة.
    typical = vegetative_growing_days(crop)
    if typical and features.days_in_growing > 0:
        ratio = features.days_in_growing / typical
        if ratio < 0.7:
            yield_score -= 0.15
            warnings.append(
                f"فترة النموّ قصيرة جدّاً ({features.days_in_growing} مقابل {typical} يوم متوقّع)"
            )
        elif ratio > 1.3:
            yield_score -= 0.08
            contributors.append(
                f"−٨٪ تأخّر في النضج ({features.days_in_growing} مقابل {typical} يوم)"
            )

    # ٥. NDVI bonus/penalty
    if features.avg_ndvi_growing is not None:
        confidence_factors.append(0.85)  # NDVI متاح → ثقة أعلى
        if features.avg_ndvi_growing > 0.65:
            yield_score += 0.05
            contributors.append(f"+٥٪ NDVI ممتاز في النموّ ({features.avg_ndvi_growing:.2f})")
        elif features.avg_ndvi_growing < 0.45:
            yield_score -= 0.10
            contributors.append(f"−١٠٪ NDVI منخفض ({features.avg_ndvi_growing:.2f})")

    # ٦. Irrigation regularity bonus
    if features.irrigation_count >= 5 and features.moisture_stress_events == 0:
        yield_score += 0.03
        contributors.append("+٣٪ ري منتظم بدون إجهاد")

    # ٧. Rain compensation
    if features.rain_events > 3:
        yield_score += 0.02
        contributors.append(f"+٢٪ أمطار مساعدة ({features.rain_events} أحداث)")

    # Clamp
    yield_score = max(0.20, min(1.10, yield_score))

    estimated_kg_ha = target * yield_score

    # Stress level classification
    if features.moisture_stress_events >= 8 or features.drought_streak_days > 21:
        stress_level = StressLevel.CRITICAL
    elif features.moisture_stress_events >= 5 or features.drought_streak_days > 14:
        stress_level = StressLevel.HIGH
    elif features.moisture_stress_events >= 3:
        stress_level = StressLevel.MEDIUM
    elif features.moisture_stress_events >= 1:
        stress_level = StressLevel.LOW
    else:
        stress_level = StressLevel.NONE

    # Confidence calculation
    # Base 0.5، يرتفع بـNDVI + history، ينخفض بـmissing data
    base_confidence = 0.55
    if features.avg_ndvi_growing is not None:
        base_confidence += 0.15
    if features.avg_ndvi_mature is not None:
        base_confidence += 0.10
    if features.days_in_growing > 0:
        base_confidence += 0.10
    if features.irrigation_count > 0:
        base_confidence += 0.05
    confidence = min(0.92, base_confidence)  # cap عند ٩٢٪ — لا "100% confident" بدون ground truth

    rationale = (
        f"تقدير الإنتاج: {estimated_kg_ha:.0f} kg/ha من {target} (نسبة {yield_score:.0%}). "
        f"مستوى الإجهاد: {stress_level.value}. "
        f"الثقة: {confidence:.0%} — "
        + ("بيانات جيّدة" if confidence > 0.75 else "بيانات محدودة، تحقّق ميدانياً")
    )

    return YieldEstimate(
        field_id=features.field_id,
        crop=crop,
        estimated_yield_kg_ha=round(estimated_kg_ha, 0),
        yield_score=round(yield_score, 3),
        confidence=round(confidence, 2),
        stress_level=stress_level,
        rationale_ar=rationale,
        contributors=contributors,
        warnings=warnings,
        created_at=_now_iso(),
    )


# ─── Anomaly detection (simple) ─────────────────────────────────


@dataclass
class Anomaly:
    field_id: str
    type: str
    severity: str  # "low" | "medium" | "high"
    message_ar: str
    suggested_action_ar: str


def detect_anomalies(features: LifecycleFeatures) -> list[Anomaly]:
    """يكشف الـpatterns الخطيرة. لا "AI" — قواعد مباشرة."""
    anomalies: list[Anomaly] = []

    # Chronic water stress
    if features.moisture_stress_events >= 5:
        anomalies.append(
            Anomaly(
                field_id=features.field_id,
                type="water_stress_chronic",
                severity="high",
                message_ar=f"إجهاد مائي مزمن: {features.moisture_stress_events} حالة في الموسم",
                suggested_action_ar="راجع جدولة الري + تحقّق من نظام الري (تسرّب؟ توزيع غير متساوٍ؟)",
            )
        )

    # Long drought
    if features.drought_streak_days > 14:
        anomalies.append(
            Anomaly(
                field_id=features.field_id,
                type="drought_streak",
                severity="high",
                message_ar=f"فترة جفاف طويلة: {features.drought_streak_days} يوم بلا ري",
                suggested_action_ar="ريّ عاجل قبل وصول الإجهاد إلى مرحلة لا رجعة فيها",
            )
        )

    # Pest pressure
    if features.pest_alerts >= 3:
        anomalies.append(
            Anomaly(
                field_id=features.field_id,
                type="pest_pressure",
                severity="medium",
                message_ar=f"ضغط آفات/أمراض متكرّر: {features.pest_alerts} تنبيهات",
                suggested_action_ar="جولة scouting ميدانيّة، أو استشارة مهندس زراعي",
            )
        )

    # Delayed maturity
    typical = vegetative_growing_days(features.crop)
    if typical and features.days_in_growing > typical * 1.4:
        anomalies.append(
            Anomaly(
                field_id=features.field_id,
                type="delayed_maturity",
                severity="medium",
                message_ar=f"النموّ متأخّر: {features.days_in_growing} يوم بدلاً من {typical}",
                suggested_action_ar="تحقّق من النيتروجين + درجات الحرارة + المياه",
            )
        )

    return anomalies


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
