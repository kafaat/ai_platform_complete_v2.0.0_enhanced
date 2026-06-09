"""
sahool_core.anwa_calendar
==========================
الأنواء النجمية (مطالع النجوم) كمصدر معرفة مجتمعية للتوقيت الزراعي.

ما هي: تقويم زراعي فلكي تجريبي تراكم عبر قرون في اليمن والجزيرة.
ليست تنجيماً — مواقع النجوم ترتبط بدورة الأرض الشمسية، فهي مؤشّر
موسمي دقيق. التقويم النجمي رسمي في اليمن (الحميري العنسي، 2006).

مكانتها (تطبيق مبدأ القرينة/الدليل):
  • قرينة قوية للتوقيت الموسمي (متى يُزرع، متى تأتي الأمطار)
  • مبنية على ملاحظة تراكمية طويلة — تستحقّ احتراماً ووزناً
  • لكنها لا تقيس حالة حقل بعينه (ملوحته، رطوبته الآن)
  • ولا تتجاوز الحاكمات الفيزيائية ولا بيانات الطقس الآنية

التكامل: تُعرض كـ "سياق توقيت تقليدي" يُثري التوصية، ويتقاطع مع
الطقس الفعلي (Open-Meteo). عند اتفاقهما → تضافر قرائن يقوّي التوقيت.
عند اختلافهما → نعرض الاثنين بصدق، الطقس الآني له الأولوية للقرار،
والعرف يبقى سياقاً ثقافياً محترماً.
"""

from __future__ import annotations

from dataclasses import dataclass

# سقف وزن المعرفة المجتمعية (متّسق مع farmer_knowledge: 0.15)
ANWA_WEIGHT_CEILING = 0.15


@dataclass
class StarSeason:
    """نجم زراعي (نوء) ودلالته الموسمية."""

    name_ar: str
    approx_start_ar: str  # تاريخ تقريبي (يختلف بالتقويم)
    duration_days: int
    agricultural_meaning_ar: str


# نجوم زراعية يمنية مختارة (دلالات تراثية موثّقة)
# ملاحظة: التواريخ تقريبية وتختلف بين التقاويم (الواسعي/العنسي/المريسي)
_STAR_SEASONS = {
    "soheil": StarSeason(
        "سهيل (اليماني)",
        "أواخر أغسطس",
        13,
        "بشير المطر الخريفي وغزارته؛ اعتدال الجو وبدء نضج العنب والرمان",
    ),
    "thuraya": StarSeason(
        "الثريا", "أوائل يونيو", 13, "بداية القيظ (شدة الحر)؛ توقيت لمحاصيل الصيف"
    ),
    "jawza": StarSeason(
        "الجوزاء", "أواخر يونيو", 13, "آخر أوقات زراعة الذرة — الزراعة بعده غير محبّذة لقرب الشتاء"
    ),
    "nathra": StarSeason(
        "النثرة", "أوائل سبتمبر", 13, "أول الخريف؛ رياح غربية ممطرة، اكتمال نضج التين"
    ),
}


def get_star_season(star_id: str) -> StarSeason | None:
    return _STAR_SEASONS.get(star_id)


@dataclass
class TimingContext:
    """سياق توقيت من العرف النجمي — قرينة محترمة لا حاكمة."""

    star_ar: str
    traditional_advice_ar: str
    weight: float  # سقف 0.15 (معرفة مجتمعية)
    is_governing: bool = False  # لا يحكم أبداً
    agrees_with_weather: bool | None = None
    note_ar: str = ""


def anwa_timing_context(
    star_id: str,
    *,
    weather_supports_planting: bool | None = None,  # من Open-Meteo الآني
) -> TimingContext | None:
    """يعطي سياق توقيت من العرف النجمي، ويتقاطع مع الطقس الفعلي.

    العرف قرينة توقيت محترمة (وزن ≤0.15). عند اتفاقه مع الطقس الآني
    → تضافر يقوّي التوقيت. عند اختلافهما → الطقس الآني أولوية للقرار،
    والعرف سياق ثقافي. لا يحكم العرف ولا يتجاوز بيانات الطقس."""
    season = get_star_season(star_id)
    if season is None:
        return None

    agrees = weather_supports_planting
    if agrees is None:
        note = (
            f"عُرف {season.name_ar}: {season.agricultural_meaning_ar}. "
            f"سياق توقيت تقليدي — قارنه بالطقس الفعلي للتأكيد."
        )
    elif agrees:
        note = (
            f"عُرف {season.name_ar} يتّفق مع الطقس الفعلي → "
            f"توقيت مرجّح بقوّة (تضافر العرف والبيانات). "
            f"{season.agricultural_meaning_ar}"
        )
    else:
        note = (
            f"عُرف {season.name_ar} يشير لـ: {season.agricultural_meaning_ar}، "
            f"لكن الطقس الفعلي الحالي مختلف. الطقس الآني له الأولوية "
            f"للقرار؛ العرف سياق محترم. راجع الحالة فعلياً."
        )

    return TimingContext(
        star_ar=season.name_ar,
        traditional_advice_ar=season.agricultural_meaning_ar,
        weight=ANWA_WEIGHT_CEILING,
        is_governing=False,
        agrees_with_weather=agrees,
        note_ar=note,
    )


def explain_anwa_principle_ar() -> str:
    """شرح مكانة الأنواء للعرض."""
    return (
        "مطالع النجوم (الأنواء) معرفة زراعية يمنية أصيلة تراكمت عبر قرون، "
        "وهي تقويم موسمي تجريبي محترم — لا تنجيم. في سهول نعاملها كـ"
        "قرينة توقيت قيّمة: تُثري التوصية وتتقاطع مع الطقس الفعلي. "
        "عند اتفاق العرف مع بيانات الطقس، يتقوّى التوقيت. وحين يختلفان، "
        "نعرض الاثنين بصدق — الطقس الآني للقرار، والعرف سياق ثقافي محترم. "
        "نحترم حكمة الأجداد دون أن نجعلها تتجاوز قياس الواقع الحالي."
    )
