"""
sahool_core.engines.pesticide
==============================
بوّابات قرار المبيدات — تطبيق مبدأ "السلامة لا تُتخطّى" بثلاث طبقات.

الترتيب الحاكم (لا يُخالَف):
  ١. PHI (حاجز ثنائي زمني): إن لم تمضِ فترة ما قبل الحصاد → BLOCKED صرف.
     حدّ زمني صارم لا نسبة. يأتي أوّلاً ويُلغي ما بعده.
  ٢. RRI (قرينة احتياطية للمخلفات): تقدير تفكّك المبيد. ⚠️ قرينة لا دليل —
     ترفع الحذر، لا تأذن بالحصاد وحدها أبداً (المختبر يحكم، لا التقدير).
  ٣. Economic (تحذير اقتصادي): جدوى الرش. تحذير لا حظر (ليس سلامة).

المبدأ الحاسم (يخالف الاقتراح الأصلي عمداً للسلامة):
  RRI < 30% لا يعني "آمن للحصاد". المخلفات المُقدَّرة تقدير لا قياس؛
  لو وثقنا بها وأخطأت → سمّ على مائدة المستهلك. لذا RRI أقصى ما يفعل:
  يخفّف الحذر ضمن التزام PHI، أو يرفعه. لا يستبدل PHI ولا الفحص المخبري.

غياب أي بيانات (سجلّ رش، PHI، أو بطاقة المبيد) → BLOCKED (القاعدة الذهبية).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class PesticideGate(str, Enum):
    BLOCKED = "blocked"  # لا حصاد (PHI لم يمضِ أو RRI≥100% أو بيانات ناقصة)
    CAUTION = "caution"  # ضمن PHI لكن RRI يرفع الحذر
    CLEARED_PHI = "cleared"  # مضى PHI — الحاجز الزمني انفتح (يبقى الفحص مستحسناً)


@dataclass
class PesticideDecision:
    gate: PesticideGate
    confidence: str  # none / low / medium
    phi_satisfied: bool | None  # هل مضى PHI؟ None = بيانات ناقصة
    days_since_spray: int | None
    phi_days: int | None
    rri_pct: float | None  # مؤشّر المخاطرة المتبقّية (قرينة)
    reason_ar: str
    recommendation_ar: str
    requires_lab_ar: str = ""  # متى يُنصح بفحص مخبري


# ════════════════════════════════════════════════════════════
# ١. PHI — الحاجز الثنائي الزمني (حاكم صارم)
# ════════════════════════════════════════════════════════════
def phi_gate(days_since_spray: int | None, phi_days: int | None) -> tuple[bool | None, str]:
    """الحاجز الزمني الصارم. يُرجع (مضى PHI؟, سبب).
    بيانات ناقصة → None (→ BLOCKED بالقاعدة الذهبية)."""
    if days_since_spray is None or phi_days is None:
        return None, "بيانات ناقصة: تاريخ الرش أو PHI المبيد غير معروف"
    if days_since_spray < phi_days:
        remaining = phi_days - days_since_spray
        return False, (
            f"لم تمضِ فترة الأمان (PHI={phi_days}يوم؛ مضى "
            f"{days_since_spray}). يُمنع الحصاد {remaining} يوماً بعد."
        )
    return True, f"مضت فترة الأمان (PHI={phi_days}يوم، مضى {days_since_spray})."


# ════════════════════════════════════════════════════════════
# ٢. RRI — قرينة المخلفات الاحتياطية (لا تحكم وحدها)
# ════════════════════════════════════════════════════════════
def predict_residue(initial_deposit: float, decay_k: float, days_since_spray: int) -> float:
    """تقدير المخلفات بالتفكّك الأُسّي: deposit × e^(-k·t).
    تقدير لا قياس — قرينة فقط."""
    return initial_deposit * math.exp(-decay_k * days_since_spray)


def residue_risk_index(
    initial_deposit: float | None,
    decay_k: float | None,
    days_since_spray: int | None,
    mrl: float | None,
) -> float | None:
    """RRI% = (المخلّف المُقدَّر / الحدّ الأقصى المسموح) × 100.
    None إن نقصت بيانات. قرينة احتياطية لا دليل."""
    if None in (initial_deposit, decay_k, days_since_spray, mrl) or mrl <= 0:
        return None
    residue = predict_residue(initial_deposit, decay_k, days_since_spray)
    return round((residue / mrl) * 100, 1)


# ════════════════════════════════════════════════════════════
# ٣. Economic — التحذير الاقتصادي (لا يمسّ السلامة)
# ════════════════════════════════════════════════════════════
def economic_warning(
    pesticide_cost: float,
    application_cost: float,
    phi_delay_cost: float,
    expected_yield_increase: float,
    market_price: float,
) -> tuple[str, str]:
    """جدوى الرش. تحذير لا حظر. يُرجع (مستوى, رسالة)."""
    benefit = expected_yield_increase * market_price
    if benefit <= 0:
        return "unknown", "لا يمكن تقدير الجدوى (عائد متوقّع غير معروف)"
    total_cost = pesticide_cost + application_cost + phi_delay_cost
    ratio = total_cost / benefit
    if ratio > 0.5:
        return "not_viable", f"تكلفة الرش ({ratio:.0%} من العائد) قد تتجاوز جدواه — استشر خبيراً"
    if ratio >= 0.3:
        return "marginal", f"جدوى حدّية ({ratio:.0%} من العائد) — راجع الأرقام"
    return "viable", f"الرش مجدٍ اقتصادياً ({ratio:.0%} من العائد)"


# ════════════════════════════════════════════════════════════
# التجميع: قرار المبيد الموحّد (PHI أولاً، ثم RRI كقرينة)
# ════════════════════════════════════════════════════════════
def evaluate_pesticide_safety(
    *,
    days_since_spray: int | None,
    phi_days: int | None,
    initial_deposit: float | None = None,
    decay_k: float | None = None,
    mrl: float | None = None,
) -> PesticideDecision:
    """القرار الموحّد. PHI حاكم صارم يأتي أولاً؛ RRI قرينة احتياطية.

    الحاسم: حتى لو RRI منخفض، لا حصاد قبل مُضيّ PHI. وحتى بعد PHI،
    RRI المرتفع يرفع الحذر ويُوصي بفحص مخبري — لا يُلغي PHI ولا يستبدله."""
    phi_ok, phi_reason = phi_gate(days_since_spray, phi_days)
    rri = residue_risk_index(initial_deposit, decay_k, days_since_spray, mrl)

    # بيانات PHI ناقصة → BLOCKED (القاعدة الذهبية)
    if phi_ok is None:
        return PesticideDecision(
            gate=PesticideGate.BLOCKED,
            confidence="none",
            phi_satisfied=None,
            days_since_spray=days_since_spray,
            phi_days=phi_days,
            rri_pct=rri,
            reason_ar=phi_reason,
            recommendation_ar="لا توصية حصاد — أكمل بيانات الرش وPHI المبيد",
            requires_lab_ar="فحص مخبري للمخلفات قبل الحصاد",
        )

    # PHI لم يمضِ → BLOCKED صرف (تجاهل RRI تماماً — الزمن حاكم)
    if phi_ok is False:
        return PesticideDecision(
            gate=PesticideGate.BLOCKED,
            confidence="none",
            phi_satisfied=False,
            days_since_spray=days_since_spray,
            phi_days=phi_days,
            rri_pct=rri,
            reason_ar=phi_reason,
            recommendation_ar="يُمنع الحصاد حتى انقضاء فترة الأمان (PHI)",
        )

    # PHI مضى — RRI الآن قرينة احتياطية (لا تأذن وحدها)
    if rri is not None and rri >= 100:
        # المخلّف المُقدَّر يتجاوز الحدّ → حذر قصوى رغم انقضاء PHI
        return PesticideDecision(
            gate=PesticideGate.CAUTION,
            confidence="low",
            phi_satisfied=True,
            days_since_spray=days_since_spray,
            phi_days=phi_days,
            rri_pct=rri,
            reason_ar=f"مضى PHI لكن المخلّف المُقدَّر مرتفع (RRI≈{rri}%)",
            recommendation_ar="رغم انقضاء PHI، التقدير يشير لمخلّف مرتفع — أجّل الحصاد وافحص مخبرياً",
            requires_lab_ar="فحص مخبري للمخلفات إلزامي قبل الحصاد",
        )

    # PHI مضى وRRI منخفض/غير معروف → الحاجز الزمني انفتح
    # حاسم: هذا ليس "آمن مؤكّد" بل "الحاجز الزمني انقضى"
    note = ""
    conf = "medium"
    if rri is None:
        note = "فحص مخبري للمخلفات مُستحسن (لا بيانات تفكّك لتقدير RRI)"
        conf = "low"
    elif rri >= 30:
        note = f"المخلّف المُقدَّر متوسّط (RRI≈{rri}%) — فحص مخبري سريع مُستحسن قبل الحصاد"
        conf = "low"
    else:
        note = f"المخلّف المُقدَّر منخفض (RRI≈{rri}%) — يبقى الفحص المخبري هو المؤكّد الوحيد"
    return PesticideDecision(
        gate=PesticideGate.CLEARED_PHI,
        confidence=conf,
        phi_satisfied=True,
        days_since_spray=days_since_spray,
        phi_days=phi_days,
        rri_pct=rri,
        reason_ar=f"مضت فترة الأمان (PHI={phi_days}يوم)",
        recommendation_ar="انقضت فترة الأمان الزمنية؛ التقدير قرينة لا إذن — المختبر يحكم",
        requires_lab_ar=note,
    )
