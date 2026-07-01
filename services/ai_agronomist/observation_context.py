"""سياق الرصد الموحَّد للوكيل (V55 — المرحلة ٣: Observation).

النموذج يجب ألّا يعمل أعمى. قبل أيّ استنتاج يرى **لقطة رصد صادقة** لبيئته الحاليّة:
الطبقة النشطة · الحقل والتاريخ المختاران · مدى الخطّ الزمنيّ · جاهزيّة الراستر ·
مصدر الطقس · حالة تجهيز الصور (backfill) · آخر أخطاء API · سياسة المستأجِر (القدرات
ومستوى مشاركة البيانات).

الأهمّ: **الصدق في الغياب** — إن لم تكن TrueColor جاهزة، لا يقول النموذج «أرى الصورة»
بل يرى ملاحظةً صريحة («غير جاهزة؛ يمكن تشغيل التجهيز أو استخدام آخر مؤشّر»). دالّة صرفة
حتميّة تُطبِّع مُدخلاتٍ خامّة (تأتي من الواجهة/الخدمات) إلى لقطة مُنظَّمة — بلا نداءات حيّة.
"""

from __future__ import annotations

from typing import Any

# حالات جاهزيّة الراستر القانونيّة (مرآة تشخيص V54 من raster-service).
RASTER_READY = "ready"
RASTER_NOT_RENDERED = "index_not_rendered"  # مثل truecolor غير مُصيَّر بعد
RASTER_NOT_CONFIGURED = "cdse_not_configured"
RASTER_UNKNOWN = "unknown"


def _clean_errors(errors: Any) -> list[str]:
    if not isinstance(errors, (list, tuple)):
        return []
    return [str(e) for e in errors if e][:10]  # سقف: آخر ١٠ أخطاء


def build_observation(
    *,
    field_id: str | None,
    active_layer: str | None = None,
    selected_date: str | None = None,
    timeline_range_days: int | None = None,
    raster_state: str = RASTER_UNKNOWN,
    weather_source: str | None = None,
    backfill_status: str | None = None,
    last_api_errors: Any = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """يبني لقطة رصد مُنظَّمة صادقة يراها النموذج قبل الاستنتاج.

    ``notes`` تحمل تدرّجاً صادقاً (ماذا ينقص وما البديل). ``policy`` (سياسة المستأجِر)
    يُقرأ منها القدرات ومستوى مشاركة البيانات — فيعرف النموذج حدوده."""
    pol = policy or {}
    raster_ready = raster_state == RASTER_READY
    errors = _clean_errors(last_api_errors)

    notes: list[str] = []
    if field_id is None:
        notes.append("لم يُختَر حقل بعد — اطلب من المستخدم اختيار حقل أوّلاً.")
    if not raster_ready:
        if raster_state == RASTER_NOT_RENDERED:
            notes.append(
                "الصورة الخام (TrueColor) غير مُصيَّرة بعد من raster-service — "
                "يمكن تشغيل تجهيز الصور التاريخيّة أو استخدام مؤشّر تفسيريّ (NDVI/NDMI)."
            )
        elif raster_state == RASTER_NOT_CONFIGURED:
            notes.append("صور Copernicus غير مُهيّأة في البيئة — لا صور حيّة متاحة الآن.")
        else:
            notes.append("جاهزيّة الراستر غير مؤكَّدة — تحقّق قبل الاعتماد على الصورة.")
    if backfill_status and str(backfill_status).lower() in {"running", "queued"}:
        notes.append(
            f"تجهيز الصور قيد التنفيذ (الحالة: {backfill_status}) — قد تتغيّر الجاهزيّة قريباً."
        )
    if errors:
        notes.append(f"وُجدت {len(errors)} أخطاء API حديثة — تعامَل مع البيانات بحذر.")
    if not weather_source:
        notes.append("مصدر الطقس غير معروف — لا تدّعِ دقّةً لم تتحقّق منها.")

    return {
        "field_id": field_id,
        "active_layer": active_layer,
        "selected_date": selected_date,
        "timeline_range_days": timeline_range_days,
        "raster": {"state": raster_state, "ready": raster_ready},
        "weather_source": weather_source,
        "backfill_status": backfill_status,
        "last_api_errors": errors,
        "policy": {
            "allowed_capabilities": list(pol.get("allowed_capabilities") or []),
            "data_sharing_level": pol.get("data_sharing_level") or "local_only",
            "ai_generation_allowed": bool(pol.get("ai_generation_allowed", True)),
        },
        "notes": notes,
        "blind": not raster_ready or field_id is None,  # هل الرؤية منقوصة؟
    }
