"""api/water_ledger_auto.py — منطق نقيّ لأتمتة ميزان الماء اليوميّ (FAO-56 accumulation).

يحسب قيد دفتر المياه لليوم من قيد الأمس + مدخلات اليوم الحقيقيّة:

    Dr_t = clamp( Dr_{t-1} + ETc_t − P_eff_t − I_t , 0 , TAW )

الصدق قبل كلّ شيء:
  • لا اختلاق مدخلات: ET0 يأتي من محرّك الطقس (المصدر الوحيد)، المطر من التوقّع
    اليوميّ، والريّ من دفتر التشغيلات ``irrigation_runs`` — غياب أيّها يوقف حساب
    اليوم (skip مُعلَّل) ولا يُستبدَل بصفر مُختلَق.
  • bootstrap مُعلَن: أوّل يوم بلا قيد سابق يبدأ من Dr=0 (افتراض سعة حقليّة بعد
    ترطيب — التهيئة القياسيّة في FAO-56) مع خفض الثقة وذكر الافتراض في القرار.
  • تشغيلات ريّ بلا حجم mm تُحتسَب صفراً مع علمٍ مُعلَن ``irrigation_volume_untracked``
    (القيد يبقى أدنى تقدير للريّ لا أعلاه).
  • القيد اليدويّ سيّد: العامل لا يلمس قيد يومٍ أنشأه إنسان (يُقرَّر خارج هذه الدالّة).

نقيّ حتميّ (لا I/O) — كلّ المدخلات تُمرَّر صراحةً؛ يُختبَر بلا قاعدة.
"""

from __future__ import annotations

from api.water_balance import _effective_rain

# هويّة الكاتب الآليّ في created_by — بها يُميَّز قيد العامل من القيد اليدويّ.
AUTO_CREATED_BY = "water-balance-auto"

# ثقة القيد الآليّ: مدخلات حقيقيّة لكن TAW/Kc قد يكونان fallback — أدنى من قيد ميدانيّ.
CONFIDENCE_AUTO = 0.7
# أوّل قيد (bootstrap من Dr=0) أدنى ثقة حتى تتراكم أيّام حقيقيّة فوقه.
CONFIDENCE_BOOTSTRAP = 0.4


def compute_daily_ledger_entry(
    *,
    prev_depletion_mm: float | None,
    taw_mm: float,
    raw_mm: float,
    et0_mm: float,
    kc: float,
    rain_mm: float,
    irrigation_mm: float,
    irrigation_volume_untracked: bool = False,
    rain_assumed_zero: bool = False,
) -> dict:
    """قيد اليوم من قيد الأمس + مدخلات اليوم — نقيّ، مع افتراضات مُعلَنة لا صامتة.

    Returns dict بمفاتيح أعمدة ``water_ledger`` الحسابيّة + ``notes`` (قائمة أعلام
    الافتراضات) و``bootstrap`` و``confidence``.
    """
    if taw_mm <= 0:
        raise ValueError("TAW يجب أن يكون موجباً — لا يُحسب ميزان بلا سعة ماء متاح")
    if et0_mm < 0 or rain_mm < 0 or irrigation_mm < 0 or kc <= 0:
        raise ValueError("مدخلات سالبة/معدومة غير صالحة لميزان اليوم")

    notes: list[str] = []
    if rain_assumed_zero:
        # الطقس لم يُرجِع هطولاً لهذا اليوم ⇒ يُفترَض 0mm **صراحةً** (تقدير محافِظ: أعلى
        # استنزاف) لا تعبئة صامتة. p_eff=0 عندئذٍ. القيد يبقى أدنى تقدير للماء المتاح.
        notes.append("precipitation_assumed_zero")
    bootstrap = prev_depletion_mm is None
    if bootstrap:
        # التهيئة القياسيّة: بداية من السعة الحقليّة (Dr=0) — افتراض مُعلَن لا قياس.
        prev = 0.0
        notes.append("bootstrap_assumed_field_capacity")
    else:
        # قيد أمس قد يكون خارج المدى نظريّاً (إدخال يدويّ قديم) — يُقصّ بإعلان.
        prev = float(prev_depletion_mm)
        if prev < 0 or prev > taw_mm:
            notes.append("previous_depletion_clamped")
            prev = min(max(prev, 0.0), taw_mm)

    etc_mm = round(kc * et0_mm, 2)
    p_eff = _effective_rain(rain_mm)
    if irrigation_volume_untracked:
        notes.append("irrigation_volume_untracked")

    raw_depletion = prev + etc_mm - p_eff - irrigation_mm
    depletion_mm = round(min(max(raw_depletion, 0.0), taw_mm), 2)
    if raw_depletion > taw_mm:
        # استنزاف محسوب فوق السعة = إجهاد فعليّ فوق المتاح — يُعلَن لا يُخفى بالقصّ.
        notes.append("depletion_capped_at_taw")

    # العجز عن عتبة الريّ (RAW): موجب ⇒ الريّ مستحقّ بهذا المقدار.
    deficit_mm = round(max(depletion_mm - raw_mm, 0.0), 2)

    return {
        "etc_mm": etc_mm,
        "effective_rain_mm": round(p_eff, 2),
        "depletion_mm": depletion_mm,
        "deficit_mm": deficit_mm,
        "bootstrap": bootstrap,
        "confidence": CONFIDENCE_BOOTSTRAP if bootstrap else CONFIDENCE_AUTO,
        "notes": notes,
        "decision": ("auto:" + (";".join(notes) if notes else "daily_balance")),
    }


def manual_entry_takes_precedence(existing_created_by: str | None) -> bool:
    """قيد اليوم الموجود يُحترَم إن لم يكن من العامل نفسه — الإنسان سيّد الدفتر."""
    return existing_created_by is not None and existing_created_by != AUTO_CREATED_BY
