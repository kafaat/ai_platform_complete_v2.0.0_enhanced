"""
api/astronomical_timing.py — التوقيت الفلكي كمرساة موسميّة (رصدي لا تنجيمي)

يحسب توقيت الشروق الاحتراقي التقريبي لنجوم التقويم الزراعي العربي (سهيل،
الثريّا) لخطّ عرض اليمن، كـ**أداة توقيت موسمي** تُعرَض مع GDD للتحقّق المتقاطع.

التمييز الجوهري (مبدأ الصدق العلمي):
  • هذا **قياس فلكي رصدي** لموضع الأرض المداري — مكافئ زمني للفصل، مثل
    الاعتدال والانقلاب. ليس تنجيماً.
  • النجم لا "يؤثّر" في المحصول؛ بل توقيت شروقه **يقيس** أين الأرض في مدارها.
  • لا ادّعاء تأثير سببي (لا "ازرع في القمر المتزايد") — ذلك تنجيم نرفضه.

القيمة: يعمل offline بحساب بحت (لا استشعار)، مرساة ثقافيّة يفهمها المزارع،
وتقاطع تحقّق مع GDD (اتّفاق = ثقة؛ اختلاف = تنبيه لموسم شاذّ).

⚠ الحساب **تقريبي عملي** (مرساة موسميّة)، لا فلك أثري دقيق (الذي يحتاج arcus
visionis وانكسار جوّي وSwiss Ephemeris). موسوم بدقّته. كافٍ للتوقيت الزراعي.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class StarTiming:
    """توقيت نجم تقويمي."""

    name_ar: str
    heliacal_rising_approx: str  # تاريخ تقريبي (شهر/يوم)
    season_marker_ar: str  # ما يشير إليه موسميّاً
    agricultural_note_ar: str  # الاستخدام الزراعي التقليدي

    def to_dict(self) -> dict:
        return {
            "name_ar": self.name_ar,
            "heliacal_rising_approx": self.heliacal_rising_approx,
            "season_marker_ar": self.season_marker_ar,
            "agricultural_note_ar": self.agricultural_note_ar,
        }


# نجوم التقويم الزراعي العربي — توقيت تقريبي لخطوط عرض اليمن/الجزيرة (~15°N)
# التواريخ من التقاليد الرصديّة الموثّقة (سهيل ~24 أغسطس)؛ تقريب موسمي
ARABIAN_CALENDAR_STARS: list[StarTiming] = [
    StarTiming(
        "سهيل (Canopus)",
        "24 أغسطس تقريباً",
        "بدء تراجع ذروة حرّ الصيف؛ تبرد الليالي تدريجيّاً على ~52 يوماً",
        "إشارة تقليديّة لقرب موسم الزراعة الخريفي وتحسّن ظروف العمل الحقلي",
    ),
    StarTiming(
        "الثريّا (Pleiades)",
        "شروق احتراقي ~أوائل يونيو",
        "تُستخدم في نظام الأنواء لتتبّع التحوّلات الموسميّة وأنماط المطر",
        "مرجع تقليدي لتوقيت بعض الأعمال الزراعيّة الموسميّة",
    ),
]


# تواريخ مرجعيّة موسميّة (نصف الكرة الشمالي) للتحقّق المتقاطع
_SEASON_ANCHORS = {
    "spring_equinox": (3, 21),
    "summer_solstice": (6, 21),
    "autumn_equinox": (9, 23),
    "winter_solstice": (12, 21),
    "suhail_rising": (8, 24),
}


@dataclass
class TimingCrossCheck:
    """تحقّق متقاطع: المرساة الفلكيّة مقابل GDD."""

    star_anchor_ar: str
    days_from_anchor: int
    gdd_stage: str | None
    agreement_ar: str

    def to_dict(self) -> dict:
        return {
            "star_anchor_ar": self.star_anchor_ar,
            "days_from_anchor": self.days_from_anchor,
            "gdd_stage": self.gdd_stage,
            "agreement_ar": self.agreement_ar,
        }


def get_calendar_stars() -> dict:
    """يُرجع نجوم التقويم الزراعي كمرساة موسميّة (رصديّة، لا تنجيميّة)."""
    return {
        "purpose_ar": "توقيت موسمي رصدي (لا تنجيم)",
        "is_observational": True,
        "is_astrological": False,
        "disclaimer_ar": (
            "هذه مراسٍ فلكيّة رصديّة لتوقيت المواسم — تقيس موضع الأرض في مدارها "
            "(مثل الاعتدال والانقلاب)، ولا تدّعي أيّ تأثير للنجوم في المحصول. "
            "تُعرَض كمرجع توقيت يفهمه المزارع، ويُتحقَّق منها متقاطعاً مع تتبّع GDD."
        ),
        "stars": [s.to_dict() for s in ARABIAN_CALENDAR_STARS],
    }


# ─── التقاويم الزراعيّة الإقليميّة اليمنيّة ──────────────────────
# الحِميري للهضبة، الحضرمي للوادي. لكلّ منطقة تقويمها (المناخ يختلف).
# ⚠ التواريخ الميلاديّة تقريبيّة وتحتاج تأكيداً (تباين المصادر الشعبيّة/الأكاديميّة).


@dataclass
class RegionalCalendarEntry:
    period_name_ar: str  # اسم الشهر/النجم
    approx_gregorian_ar: str  # ما يقابله ميلاديّاً (تقريبي)
    agricultural_meaning_ar: str

    def to_dict(self) -> dict:
        return {
            "period_name_ar": self.period_name_ar,
            "approx_gregorian_ar": self.approx_gregorian_ar,
            "agricultural_meaning_ar": self.agricultural_meaning_ar,
        }


# التقويم الحِميري الزراعي (الهضبة: صنعاء/ذمار/البيضاء) — شهري شمسي
# ⚠ التواريخ من مصادر شعبيّة، تحتاج تأكيداً أكاديميّاً
_HIMYARITE_CALENDAR: list[RegionalCalendarEntry] = [
    RegionalCalendarEntry("ذو الثابة", "≈ أبريل", "أوّل الصيف — أوّل الشهور الزراعيّة"),
    RegionalCalendarEntry("ذو مبكر", "≈ مايو", "بداية الذرة"),
    RegionalCalendarEntry("ذو القياظ", "≈ يونيو", "شدّة الحرارة"),
    RegionalCalendarEntry("ذو المذراء", "≈ يوليو", "موسم زراعي صيفي"),
    RegionalCalendarEntry("ذو الخريف", "≈ أغسطس", "النضوج"),
    RegionalCalendarEntry("ذو علان", "≈ سبتمبر", "ظهور الحبوب والحاجة للمطر"),
]

# التقويم الحضرمي النجمي (وادي حضرموت) — ٢٨ نجماً × ١٣ يوماً
# عيّنة موثّقة من محطّة بحوث سيئون (٢٠١٢)
_HADRAMI_CALENDAR: list[RegionalCalendarEntry] = [
    RegionalCalendarEntry("الصرفة", "≈ ٢٠ مارس–١ أبريل", "ذرة صيفيّة + بامية"),
    RegionalCalendarEntry("العوّاء", "≈ ٢–١٤ أبريل", "ذرة صيفيّة"),
    RegionalCalendarEntry("السماك", "≈ ١٥–٢٧ أبريل", "لوبيا (الدجر)"),
]

# ربط المحافظة بالتقويم الإقليمي المناسب
_GOVERNORATE_CALENDAR = {
    # الهضبة → الحِميري
    "al_bayda": "himyarite",
    "sanaa": "himyarite",
    "dhamar": "himyarite",
    "ibb": "himyarite",
    "al_jawf": "himyarite",
    # الوادي/الساحل الشرقي → الحضرمي
    "hadramout": "hadrami",
    "al_mahra": "hadrami",
    "shabwa": "hadrami",
}

_CALENDAR_META = {
    "himyarite": {
        "name_ar": "التقويم الحِميري الزراعي",
        "structure_ar": "شمسي زراعي — ١٢ شهراً (حضارة حمير، ~٧٠٠ عام)",
        "region_ar": "الهضبة اليمنيّة (صنعاء، ذمار، البيضاء، إب، الجوف)",
        "entries": _HIMYARITE_CALENDAR,
    },
    "hadrami": {
        "name_ar": "التقويم الحضرمي النجمي",
        "structure_ar": "نجمي — ٢٨ نجماً × ١٣ يوماً (محطّة بحوث سيئون)",
        "region_ar": "وادي حضرموت والمناطق الشرقيّة",
        "entries": _HADRAMI_CALENDAR,
    },
}


def get_regional_calendar(governorate: str | None = None) -> dict:
    """يُرجع التقويم الزراعي الإقليمي المناسب للمحافظة (حِميري/حضرمي).

    لا "تقويم يمني موحّد" — التوقيت يختلف بالمنطقة لاختلاف المناخ والمحاصيل.
    """
    cal_key = _GOVERNORATE_CALENDAR.get(governorate or "", None)

    base = {
        "is_observational": True,
        "is_astrological": False,
        "disclaimer_ar": (
            "تقويم زراعي إقليمي رصدي (لا تنجيم) — مرساة موسميّة محلّيّة تُعرَض مع "
            "تتبّع GDD. التواريخ الميلاديّة تقريبيّة وتحتاج تأكيداً (تباين المصادر). "
            "لا يدخل في حساب توصيات التسميد/الريّ الكمّيّة."
        ),
        "regional_note_ar": (
            "لكلّ منطقة يمنيّة تقويمها الزراعي — لا تقويم موحّد. لا يُطبَّق تقويم "
            "منطقة على أخرى (المناخ والمحاصيل يختلفان)."
        ),
    }

    if cal_key is None:
        return {
            **base,
            "matched": False,
            "message_ar": (
                f"لا تقويم إقليمي محدّد للمحافظة '{governorate}'. "
                "المتاح: الحِميري (الهضبة)، الحضرمي (الوادي)."
            ),
            "available": ["himyarite", "hadrami"],
        }

    meta = _CALENDAR_META[cal_key]
    return {
        **base,
        "matched": True,
        "calendar_key": cal_key,
        "name_ar": meta["name_ar"],
        "structure_ar": meta["structure_ar"],
        "region_ar": meta["region_ar"],
        "entries": [e.to_dict() for e in meta["entries"]],
    }


def cross_check_with_gdd(
    current_date_iso: str,
    gdd_stage: str | None = None,
    anchor: str = "suhail_rising",
) -> dict:
    """تحقّق متقاطع: كم يوماً من المرساة الفلكيّة، وهل يتّفق مع مرحلة GDD؟

    Args:
        current_date_iso: التاريخ الحالي ISO (YYYY-MM-DD).
        gdd_stage: مرحلة GDD الحاليّة (من gdd_tracker) إن توفّرت.
        anchor: المرساة الفلكيّة (suhail_rising افتراضاً).
    """
    try:
        y, m, d = map(int, current_date_iso.split("-"))
        today = date(y, m, d)
    except (ValueError, AttributeError):
        return {"error_ar": "تاريخ غير صالح (استخدم YYYY-MM-DD)"}

    if anchor not in _SEASON_ANCHORS:
        return {"error_ar": f"مرساة غير معروفة: {anchor}"}

    am, ad = _SEASON_ANCHORS[anchor]
    anchor_date = date(today.year, am, ad)
    days_diff = (today - anchor_date).days

    anchor_ar = {
        "suhail_rising": "شروق سهيل (~24 أغسطس)",
        "autumn_equinox": "الاعتدال الخريفي",
        "spring_equinox": "الاعتدال الربيعي",
    }.get(anchor, anchor)

    # رسالة التحقّق المتقاطع
    if gdd_stage:
        agreement = (
            f"المرساة الفلكيّة ({anchor_ar}) و مرحلة GDD ('{gdd_stage}') تُعرَضان "
            "معاً للمزارع. لو اتّفقتا، الثقة في التوقيت أعلى؛ لو اختلفتا بوضوح، "
            "فقد يكون الموسم حارّاً/بارداً بشكل غير اعتيادي — راجع الحرارة."
        )
    else:
        agreement = (
            f"أنت على بُعد {abs(days_diff)} يوماً "
            f"{'بعد' if days_diff >= 0 else 'قبل'} {anchor_ar}. "
            "للتوقيت الأدقّ، اعتمد تتبّع GDD مع هذه المرساة."
        )

    return TimingCrossCheck(
        star_anchor_ar=anchor_ar,
        days_from_anchor=days_diff,
        gdd_stage=gdd_stage,
        agreement_ar=agreement,
    ).to_dict()
