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
from datetime import UTC, date, datetime, timedelta
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
    # W0-11: لا دليل على الإجهاد المائي ⇒ مجهول، لا «لا إجهاد».
    UNKNOWN = "unknown"


@dataclass
class LifecycleFeatures:
    """Features مُستخلَصة من lifecycle events لحقل.

    W0-11 (``fields-4``/``crop-5``): كلّ مدخل اختياريّ و``None`` يعني **مجهول**، لا صفر.
    كانت القيم الافتراضيّة أصفاراً، فطلبٌ بلا أيّ دليل يُقرأ «صفر إجهاد، صفر آفات» ويُعطي
    العائد المستهدف كاملاً. الصفر الآن ملاحظةٌ مُعلَنة («رُصد ولا شيء»)، والغياب غياب.
    """

    field_id: str
    crop: str
    days_in_growing: int | None = None
    irrigation_count: int | None = None
    moisture_stress_events: int | None = None
    pest_alerts: int | None = None
    fertilizer_applications: int | None = None
    avg_ndvi_growing: float | None = None
    avg_ndvi_mature: float | None = None
    drought_streak_days: int | None = None  # أطول فترة بدون ري
    rain_events: int | None = None


# مدخلات تصف حالة المحصول فتستطيع خفض التقدير. بلا واحدٍ منها على الأقلّ لا تقدير:
# البقيّة (المدّة، عدد الريّات، الأمطار) لا تقول شيئاً عن إجهاد أو آفة أو غطاء نباتيّ.
YIELD_CONDITION_EVIDENCE: tuple[str, ...] = (
    "moisture_stress_events",
    "drought_streak_days",
    "pest_alerts",
    "avg_ndvi_growing",
)


@dataclass
class YieldEstimate:
    field_id: str
    crop: str
    estimated_yield_kg_ha: float | None  # None = no estimate, NOT observed crop failure.
    yield_score: float | None  # 0-1 (نسبيّ للحقل الأمثل)؛ None = لا تقدير (W0-11)
    confidence: float  # 0-1
    stress_level: StressLevel
    rationale_ar: str
    contributors: list[str] = field(default_factory=list)  # ما رفع/خفّض التقدير
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""
    yield_status: str = "estimated"
    # مدخلات حالة المحصول التي لم تصل (لم تُعامَل كصفر) — W0-11.
    missing_inputs: list[str] = field(default_factory=list)


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
    except Exception:  # noqa: BLE001 — بطاقة محصول غائبة/معطوبة ⇒ لا تقدير (degrade صادق)
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
    if events:
        # سجلّ أحداث غير فارغ هو الدليل: غياب صنفٍ فيه «رُصد ولا شيء» فيُعدّ صفراً.
        # سجلّ فارغ لا يقول شيئاً ⇒ تبقى العدّادات None (مجهول) — W0-11.
        f.irrigation_count = 0
        f.moisture_stress_events = 0
        f.pest_alerts = 0
        f.fertilizer_applications = 0
        f.rain_events = 0

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

    if events:
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


def yield_crop_key(raw: str | None) -> str:
    """مفتاح المحصول في جداول هذا الملف: «قمح»/"Wheat"/" wheat " ⇒ "wheat".

    المفتاح الموجود حرفيّاً يبقى كما هو؛ وإلّا يُحلّ بالهويّة الزراعيّة المشتركة
    (resolve_crop_id). "maize" الكنسيّ يُطابَق على مفتاح "corn" التاريخيّ هنا.
    غير المعروف يعود مُقلَّماً بأحرف صغيرة فيبقى «غير معروف» لا صفراً.
    """
    from core.season_phenology import resolve_crop_id

    original = (raw or "").strip().lower()
    if original in CROP_TARGET_YIELDS:
        return original
    resolved = resolve_crop_id(raw) or original
    return "corn" if resolved == "maize" else resolved


