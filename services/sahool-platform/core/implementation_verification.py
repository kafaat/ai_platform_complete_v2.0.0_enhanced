"""
sahool_core.implementation_verification
=======================================
التحقّق من تنفيذ التوصية — هل نُفّذت فعلاً؟ بثلاثة مستويات (الوثيقة، س5).

يكمّل farmer_agency (الذي يسجّل القبول/الرفض) بطبقة "هل حدث التنفيذ؟":
  ١. سلبي (Passive): النواة تسأل بعد مدّة "هل نفّذت؟" → نعم/لا/تأجيل.
  ٢. إيجابي (Active): صورة/GPS تؤكّد الحضور (دون قياس فيزيائي).
  ٣. فيزيائي (Physical): حسّاس يؤكّد الأثر (رطوبة ارتفعت بعد الري).

المبدأ: التحقّق درجات لا ثنائي. غياب التحقّق ليس فشلاً — "غير مؤكّد"
حالة صادقة (الصمت قرار). التحقّق الفيزيائي وحده يؤكّد الأثر؛ السلبي
يؤكّد النيّة لا الأثر. لا نخلط بينهما.

لا يخترع بيانات: بلا إشارة من المزارع/الحسّاس → UNCONFIRMED (لا "نُفّذ").
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VerificationLevel(str, Enum):
    PASSIVE = "passive"     # سؤال المزارع
    ACTIVE = "active"       # صورة/GPS
    PHYSICAL = "physical"   # حسّاس


class ImplementationStatus(str, Enum):
    IMPLEMENTED = "implemented"     # مؤكّد (فيزيائياً أو إيجابياً)
    CLAIMED = "claimed"             # المزارع قال نعم (سلبي — نيّة لا أثر)
    REJECTED = "rejected"           # لم يُنفّذ
    DEFERRED = "deferred"           # أُجّل
    UNCONFIRMED = "unconfirmed"     # لا إشارة — غير مؤكّد (صادق)
    INSUFFICIENT = "insufficient"   # نُفّذ جزئياً (الأثر أقلّ من المطلوب)


@dataclass
class VerificationResult:
    status: ImplementationStatus
    level: VerificationLevel | None
    confidence: str               # none/low/medium/high
    note_ar: str
    learn_signal: str = ""        # إشارة للتعلّم (سبب الرفض، إلخ)


def verify_passive(farmer_response: str | None,
                   why_rejected: str | None = None) -> VerificationResult:
    """المستوى السلبي: سؤال المزارع. يؤكّد النيّة لا الأثر."""
    if farmer_response is None:
        return VerificationResult(
            ImplementationStatus.UNCONFIRMED, None, "none",
            "لم يُسأل المزارع بعد — غير مؤكّد")
    r = farmer_response.strip().lower()
    if r in ("yes", "نعم", "true"):
        return VerificationResult(
            ImplementationStatus.CLAIMED, VerificationLevel.PASSIVE, "low",
            "المزارع أفاد بالتنفيذ — نيّة مؤكّدة لا أثر مقيس (سقف منخفض)")
    if r in ("no", "لا", "false"):
        return VerificationResult(
            ImplementationStatus.REJECTED, VerificationLevel.PASSIVE, "medium",
            "المزارع لم يُنفّذ", learn_signal=why_rejected or "(لم يُذكر سبب)")
    if r in ("later", "تأجيل", "deferred"):
        return VerificationResult(
            ImplementationStatus.DEFERRED, VerificationLevel.PASSIVE, "medium",
            "أُجّل التنفيذ — تذكير لاحق")
    return VerificationResult(
        ImplementationStatus.UNCONFIRMED, None, "none",
        f"رد غير مفهوم ({farmer_response}) — غير مؤكّد")


def verify_physical(metric_before: float | None, metric_after: float | None,
                    expected_delta: float, tolerance: float = 0.5) -> VerificationResult:
    """المستوى الفيزيائي: حسّاس يؤكّد الأثر. الأقوى (يقيس لا يسأل).

    مثال: ري 40مم → رطوبة يجب أن ترتفع. before=18%, after=25% → نُفّذ.
    قياس الأثر الفعلي، لا ادّعاء النيّة."""
    if metric_before is None or metric_after is None:
        return VerificationResult(
            ImplementationStatus.UNCONFIRMED, None, "none",
            "لا قراءة حسّاس — غير مؤكّد (لا اختراع)")
    actual_delta = metric_after - metric_before
    if actual_delta >= expected_delta - tolerance:
        return VerificationResult(
            ImplementationStatus.IMPLEMENTED, VerificationLevel.PHYSICAL, "high",
            f"الأثر مؤكّد فيزيائياً (تغيّر {actual_delta:.1f}، متوقّع {expected_delta})")
    if actual_delta > tolerance:
        return VerificationResult(
            ImplementationStatus.INSUFFICIENT, VerificationLevel.PHYSICAL, "high",
            f"نُفّذ جزئياً (تغيّر {actual_delta:.1f} < متوقّع {expected_delta}) — "
            "قد يحتاج إكمالاً")
    return VerificationResult(
        ImplementationStatus.REJECTED, VerificationLevel.PHYSICAL, "high",
        f"لا أثر فيزيائي (تغيّر {actual_delta:.1f}) — لم يُنفّذ فعلياً")


def combined_verification(
    farmer_response: str | None = None,
    metric_before: float | None = None,
    metric_after: float | None = None,
    expected_delta: float | None = None,
    why_rejected: str | None = None,
    sensor_confidence: str = "high",
    subsurface_irrigation: bool = False,
) -> VerificationResult:
    """يجمع المستويات بالتحكيم (arbitration) لا التغلّب المطلق.

    الحسّاس قرينة قويّة لا حاكم معصوم: قد يُعطّل، أو الري التحت-سطحي
    لا يُغيّر الرطوبة السطحية فوراً. لذا عند تناقض الحسّاس مع ادّعاء
    المزارع، نوازن بثقة الحسّاس بدل رفض الادّعاء رفضاً قاطعاً."""
    phys = None
    if metric_before is not None and metric_after is not None and expected_delta is not None:
        phys = verify_physical(metric_before, metric_after, expected_delta)
    pas = verify_passive(farmer_response, why_rejected)

    if phys is not None and phys.status != ImplementationStatus.UNCONFIRMED:
        # تناقض: المزارع ادّعى التنفيذ لكن الحسّاس لا يكشف أثراً
        if (pas.status == ImplementationStatus.CLAIMED
                and phys.status == ImplementationStatus.REJECTED):
            # حالات يُضعَّف فيها الحسّاس (لا يُرفَض الادّعاء قطعاً):
            #   • الري التحت-سطحي لا يرفع الرطوبة السطحية فوراً
            #   • حسّاس منخفض الثقة (قد يكون معطّلاً/غير مُعاير)
            if subsurface_irrigation:
                return VerificationResult(
                    ImplementationStatus.UNCONFIRMED, None, "low",
                    "تعارض غير حاسم: الري التحت-سطحي قد لا يرفع الرطوبة السطحية "
                    "فوراً — لا رفض قاطع، يلزم تأكيد لاحق",
                    learn_signal="subsurface_sensor_mismatch")
            if sensor_confidence in ("low", "medium"):
                return VerificationResult(
                    ImplementationStatus.UNCONFIRMED, None, "low",
                    f"تعارض غير حاسم: ثقة الحسّاس {sensor_confidence} (قد يكون "
                    "معطّلاً) مقابل ادّعاء المزارع — لا رفض قاطع، أعد الفحص",
                    learn_signal="low_confidence_sensor_mismatch")
            # حسّاس عالي الثقة + ري سطحي → التناقض حاسم (يترجّح الحسّاس)
            return VerificationResult(
                ImplementationStatus.REJECTED, VerificationLevel.PHYSICAL, "medium",
                "تعارض: أُفيد بالتنفيذ لكن حسّاس موثوق لا يكشف أثراً — "
                "يترجّح الحسّاس (ليس قطعاً؛ راجع إن تكرّر)",
                learn_signal="claimed_but_no_physical_effect")
        # حسّاس منخفض الثقة لا يؤكّد التنفيذ وحده بثقة عالية
        if sensor_confidence in ("low", "medium") and phys.confidence == "high":
            return VerificationResult(
                phys.status, phys.level, "medium",
                phys.note_ar + f" (ثقة الحسّاس {sensor_confidence} — خُفّض السقف)",
                learn_signal=phys.learn_signal)
        return phys
    return pas


# ════════════════════════════════════════════════════════════
# التكامل مع المايسترو (recommendation_engine)
# ════════════════════════════════════════════════════════════
def verify_recommendation_followup(
    recommendation_log: dict,
    *,
    farmer_response: str | None = None,
    metric_before: float | None = None,
    metric_after: float | None = None,
    expected_delta: float | None = None,
    sensor_confidence: str = "high",
    subsurface_irrigation: bool = False,
) -> dict:
    """جسر التكامل: يأخذ سجلّ توصية من المايسترو (Recommendation.to_log_dict)
    ويُرجعه مُثرى بحالة التحقّق من التنفيذ.

    هذا يربط implementation_verification بـ recommendation_engine صراحةً:
    المايسترو يولّد التوصية → بعد مدّة، هذه الدالة تتحقّق من تنفيذها →
    النتيجة تُغذّي حلقة التعلّم (calibration_loop) عبر learn_signal.

    لا يعدّل التوصية الأصلية — يُضيف طبقة متابعة (separation of concerns)."""
    result = combined_verification(
        farmer_response=farmer_response,
        metric_before=metric_before, metric_after=metric_after,
        expected_delta=expected_delta, sensor_confidence=sensor_confidence,
        subsurface_irrigation=subsurface_irrigation)
    enriched = dict(recommendation_log)
    enriched["verification"] = {
        "status": result.status.value,
        "level": result.level.value if result.level else None,
        "confidence": result.confidence,
        "note_ar": result.note_ar,
        "learn_signal": result.learn_signal,
    }
    return enriched
