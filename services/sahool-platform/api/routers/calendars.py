"""api/routers/calendars.py — التقويم الزراعيّ اليمنيّ (Calendars)
=================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الخمس حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدوالّ هنا نقيّة (عرض/معرفة فقط، بلا مصادقة) وتعتمد استيرادات كسولة داخليّة من
``api.yemeni_calendars``/``api.planting_calendar`` — تبقى كما هي. لتفادي الاستيراد
الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/calendars/today")
def calendars_today(
    date: str | None = None,
    governorate: str | None = None,
    crop: str | None = None,
):
    """سياق التقويم الزراعيّ لتاريخ (افتراضيّاً اليوم) في نداء واحد — يُسهّل بطاقة
    «التقويم الزراعيّ» في الواجهة:
      • المنزلة القمريّة النشطة + النوء (marker) + الشهر الحميريّ + ملف المنطقة.
      • إن مُرِّر محصول: نافذة زراعته وملاءمة الشهر الحاليّ (تبكير/تأخير).
    عرض/إرشاد تراثيّ-رصديّ صريحاً (display_only=true، خارج محرّك القرار) — التوقيت
    الفعليّ يبقى على GDD/الفيزياء. تاريخ غير صالح ⇒ يُعاد error_ar من الجسر.
    """
    from datetime import date as _date

    from api.yemeni_calendars import calendar_context_for_date

    target_iso = date or _date.today().isoformat()
    ctx = calendar_context_for_date(target_iso, governorate)
    # تاريخ غير صالح ⇒ الجسر يُعيد {error_ar}: لا نُضيف planting (تجنّب خلط خطأ
    # ببيانات مشتقّة من تاريخ آخر) — تدهور رشيق متّسق مع الـdocstring.
    if crop and "error_ar" not in ctx:
        from api.planting_calendar import check_planting_date, planting_window

        month = _date.fromisoformat(target_iso).month  # صحيح هنا (مرّ الجسر)
        ctx["planting"] = {
            "window": planting_window(crop),
            "current_month_fit": check_planting_date(crop, month),
        }
    return ctx


@router.get("/api/v1/calendars/lunar-mansions")
def calendars_lunar_mansions():
    """المنازل القمريّة الـ٢٨ (نجوم الزراعة) — مرجع معرفي تراثي (عرض فقط)."""
    from api.yemeni_calendars import get_lunar_mansions

    return get_lunar_mansions()


@router.get("/api/v1/calendars/himyarite-months")
def calendars_himyarite_months():
    """الشهور الحميريّة الـ١٢ + تنبيه التباين بين المصادر (عرض فقط)."""
    from api.yemeni_calendars import get_himyarite_months

    return get_himyarite_months()


@router.get("/api/v1/calendars/regional-profiles")
def calendars_regional_profiles(governorate: str | None = None):
    """ملفّات التقاويم الإقليميّة (حضرموت/تهامة/المرتفعات/الجوف) — الربط المكانيّ."""
    from api.yemeni_calendars import get_regional_profiles

    return get_regional_profiles(governorate=governorate)


@router.get("/api/v1/calendars/context")
def calendars_context(date_iso: str, governorate: str | None = None):
    """الجسر الزمني: تاريخ → المنزلة النشطة + الشهر الحميري + ملف المنطقة.

    عرض ومعرفة فقط؛ لا يدخل القرار. التواريخ تقريبيّة، المقابلات تختلف.
    """
    from api.yemeni_calendars import calendar_context_for_date

    return calendar_context_for_date(date_iso, governorate=governorate)
