"""api/routers/automation.py — أتمتة الجدولة (Scheduler / Weather / Imagery / Alerts)
=====================================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ السبع حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المفردات السنغلتون/المساعِدات) تبقى
مُعرَّفة في ``api.main`` وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models``
واستيرادات الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه
في نهايته فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

# المفردتان السنغلتون (weather_automation/imagery_automation) تُستورَدان مباشرةً من
# وحدتيهما — وهو نفس الكائن المُخزَّن في ذاكرة الوحدات (لا نسخة جديدة)، مطابقاً
# تماماً لما كان في main. النماذج/التبعيات المُعرَّفة في main تبقى وتُستورَد من api.main.
from api.imagery_automation import imagery_automation
from api.main import (
    ImageryFieldRegister,
    Permission,
    UserSchema,
    _db_unavailable,
    _evaluate_field_alerts_persist,
    get_current_user,
    require_permission,
    tenant_connection,
)
from api.weather_automation import weather_automation

router = APIRouter()


# ─── ٥٨. حالة جدولة الأتمتة (مراقبة) ──
@router.get("/api/v1/automation/scheduler-status")
def scheduler_status_endpoint():
    """حالة المهامّ الدوريّة المُؤتمتة: آخر تشغيل/نجاح/فشل لكلّ مهمّة.

    للمراقبة التشغيليّة — يكشف إن توقّفت أتمتة (سحب طقس/صور) أو تكرّر فشلها.
    """
    from api.scheduler import scheduler

    return scheduler.status()


@router.get("/api/v1/automation/runs")
def automation_runs_endpoint(
    limit: int | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """سجلّ تشغيل الأتمتة الدوريّة (مراقبة): ماذا فعلت كلّ دورة فعليّاً.

    يُكمّل ``scheduler-status`` (الذي يكشف آخر تشغيل/فشل فقط) بسجلّ منظّم لكلّ
    دورة: كم حقلاً قُيّم/تُخطّى/تعثّر، كم تنبيهاً أُنشئ، المدّة، والحالة
    (ok/partial/error). حلقة حلقيّة في الذاكرة (آخر ~50 دورة) — الأحدث أوّلاً.
    """
    from core.automation_ledger import LEDGER

    return {
        "runs": LEDGER.recent(limit=limit),
        "summary": LEDGER.summary(),
    }


@router.post("/api/v1/automation/weather/register")
async def weather_register_endpoint(
    lat: float,
    lon: float,
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """يسجّل إحداثيّة لسحب طقسها تلقائيّاً (الجدولة تحدّثه دوريّاً).

    يُحفظ في القاعدة لو توفّرت (يبقى بعد إعادة التشغيل).
    H1 FIX: يتطلّب مصادقة — يمنع تسجيل/استنزاف مجهول لمهامّ السحب الدوريّة.
    """
    await weather_automation.register_location_persistent(lat, lon, field_id)
    return {
        "registered": True,
        "lat": lat,
        "lon": lon,
        "field_id": field_id,
        "total_registered": weather_automation.registered_count(),
        "note_ar": "ستُسحب بيانات الطقس تلقائيّاً ضمن الدورة القادمة.",
    }


@router.get("/api/v1/automation/weather/cached")
def weather_cached_endpoint(
    lat: float,
    lon: float,
    user: UserSchema = Depends(get_current_user),
):
    """يقرأ آخر طقس مسحوب تلقائيّاً لإحداثيّة (سريع، من الذاكرة)."""
    c = weather_automation.get_cached(lat, lon)
    if c is None:
        return JSONResponse(
            status_code=404,
            content={
                "found": False,
                "note_ar": "لا طقس مُخزّن لهذه الإحداثيّة — سجّلها أوّلاً عبر /register.",
            },
        )
    return {"found": True, **c.to_dict()}


@router.get("/api/v1/automation/weather/status")
def weather_automation_status_endpoint(
    user: UserSchema = Depends(get_current_user),
):
    """حالة أتمتة الطقس: كم إحداثيّة مسجّلة وكم في الـcache."""
    return weather_automation.status()


@router.post("/api/v1/automation/imagery/register-field")
async def imagery_register_field_endpoint(
    req: ImageryFieldRegister,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """يسجّل حقلاً (bbox) لمتابعة صور Sentinel الجديدة تلقائيّاً.

    عند كلّ دورة جدولة: يُبحَث عن صور جديدة، وتُحسب المؤشّرات (NDVI) لها.
    يُحفظ في القاعدة لو توفّرت (يبقى بعد إعادة التشغيل، لا إعادة معالجة).
    الهويّة (tenant) من التوكن — تُمرَّر لـraster /process عند الحساب التلقائي.
    """
    try:
        await imagery_automation.register_field_persistent(
            req.field_id, req.bbox, tenant_id=str(user.tenant_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "registered": True,
        "field_id": req.field_id,
        "bbox": req.bbox,
        "total_tracked": imagery_automation.tracked_count(),
        "note_ar": "ستُفحَص صور Sentinel الجديدة وتُحسب مؤشّراتها تلقائيّاً.",
    }


@router.get("/api/v1/automation/imagery/status")
def imagery_automation_status_endpoint():
    """حالة أتمتة الصور: الحقول المتابَعة + آخر صورة/مؤشّر لكلّ حقل."""
    return imagery_automation.status()


@router.post("/api/v1/automation/alerts/run")
async def automation_run_alerts_endpoint(
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يُشغّل تقييم التنبيهات لكلّ حقول المستأجِر دفعةً واحدة (تشغيل عند الطلب).

    هذا هو المسار الذي يضربه جدولٌ خارجيّ (cron) أو الجدولة الداخليّة دوريّاً
    لتوليد تنبيهات الحقول تلقائيّاً بدل الانتظار لطلب يدويّ لكلّ حقل.

    معزول لكلّ حقل: فشل القاعدة/الطقس لحقل (مثلاً بلا إحداثيّات → 422، أو تعذّر
    Open-Meteo → 503) يُسجَّل في error ويُتخطّى — لا يُسقط بقيّة الحقول ولا يرفع
    500. tenant-isolated (RLS عبر tenant_connection + ترشيح tenant_id). يُرجع
    ملخّصاً لكلّ حقل {field_id, created, skipped} + إجماليّات.
    """
    from api.alert_rules import field_run_summary, summarize_run

    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT field_id FROM fields WHERE tenant_id = $1::uuid ORDER BY name",
                str(user.tenant_id),
            )
    except HTTPException:
        raise  # get_pool() ⇒ 503 (القاعدة معطّلة) — لا حقول لنقرأها أصلاً
    except Exception as e:  # noqa: BLE001 — تعذّر قراءة قائمة الحقول ⇒ 503 موثَّق
        raise _db_unavailable("قراءة حقول المستأجِر", e) from e

    summaries: list[dict] = []
    for r in rows:
        fid = r["field_id"]
        try:
            created, skipped = await _evaluate_field_alerts_persist(user, fid)
            summaries.append(field_run_summary(fid, created=len(created), skipped=skipped))
        except HTTPException as he:  # 404/422/503 لحقل ⇒ تخطٍّ رشيق (لا 500)
            summaries.append(field_run_summary(fid, error=f"{he.status_code}: {he.detail}"))
        except Exception as e:  # noqa: BLE001 — أيّ خطأ آخر لحقل ⇒ تخطٍّ معزول
            logging.warning("automation alerts run: skipped field %s: %s", fid, type(e).__name__)
            summaries.append(field_run_summary(fid, error=type(e).__name__))

    return summarize_run(summaries)