def estimate_yield(features: LifecycleFeatures) -> YieldEstimate:
    """
    Yield estimation بقواعد agronomic.

    الـscore يبدأ من ١.٠ (potential كامل) ثمّ يُخفَّض بناءً على stress events.
    الـconfidence يعتمد على مدى توفّر البيانات (NDVI, lab samples, history).
    """
    crop = yield_crop_key(features.crop)
    target = CROP_TARGET_YIELDS.get(crop)
    if target is None:
        return YieldEstimate(
            field_id=features.field_id,
            crop=crop,
            estimated_yield_kg_ha=None,
            yield_score=0,
            confidence=0,
            stress_level=StressLevel.NONE,
            rationale_ar=f"المحصول '{crop}' غير معروف في قاعدة المعرفة — لا تقدير غلّة",
            warnings=["unsupported_crop_no_yield_estimate"],
            created_at=_now_iso(),
            yield_status="unavailable_unrecognized_crop",
        )

    missing = [name for name in YIELD_CONDITION_EVIDENCE if getattr(features, name) is None]
    if len(missing) == len(YIELD_CONDITION_EVIDENCE):
        # W0-11: لا دليل على حالة المحصول ⇒ لا تقدير. كان الغياب يُقرأ صفر إجهاد فيُرجِع
        # العائد المستهدف كاملاً بثقة 55٪ — رقمٌ يبدو مقيساً وهو افتراض.
        return YieldEstimate(
            field_id=features.field_id,
            crop=crop,
            estimated_yield_kg_ha=None,
            yield_score=None,
            confidence=0,
            stress_level=StressLevel.UNKNOWN,
            rationale_ar=(
                "لا أدلّة على حالة المحصول (إجهاد مائي، جفاف، آفات، NDVI) — "
                "لا تقدير غلّة. الغياب ليس صفر إجهاد."
            ),
            warnings=["insufficient_evidence_no_yield_estimate"],
            created_at=_now_iso(),
            yield_status="unavailable_insufficient_evidence",
            missing_inputs=missing,
        )

    moisture = features.moisture_stress_events
    drought = features.drought_streak_days
    pests = features.pest_alerts
    days = features.days_in_growing
    irrigations = features.irrigation_count
    rains = features.rain_events

    yield_score = 1.0
    contributors: list[str] = []
    warnings: list[str] = []
    confidence_factors: list[float] = []

    # ١. Moisture stress (penalty)
    stress_penalty = (moisture or 0) * 0.04
    if stress_penalty > 0:
        yield_score -= stress_penalty
        contributors.append(f"−{stress_penalty:.0%} بسبب {moisture} حالات إجهاد مائي")

    # ٢. Drought streak (penalty if long)
    if drought is not None and drought > 7:
        drought_penalty = min(0.20, (drought - 7) * 0.02)
        yield_score -= drought_penalty
        contributors.append(f"−{drought_penalty:.0%} بسبب فترة جفاف ({drought} يوم بلا ري)")
        if drought > 14:
            warnings.append(f"فترة جفاف طويلة جدّاً ({drought} يوم) — الإنتاج قد يكون أقلّ كثيراً")

    # ٣. Pest alerts (penalty)
    if pests is not None and pests > 0:
        pest_penalty = min(0.15, pests * 0.05)
        yield_score -= pest_penalty
        contributors.append(f"−{pest_penalty:.0%} بسبب {pests} تنبيهات آفات/أمراض")

    # ٤. Growing duration (anomaly detection)
    # صدق: لا نطبّق فحص المدّة إلّا لمحصول معروف مدّته. الأشجار المعمّرة
    # وغير المعروفة لا مدّة "نموذجيّة" لها — رقم افتراضي يولّد تحذيرات كاذبة.
    typical = vegetative_growing_days(crop)
    if typical and days is not None and days > 0:
        ratio = days / typical
        if ratio < 0.7:
            yield_score -= 0.15
            warnings.append(f"فترة النموّ قصيرة جدّاً ({days} مقابل {typical} يوم متوقّع)")
        elif ratio > 1.3:
            yield_score -= 0.08
            contributors.append(f"−٨٪ تأخّر في النضج ({days} مقابل {typical} يوم)")

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
    # المكافأة تشترط صفر إجهاد **مرصوداً**؛ الإجهاد المجهول لا يمنح «ري منتظم بدون إجهاد».
    if irrigations is not None and irrigations >= 5 and moisture == 0:
        yield_score += 0.03
        contributors.append("+٣٪ ري منتظم بدون إجهاد")

    # ٧. Rain compensation
    if rains is not None and rains > 3:
        yield_score += 0.02
        contributors.append(f"+٢٪ أمطار مساعدة ({rains} أحداث)")

    # Clamp
    yield_score = max(0.20, min(1.10, yield_score))

    estimated_kg_ha = target * yield_score

    # Stress level classification — يُقرأ ممّا رُصد فقط. «لا إجهاد» يحتاج المدخلين
    # المائيّين كليهما مرصودين؛ وإلّا فالمستوى مجهول ما لم يُثبت ما رُصد إجهاداً.
    m = moisture or 0
    d = drought or 0
    if m >= 8 or d > 21:
        stress_level = StressLevel.CRITICAL
    elif m >= 5 or d > 14:
        stress_level = StressLevel.HIGH
    elif m >= 3:
        stress_level = StressLevel.MEDIUM
    elif m >= 1:
        stress_level = StressLevel.LOW
    elif moisture is not None and drought is not None:
        stress_level = StressLevel.NONE
    else:
        stress_level = StressLevel.UNKNOWN

    # Confidence calculation
    # Base 0.5، يرتفع بـNDVI + history، ينخفض بـmissing data
    base_confidence = 0.55
    if features.avg_ndvi_growing is not None:
        base_confidence += 0.15
    if features.avg_ndvi_mature is not None:
        base_confidence += 0.10
    if days is not None and days > 0:
        base_confidence += 0.10
    if irrigations is not None and irrigations > 0:
        base_confidence += 0.05
    confidence = min(0.92, base_confidence)  # cap عند ٩٢٪ — لا "100% confident" بدون ground truth

    rationale = (
        f"تقدير الإنتاج: {estimated_kg_ha:.0f} kg/ha من {target} (نسبة {yield_score:.0%}). "
        f"مستوى الإجهاد: {stress_level.value}. "
        f"الثقة: {confidence:.0%} — "
        + ("بيانات جيّدة" if confidence > 0.75 else "بيانات محدودة، تحقّق ميدانياً")
    )
    if missing:
        rationale += f" مدخلات مجهولة لم تُعامَل كصفر: {', '.join(missing)}."

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
        missing_inputs=missing,
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
    # المجهول (None) لا يُكشَف منه شذوذ — ولا يُدّعى غيابه.
    moisture = features.moisture_stress_events or 0
    drought = features.drought_streak_days or 0
    pests = features.pest_alerts or 0
    days = features.days_in_growing or 0

    if moisture >= 5:
        anomalies.append(
            Anomaly(
                field_id=features.field_id,
                type="water_stress_chronic",
                severity="high",
                message_ar=f"إجهاد مائي مزمن: {moisture} حالة في الموسم",
                suggested_action_ar="راجع جدولة الري + تحقّق من نظام الري (تسرّب؟ توزيع غير متساوٍ؟)",
            )
        )

    # Long drought
    if drought > 14:
        anomalies.append(
            Anomaly(
                field_id=features.field_id,
                type="drought_streak",
                severity="high",
                message_ar=f"فترة جفاف طويلة: {drought} يوم بلا ري",
                suggested_action_ar="ريّ عاجل قبل وصول الإجهاد إلى مرحلة لا رجعة فيها",
            )
        )

    # Pest pressure
    if pests >= 3:
        anomalies.append(
            Anomaly(
                field_id=features.field_id,
                type="pest_pressure",
                severity="medium",
                message_ar=f"ضغط آفات/أمراض متكرّر: {pests} تنبيهات",
                suggested_action_ar="جولة scouting ميدانيّة، أو استشارة مهندس زراعي",
            )
        )

    # Delayed maturity
    typical = vegetative_growing_days(yield_crop_key(features.crop))
    if typical and days > typical * 1.4:
        anomalies.append(
            Anomaly(
                field_id=features.field_id,
                type="delayed_maturity",
                severity="medium",
                message_ar=f"النموّ متأخّر: {days} يوم بدلاً من {typical}",
                suggested_action_ar="تحقّق من النيتروجين + درجات الحرارة + المياه",
            )
        )

    return anomalies


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ═══ W1-08: ميزات التقدير من الخادم (أحداث + NDVI + طقس) ═══════════════
# الدوالّ النقيّة أوّلاً؛ قراءات القاعدة وraster والطقس في آخر القسم باستيراد كسول، فيبقى
# ما فوقه بلا قاعدة ولا شبكة. (في هذا الملفّ لا في وحدة جديدة: ميزانية وحدات المنصّة لا تنمو.)
#
# W1-08 (``fields-4``/``crop-5``): كانت ميزات تقدير العائد تأتي من جسم الطلب وحده، و
# ``build_features_from_events`` بلا مستدعٍ. هنا تُجمَع من مصادر الخادم المالكة:
#
#   • الأحداث المخزَّنة (جدول ``events``، مالكه هذه الخدمة) لموسم الحقل المزروع، مُترجَمةً إلى
#     مفردات ``build_features_from_events``؛
#   • سلسلة NDVI من واجهة raster (``raster_service_client.get_field_timeseries``)؛
#   • الطقس التاريخيّ من مالك الطقس (``weather_service_client.get_weather_historical``)،
#     مُتحقَّقاً منه بـ``season_simulation.canonical_historical_days``.
#
# قيم الطلب **تجاوزاتٌ مُعلَنة** فقط: تُسجَّل في ``declared_overrides`` مع قيمة الخادم التي
# حلّت محلّها، ولا تختفي في الرقم.
#
# المبدأ: الغياب مجهول (W0-11). سجلّ ريٍّ بلا تنبيه آفة لا يرصد «صفر آفات»؛ فعدّاد الصنف
# يبقى ``None`` ما لم يوجد حدثٌ واحد على الأقلّ من صنفه. الصفر المرصود يُعلَن تجاوزاً.

