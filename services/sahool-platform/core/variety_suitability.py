"""
sahool_core.variety_suitability
===============================
محرّك ملاءمة زراعيّة على مستوى الصنف (variety-aware agronomic suitability).

محرّك نقيّ (pure): المدخل/المخرج الوحيد عبر ``core.crop_cards.loader``.
لا يكتب شيئاً في البطاقات ولا يرفع استثناءات على البيانات الناقصة —
بل يتدهور بصدق (degrade honestly) ويُرجع None/فراغاً عند الجهل.

تنبيه حياديّة الموقع: دالّة ``salinity_suitability`` حسابُ دعمِ قرارٍ لكلّ
حقلٍ (مدخل قياس ECe ميدانيّ) — ليست بيانات تُخزَّن في البطاقة المحايدة
للموقع. تبقى في هذا المحرّك ولا تُكتب أبداً إلى البطاقات.
"""

from __future__ import annotations

import datetime

from core.crop_cards.loader import load_crop_card, load_variety_card

# عتبات تصنيف الملاءمة الملحيّة (موثّقة هنا، لا تُخزَّن في البطاقة):
#   - القياس عند/تحت العتبة            ⇒ "suitable"   (0% فقدان)
#   - فوق العتبة وفقدان متوقَّع ≤ 25%   ⇒ "marginal"
#   - فوق العتبة وفقدان متوقَّع  > 25%   ⇒ "unsuitable"
_MARGINAL_MAX_LOSS_PCT = 25.0


def variety_salinity_threshold(variety_id: str) -> float | None:
    """عتبة الملوحة الفعليّة للصنف = عتبة المحصول الأمّ + تعديل الصنف.

    threshold_ece_ds_m للمحصول الأمّ مضافاً إليه
    variety_traits.salt_tolerance_modifier (تعديل بوحدة dS/m، عادةً 0.0).
    تُرجع None إن جُهِل الصنف أو المحصول الأمّ أو العتبة.
    """
    variety = load_variety_card(variety_id)
    if variety is None:
        return None
    parent_id = variety.get("parent_crop_id")
    if not parent_id:
        return None
    crop = load_crop_card(parent_id)
    if crop is None:
        return None
    base = crop.get("salinity", {}).get("threshold_ece_ds_m")
    if base is None:
        return None
    modifier = variety.get("variety_traits", {}).get("salt_tolerance_modifier", 0.0) or 0.0
    return float(base) + float(modifier)


def salinity_suitability(variety_id: str, measured_ece_ds_m: float) -> dict:
    """يصنّف ECe المقيس ميدانيّاً ضدّ عتبة الصنف + انحدار Maas-Hoffman.

    دعمُ قرارٍ لكلّ حقل (per-field decision support) — لا يُكتب إلى البطاقة.
    عند/تحت العتبة ⇒ "suitable" بفقدان 0%؛ فوقها يُحسب الفقدان المتوقَّع =
    slope_pct_per_ds_m × (measured − threshold) مع تثبيته في المجال 0..100،
    والتصنيف "marginal" إن كان الفقدان ≤ 25% وإلّا "unsuitable".
    عند نقص البيانات ⇒ {"class": None, "note_ar": "بيانات غير كافية"}.
    """
    threshold = variety_salinity_threshold(variety_id)
    variety = load_variety_card(variety_id)
    crop = load_crop_card(variety["parent_crop_id"]) if variety else None
    slope = crop.get("salinity", {}).get("slope_pct_per_ds_m") if crop else None

    if threshold is None or slope is None or measured_ece_ds_m is None:
        return {
            "variety_id": variety_id,
            "threshold_ece_ds_m": threshold,
            "measured_ece_ds_m": measured_ece_ds_m,
            "class": None,
            "expected_yield_loss_pct": None,
            "note_ar": "بيانات غير كافية",
        }

    measured = float(measured_ece_ds_m)
    if measured <= threshold:
        loss = 0.0
        klass = "suitable"
        note = "ECe عند/تحت عتبة الصنف — لا فقدان إنتاج متوقَّع من الملوحة"
    else:
        loss = float(slope) * (measured - threshold)
        loss = max(0.0, min(100.0, loss))
        if loss <= _MARGINAL_MAX_LOSS_PCT:
            klass = "marginal"
            note = "ECe فوق العتبة — فقدان إنتاج محدود متوقَّع؛ يُنصح بمتابعة الإدارة الملحيّة"
        else:
            klass = "unsuitable"
            note = "ECe فوق العتبة بفقدان إنتاج مرتفع — غير ملائم لهذا الصنف دون تحسين"

    return {
        "variety_id": variety_id,
        "threshold_ece_ds_m": threshold,
        "measured_ece_ds_m": measured,
        "class": klass,
        "expected_yield_loss_pct": round(loss),
        "note_ar": note,
    }


def expected_harvest(variety_id: str, sowing_date: datetime.date) -> dict:
    """يقدّر تواريخ التزهير/الحصاد من phenology للصنف وتاريخ الزراعة.

    يعتمد phenology.days_to_maturity و days_to_50pct_flowering (تواريخ ISO).
    الحقول None عندما يفتقر الصنف إلى phenology المعنيّة (صدق عند الجهل).
    """
    variety = load_variety_card(variety_id)
    phenology = variety.get("phenology", {}) if variety else {}

    days_to_maturity = phenology.get("days_to_maturity")
    days_to_flowering = phenology.get("days_to_50pct_flowering")

    expected_harvest_date = None
    if days_to_maturity is not None:
        expected_harvest_date = (
            sowing_date + datetime.timedelta(days=int(days_to_maturity))
        ).isoformat()

    expected_flowering_date = None
    if days_to_flowering is not None:
        expected_flowering_date = (
            sowing_date + datetime.timedelta(days=int(days_to_flowering))
        ).isoformat()

    return {
        "variety_id": variety_id,
        "sowing_date": sowing_date.isoformat(),
        "days_to_maturity": days_to_maturity,
        "expected_harvest_date": expected_harvest_date,
        "days_to_50pct_flowering": days_to_flowering,
        "expected_flowering_date": expected_flowering_date,
    }


def variety_disease_watch(variety_id: str) -> dict:
    """يُرجع تحمّلات الأمراض المُصرَّح بها للصنف فقط (لا اختلاق).

    إن كانت disease_resistance_ar فارغة ⇒ resistant_ar [] مع ملاحظة أنّ الدليل
    لا يُصرّح بتحمّل محدّد (يُنصح بمسحٍ ميدانيّ واسع — scout broadly).
    لا تُخترَع أمراض لم تذكرها البطاقة.
    """
    variety = load_variety_card(variety_id)
    if variety is None:
        return {
            "variety_id": variety_id,
            "resistant_ar": [],
            "note_ar": "الصنف غير معروف — لا توجد بطاقة لاستخلاص تحمّلاته",
        }

    resistances = variety.get("variety_traits", {}).get("disease_resistance_ar") or []
    resistant_ar = list(resistances)
    if resistant_ar:
        note = "تحمّلات مُصرَّح بها في الدليل — تبقى المتابعة الميدانيّة مطلوبة"
    else:
        note = "الدليل لا يُصرّح بتحمّل مرضيّ محدّد لهذا الصنف — يُنصح بمسحٍ ميدانيّ واسع"

    return {
        "variety_id": variety_id,
        "resistant_ar": resistant_ar,
        "note_ar": note,
    }