# مدخلات التقدير التي يجوز للطلب تجاوزها (بإعلان).
OVERRIDABLE_INPUTS: tuple[str, ...] = (
    "days_in_growing",
    "irrigation_count",
    "moisture_stress_events",
    "pest_alerts",
    "fertilizer_applications",
    "avg_ndvi_growing",
    "drought_streak_days",
    "rain_events",
)

# يومٌ «مطير» يقطع فترة الجفاف: هطول ≥ 5 مم (عتبة المطر الفعّال الشائعة في FAO-56).
# ⚠ UNVALIDATED DEFAULT — needs agronomist review.
EFFECTIVE_RAIN_MM = 5.0
# سياسة جودة NDVI نفسها في مُركِّب الموسم التاريخيّ: الغيم المجهول ليس صفر غيم.
NDVI_MAX_CLOUD_PCT = 30.0

_MOISTURE_ALERT_TYPES = frozenset({"low_moisture", "water_stress", "drought"})
# تنبيهٌ يرصد آفة/مرضاً فعلاً. ``disease_risk`` تنبّؤٌ طقسيّ لا رصد، فلا يُعدّ.
_PEST_ALERT_TYPES = frozenset({"pest", "pest_detected", "pest_outbreak", "disease_detected"})

SOURCE_EVENTS = "server:events"
SOURCE_NDVI = "server:raster_ndvi"
SOURCE_WEATHER = "server:weather_history"
SOURCE_SEASON = "server:season_irrigation_type"
SOURCE_OVERRIDE = "request_override"
SOURCE_UNKNOWN = "unknown"


@dataclass
class SeasonWindow:
    season_id: str
    crop: str | None
    sowing_date: date
    end_date: date
    irrigation_type: str | None


@dataclass
class ServerYieldEvidence:
    features: LifecycleFeatures
    evidence_ids: list[str] = field(default_factory=list)
    input_sources: dict[str, str] = field(default_factory=dict)
    declared_overrides: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    window: dict[str, Any] | None = None

    def response_fields(self) -> dict[str, Any]:
        """حقول الاستجابة التي تجعل التقدير قابلاً للتتبّع: ما دخل، ومن أين، وما تُجووِز."""
        return {
            "evidence_ids": self.evidence_ids,
            "input_sources": self.input_sources,
            "declared_overrides": self.declared_overrides,
            "evidence_window": self.window,
            "evidence_warnings": self.warnings,
        }


# ─── ترجمة الأحداث المخزَّنة إلى مفردات المُستخرِج ─────────────────────


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    p = row.get("payload")
    if isinstance(p, str):
        import json

        try:
            p = json.loads(p)
        except (TypeError, ValueError):
            p = {}
    return p if isinstance(p, dict) else {}


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC).isoformat()
    return str(value or "")


def normalize_stored_event(row: dict[str, Any]) -> dict[str, Any] | None:
    """صفّ ``events`` ⇒ حدث بمفردات ``build_features_from_events``، أو None إن لم يُعنَ به.

    المطر لا يُقرأ من الأحداث: مصدره الوحيد هنا تاريخ الطقس (لا عدّ مزدوج).
    """
    etype = str(row.get("event_type") or "").lower()
    payload = _payload(row)
    mapped: str | None = None
    if etype == "operation.irrigation.completed":
        mapped = "operation.irrigation"
    elif etype == "operation.fertilizer.applied":
        mapped = "operation.fertilizer"
    elif etype == "weather.moisture.low" or "water_stress" in etype or "drought" in etype:
        mapped = "moisture.low"
    elif etype.startswith("pest.") or etype.startswith("disease."):
        mapped = etype
    elif etype == "alert.created":
        alert_type = str(payload.get("alert_type") or "").lower()
        if alert_type in _MOISTURE_ALERT_TYPES:
            mapped = "moisture.low"
        elif alert_type in _PEST_ALERT_TYPES or payload.get("pest_detected") is True:
            mapped = "pest.alert"
    elif etype == "lifecycle.transitioned" and payload.get("to_stage"):
        mapped = "lifecycle.transition"
    if mapped is None:
        return None
    return {
        "event_type": mapped,
        "timestamp": _iso(row.get("occurred_at")),
        "payload": payload,
        "event_id": str(row.get("event_id") or ""),
    }


def _category(mapped_type: str) -> str:
    if mapped_type == "operation.irrigation":
        return "irrigation"
    if mapped_type == "operation.fertilizer":
        return "fertilizer"
    if mapped_type == "moisture.low":
        return "moisture"
    if mapped_type.startswith("pest.") or mapped_type.startswith("disease."):
        return "pest"
    return "lifecycle"


# ─── NDVI من raster ───────────────────────────────────────────────────


def ndvi_history_from_points(
    points: list[dict[str, Any]], window: SeasonWindow, crop: str
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """نقاط raster ⇒ تاريخ NDVI مُرحَّل (GROWING/MATURE) + معرّفات الأدلّة + تحذيرات.

    المرحلة من أيّام النموّ الخضريّ للمحصول منذ البذار؛ محصولٌ بلا مدّة معروفة لا يُرحَّل
    فلا يُستعمل NDVI (لا مرحلة مُفترَضة). نقطةٌ بلا غيم مقيس أو بغيم > 30٪ تُسقَط.
    """
    if not points:
        return [], [], []
    veg_days = vegetative_growing_days(yield_crop_key(crop))
    if not veg_days:
        return [], [], ["ndvi_unstaged_unknown_crop_duration"]
    history: list[dict[str, Any]] = []
    ids: list[str] = []
    dropped = 0
    for p in points:
        day_s = str(p.get("datetime") or "")[:10]
        try:
            day = date.fromisoformat(day_s)
        except ValueError:
            continue
        if day < window.sowing_date or day > window.end_date:
            continue
        mean = p.get("mean")
        cloud = p.get("cloud_pct")
        if mean is None or cloud is None or float(cloud) > NDVI_MAX_CLOUD_PCT:
            dropped += 1
            continue
        stage = "GROWING" if (day - window.sowing_date).days <= veg_days else "MATURE"
        history.append({"date": day_s, "ndvi_mean": float(mean), "stage": stage})
        ids.append(f"raster:ndvi:{p.get('scene_id') or day_s}")
    warnings = [f"ndvi_points_dropped_unqualified:{dropped}"] if dropped else []
    return history, ids, warnings


# ─── الطقس التاريخيّ: أمطار وفترة جفاف ─────────────────────────────────


def weather_water_inputs(
    rain_by_day: list[float | None] | None,
    window_start: date,
    irrigation_days: set[date],
    irrigation_type: str | None,
) -> tuple[int | None, int | None]:
    """(rain_events, drought_streak_days) من سلسلة هطول يوميّة كاملة، أو None للمجهول.

    يومٌ بهطول مجهول يجعل السلسلة غير صالحة (لا يُقرأ صفراً). فترة الجفاف = أطول تتابع
    أيّام بلا مطر فعّال ولا ريّ مسجَّل، وتُحسب فقط إن عُرف الريّ: حقلٌ بعليّ (rainfed)،
    أو حقلٌ مرويّ له سجلّ ريّ. حقلٌ مرويّ بلا سجلّ ريّ ⇒ الجفاف مجهول.
    """
    if not rain_by_day or any(v is None for v in rain_by_day):
        return None, None
    rain_events = sum(1 for v in rain_by_day if v is not None and v >= EFFECTIVE_RAIN_MM)
    rainfed = (irrigation_type or "").lower() == "rainfed"
    if not rainfed and not irrigation_days:
        return rain_events, None
    longest = current = 0
    for i, v in enumerate(rain_by_day):
        day = window_start + timedelta(days=i)
        wet = (v is not None and v >= EFFECTIVE_RAIN_MM) or day in irrigation_days
        current = 0 if wet else current + 1
        longest = max(longest, current)
    return rain_events, longest


# ─── التجميع (نقيّ) ────────────────────────────────────────────────────


def assemble_server_features(
    field_id: str,
    crop: str,
    window: SeasonWindow | None,
    event_rows: list[dict[str, Any]],
    ndvi_points: list[dict[str, Any]],
    weather_rain_mm: list[float | None] | None,
    weather_evidence_id: str | None,
) -> ServerYieldEvidence:
    """يبني ``LifecycleFeatures`` من مصادر الخادم وحدها. نقيّ: لا قاعدة ولا شبكة."""
    if window is None:
        return ServerYieldEvidence(
            features=LifecycleFeatures(field_id=field_id, crop=crop.lower()),
            warnings=["no_sown_season_no_server_evidence"],
            input_sources=dict.fromkeys(OVERRIDABLE_INPUTS, SOURCE_UNKNOWN),
        )

    mapped = [m for m in (normalize_stored_event(r) for r in event_rows) if m is not None]
    ndvi_history, ndvi_ids, warnings = ndvi_history_from_points(ndvi_points, window, crop)
    features = build_features_from_events(field_id, crop, mapped, ndvi_history=ndvi_history)

    counts: dict[str, int] = {}
    evidence_ids: list[str] = []
    irrigation_days: set[date] = set()
    for ev in mapped:
        cat = _category(ev["event_type"])
        counts[cat] = counts.get(cat, 0) + 1
        if ev["event_id"]:
            evidence_ids.append(f"event:{ev['event_id']}")
        if cat == "irrigation" and ev["timestamp"]:
            try:
                irrigation_days.add(datetime.fromisoformat(ev["timestamp"]).date())
            except ValueError:
                pass

    sources = dict.fromkeys(OVERRIDABLE_INPUTS, SOURCE_UNKNOWN)
    # عدّاد صنفٍ بلا حدثٍ واحد منه مجهول، لا صفر: سجلّ الأحداث لا يرصد إلّا ما سُجّل.
    for name, cat in (
        ("pest_alerts", "pest"),
        ("moisture_stress_events", "moisture"),
        ("fertilizer_applications", "fertilizer"),
    ):
        if counts.get(cat):
            sources[name] = SOURCE_EVENTS
        else:
            setattr(features, name, None)
    rainfed = (window.irrigation_type or "").lower() == "rainfed"
    if counts.get("irrigation"):
        sources["irrigation_count"] = SOURCE_EVENTS
    elif rainfed:
        features.irrigation_count = 0  # بعليّ مُعلَن في الموسم: لا ريّ بالتعريف.
        sources["irrigation_count"] = SOURCE_SEASON
    else:
        features.irrigation_count = None
    if features.days_in_growing is not None:
        sources["days_in_growing"] = SOURCE_EVENTS

    rain_events, drought = weather_water_inputs(
        weather_rain_mm,
        window.sowing_date,
        irrigation_days,
        window.irrigation_type,
    )
    features.rain_events = rain_events
    features.drought_streak_days = drought
    if rain_events is not None:
        sources["rain_events"] = SOURCE_WEATHER
    if drought is not None:
        sources["drought_streak_days"] = SOURCE_WEATHER
    if (rain_events is not None or drought is not None) and weather_evidence_id:
        evidence_ids.append(weather_evidence_id)
    if weather_rain_mm is None:
        warnings.append("weather_history_unavailable")

    if features.avg_ndvi_growing is not None:
        sources["avg_ndvi_growing"] = SOURCE_NDVI
        evidence_ids.extend(ndvi_ids)
    elif not ndvi_points:
        warnings.append("ndvi_series_unavailable")

    return ServerYieldEvidence(
        features=features,
        evidence_ids=evidence_ids,
        input_sources=sources,
        warnings=warnings,
        window={
            "season_id": window.season_id,
            "start": window.sowing_date.isoformat(),
            "end": window.end_date.isoformat(),
            "irrigation_type": window.irrigation_type,
        },
    )


def apply_declared_overrides(evidence: ServerYieldEvidence, overrides: dict[str, Any]) -> None:
    """يُطبّق قيم الطلب تجاوزاتٍ مُعلَنة: كلّ تجاوز يُسجَّل مع قيمة الخادم التي استبدلها."""
    for name in OVERRIDABLE_INPUTS:
        if name not in overrides or overrides[name] is None:
            continue
        declared = overrides[name]
        server_value = getattr(evidence.features, name)
        evidence.declared_overrides.append(
            {
                "input": name,
                "declared_value": declared,
                "server_value": server_value,
                "server_source": evidence.input_sources.get(name, SOURCE_UNKNOWN),
            }
        )
        setattr(evidence.features, name, declared)
        evidence.input_sources[name] = SOURCE_OVERRIDE


# ─── التحميل (قاعدة + raster + طقس) ───────────────────────────────────


def _season_crop(crops: Any) -> str | None:
    if isinstance(crops, str):
        import json

        try:
            crops = json.loads(crops)
        except (TypeError, ValueError):
            return None
    if isinstance(crops, list):
        names = [str(c).strip() for c in crops if str(c).strip()]
        if len(names) == 1:
            return names[0]
    return None


@dataclass
class LoadedSeason:
    """ما قُرئ من القاعدة داخل ``tenant_connection`` (RLS) قبل أيّ نداء شبكة."""

    today: date
    window: SeasonWindow | None
    event_rows: list[dict[str, Any]]
    location: tuple[float, float] | None


async def load_season_and_events(conn, field_id: str, today: date | None = None) -> LoadedSeason:
    """قراءة القاعدة (داخل ``tenant_connection`` — RLS): آخر موسم مزروع + أحداثه + الموقع."""
    today = today or datetime.now(UTC).date()
    srow = await conn.fetchrow(
        "SELECT season_id, crops, sowing_date, season_end, irrigation_type "
        "FROM seasons WHERE field_id = $1 AND sowing_date IS NOT NULL AND sowing_date <= $2 "
        "ORDER BY sowing_date DESC, created_at DESC LIMIT 1",
        field_id,
        today,
    )
    frow = await conn.fetchrow("SELECT lat, lon FROM fields WHERE field_id = $1", field_id)
    location = None
    if frow is not None and frow["lat"] is not None and frow["lon"] is not None:
        location = (float(frow["lat"]), float(frow["lon"]))
    if srow is None:
        return LoadedSeason(today, None, [], location)
    end = srow["season_end"] if srow["season_end"] is not None else today
    end = min(end, today)
    window = SeasonWindow(
        season_id=str(srow["season_id"]),
        crop=_season_crop(srow["crops"]),
        sowing_date=srow["sowing_date"],
        end_date=end,
        irrigation_type=srow["irrigation_type"],
    )
    rows = await conn.fetch(
        """
        SELECT event_id, event_type, payload, occurred_at
        FROM events
        WHERE (entity_id = $1 OR payload->>'field_id' = $1)
          AND occurred_at >= $2::date AND occurred_at < ($3::date + 1)
        ORDER BY occurred_at
        LIMIT 5000
        """,
        field_id,
        window.sowing_date,
        window.end_date,
    )
    return LoadedSeason(today, window, [dict(r) for r in rows], location)


async def load_ndvi_points(field_id: str, tenant_id: str) -> list[dict[str, Any]]:
    from api.raster_service_client import get_field_timeseries

    return await get_field_timeseries(field_id, tenant_id=tenant_id, index="ndvi")


async def load_weather_rain(
    location: tuple[float, float] | None, start: date, end: date, tenant_id: str
) -> tuple[list[float | None] | None, str | None]:
    """هطولٌ يوميّ مُتحقَّق من مالك الطقس للنافذة كاملةً، أو (None, None) عند التعذّر."""
    if location is None or end < start:
        return None, None
    from api.season_simulation import canonical_historical_days
    from api.weather_service_client import get_weather_historical

    try:
        archive = await get_weather_historical(
            location[0],
            location[1],
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            tenant_id=tenant_id,
        )
        days = canonical_historical_days(archive, start=start, end=end)
    except Exception:  # noqa: BLE001 — تعذّر الطقس ⇒ مجهول (لا صفر مطر ولا جفاف مُفترَض)
        logger.warning("yield: weather history unavailable", exc_info=True)
        return None, None
    return [d.rain_mm for d in days], f"weather:{archive.get('source_snapshot_id')}"


async def collect_server_evidence(
    field_id: str, overrides: dict[str, Any], loaded: LoadedSeason, tenant_id: str
) -> ServerYieldEvidence:
    """يجمع الأدلّة: NDVI من raster وطقس الموسم (حتّى أمس) خارج معاملة القاعدة، ثمّ التجميع
    النقيّ، ثمّ تجاوزات الطلب المُعلَنة. لا محصول من الموسم ولا من الطلب ⇒ 422."""
    from fastapi import HTTPException

    window = loaded.window
    declared_crop = overrides.get("crop")
    crop = declared_crop or (window.crop if window is not None else None)
    if not crop:
        raise HTTPException(
            status_code=422,
            detail="لا محصول معروف للحقل (لا موسم مزروع بمحصول واحد ولا محصول مُعلَن في الطلب).",
        )
    ndvi_points: list[dict[str, Any]] = []
    rain_mm: list[float | None] | None = None
    weather_id: str | None = None
    if window is not None:
        ndvi_points = await load_ndvi_points(field_id, tenant_id)
        weather_end = min(window.end_date, loaded.today - timedelta(days=1))
        rain_mm, weather_id = await load_weather_rain(
            loaded.location, window.sowing_date, weather_end, tenant_id
        )
    evidence = assemble_server_features(
        field_id, crop, window, loaded.event_rows, ndvi_points, rain_mm, weather_id
    )
    if declared_crop and window is not None and window.crop and declared_crop != window.crop:
        evidence.declared_overrides.append(
            {"input": "crop", "declared_value": declared_crop, "server_value": window.crop}
        )
    apply_declared_overrides(evidence, overrides)
    return evidence
