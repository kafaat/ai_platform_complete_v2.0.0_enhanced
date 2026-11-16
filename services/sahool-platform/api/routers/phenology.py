"""api/routers/phenology.py — مراحل نموّ الموسم الطوريّة (Phenology)
=================================================================
موجِّه ``APIRouter`` جديد يكشف خطّ زمن مراحل النموّ للموسم النشط للحقل + المرحلة
الحاليّة ومعامل المحصول Kc الطوريّ، وإجراءات الطور المقترَحة — مبنيّ كلّيّاً على
المنطق النقيّ في ``core.season_phenology`` (لا تكرار).

صدق صارم: حين لا يوجد موسم نشط، أو لا تاريخ بذار، أو محصول مجهول البطاقة، نُرجع
``{"available": false, "reason_ar": ...}`` بدل خطّ زمن مُلفَّق. إجراءات الطور
**اقتراحات فقط** — لا تُكتَب مهامّ في القاعدة.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى في ``api.main`` وتُستورَد
من هنا (نمط بقيّة الموجِّهات، مثل ``routers/indicators``). المنطق النقيّ يُستورَد من
``core.season_phenology`` فيُختبَر offline دون قاعدة.
"""

from __future__ import annotations

import json
from datetime import date

from core.gdd_phenology import resolve_stage
from core.season_phenology import (
    resolve_crop_id,
    season_timeline,
    stage_kc,
)
from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


def _first_season_crop(crops, fallback_crop: str | None) -> str | None:
    """اسم المحصول الفعليّ للموسم: أوّل عنصر في ``crops`` وإلّا محصول الحقل.

    دالّة نقيّة: ``crops`` قد يكون JSON نصّيّاً (JSONB من القاعدة) أو قائمة — يُطبَّع
    كما في ``main._field_season_context``. الفراغ/التشوّه ⇒ يتدهور لمحصول الحقل.
    """
    if isinstance(crops, str):
        try:
            crops = json.loads(crops)
        except (ValueError, TypeError):
            crops = []
    if isinstance(crops, list) and crops:
        return str(crops[0])
    return fallback_crop


def _stage_basis(resolved: dict, weather: dict | None) -> dict:
    """مصدر المرحلة المُعلَن (W1-10): gdd أو احتياط تقويميّ مع سببه، ومدى GDD المستعمَل."""
    weather = weather or {}
    return {
        "stage_source": resolved.get("stage_source"),
        "stage_fallback": resolved.get("stage_fallback"),
        "stage_fallback_reason": resolved.get("stage_fallback_reason"),
        "accumulated_gdd": resolved.get("accumulated_gdd"),
        "accumulated_gdd_through": weather.get("accumulated_gdd_through"),
        "weather_unavailable": list(weather.get("unavailable") or []),
    }


def _shape_phenology(
    crop: str | None,
    sowing_date: date | None,
    today: date | None = None,
    weather: dict | None = None,
) -> dict:
    """يشكّل ردّ الـphenology من اسم محصول + تاريخ بذار (دالّة نقيّة، لا قاعدة).

    المرحلة الحاليّة من المحلِّل الواحد ``core.gdd_phenology``: حراريّة حين يحمل ``weather``
    GDD متراكماً (من ``gather_season_weather_inputs``)، وإلّا تقويميّة مُعلَنة.

    يُرجع خطّ زمن المراحل + المرحلة الحاليّة + Kc الطوريّ + أيّام ما بعد البذار.
    صدق: محصول مجهول البطاقة، أو غياب تاريخ البذار ⇒ ``available=False`` بسبب
    صريح بدل تقدير مُلفَّق.
    """
    if sowing_date is None:
        return {"available": False, "reason_ar": "لا يوجد تاريخ بذار للموسم النشط"}
    crop_id = resolve_crop_id(crop)
    if crop_id is None:
        return {
            "available": False,
            "reason_ar": "المحصول غير معروف في بطاقات المحاصيل (لا مراحل نموّ مُعرَّفة)",
        }
    ref = today or date.today()
    das = (ref - sowing_date).days
    timeline = season_timeline(crop_id, sowing_date, today=ref)
    if not timeline:
        return {
            "available": False,
            "reason_ar": "لا توجد كتلة مراحل نموّ (phenology) لهذا المحصول",
        }
    stage, resolved = resolve_stage(crop_id, das, (weather or {}).get("accumulated_gdd"))
    return {
        "available": True,
        "crop": crop,
        "crop_id": crop_id,
        "sowing_date": sowing_date.isoformat(),
        "days_after_sowing": das,
        "current_stage": stage,
        "current_stage_kc": stage_kc(crop_id, das),
        **_stage_basis(resolved, weather),
        "timeline": timeline,
    }


def _shape_stage_actions(
    crop: str | None,
    sowing_date: date | None,
    today: date | None = None,
    weather: dict | None = None,
) -> dict:
    """يشكّل اقتراحات إجراء الطور الحاليّ (دالّة نقيّة، لا قاعدة، لا كتابة مهامّ).

    يبني الاقتراح من ``key_action_ar`` و``name_ar`` للمرحلة الحاليّة. صدق: محصول
    مجهول، أو غياب تاريخ البذار، أو خروج العمر عن دورة المحصول ⇒ ``available=False``.
    """
    if sowing_date is None:
        return {"available": False, "reason_ar": "لا يوجد تاريخ بذار للموسم النشط"}
    crop_id = resolve_crop_id(crop)
    if crop_id is None:
        return {
            "available": False,
            "reason_ar": "المحصول غير معروف في بطاقات المحاصيل (لا مراحل نموّ مُعرَّفة)",
        }
    ref = today or date.today()
    das = (ref - sowing_date).days
    stage, resolved = resolve_stage(crop_id, das, (weather or {}).get("accumulated_gdd"))
    if stage is None:
        return {
            "available": False,
            "reason_ar": "العمر خارج دورة المحصول المُعرَّفة (لا مرحلة حاليّة)",
        }
    suggestions: list[dict] = []
    action = stage.get("key_action_ar")
    if action:
        suggestions.append(
            {
                "stage": stage.get("stage"),
                "stage_name_ar": stage.get("name_ar"),
                "action_ar": action,
            }
        )
    return {
        "available": True,
        "crop": crop,
        "crop_id": crop_id,
        "days_after_sowing": das,
        "current_stage": stage.get("stage"),
        "current_stage_name_ar": stage.get("name_ar"),
        **_stage_basis(resolved, weather),
        "suggestions": suggestions,
        "note_ar": "اقتراحات إرشاديّة فقط — لا تُنشَأ مهامّ تلقائيّاً",
    }


async def _active_season_crop_and_sowing(conn, field_id: str):
    """يقرأ (اسم المحصول، تاريخ البذار، lat، lon) للموسم النشط للحقل — كما ``main``.

    SELECT crops, sowing_date FROM seasons WHERE field_id=$1 AND status='active'
    ORDER BY created_at DESC LIMIT 1. يتدهور لمحصول الحقل (fields.crop) إن غاب
    أوّل محصول للموسم. غياب الموسم ⇒ (محصول الحقل، None، lat، lon).
    """
    field_row = await conn.fetchrow(
        "SELECT crop, lat, lon FROM fields WHERE field_id = $1", field_id
    )
    fallback_crop = field_row["crop"] if field_row is not None else None
    lat = field_row["lat"] if field_row is not None else None
    lon = field_row["lon"] if field_row is not None else None
    season = await conn.fetchrow(
        "SELECT crops, sowing_date FROM seasons "
        "WHERE field_id = $1 AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        field_id,
    )
    if season is None:
        return fallback_crop, None, lat, lon
    crop = _first_season_crop(season["crops"], fallback_crop)
    return crop, season["sowing_date"], lat, lon


async def _season_thermal_time(user, crop, sowing_date, lat, lon) -> dict | None:
    """GDD المتراكم للموسم من weather-service بعد تحرير الاتّصال (W1-10)، بلا توقّع.

    best-effort: تعذّر الطقس ⇒ ``accumulated_gdd`` None والسبب في ``unavailable``، فتبقى
    المرحلة تقويميّة مُعلَنة. لا موسم/لا بذار ⇒ None (لا مرحلة تُحلَّل أصلاً).
    """
    if sowing_date is None or resolve_crop_id(crop) is None:
        return None
    from datetime import UTC, datetime

    from api.field_season_projection import gather_season_weather_inputs
    from api.weather_service_client import get_gdd_product, get_weather_historical

    today = datetime.now(UTC).date()
    return await gather_season_weather_inputs(
        crop=crop,
        sowing_date=sowing_date,
        as_of=today,
        today=today,
        lat=lat,
        lon=lon,
        tenant_id=str(user.tenant_id),
        get_historical=get_weather_historical,
        get_gdd=get_gdd_product,
    )


@router.get("/api/v1/fields/{field_id}/phenology")
async def field_phenology(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """خطّ زمن مراحل النموّ للموسم النشط للحقل + المرحلة الحاليّة وKc الطوريّ.

    يقرأ الموسم النشط (crops + sowing_date) عبر الاتّصال المنطاقيّ (RLS)، ثمّ يبني
    الردّ من المنطق النقيّ في ``core.season_phenology``. صدق: لا موسم نشط/لا تاريخ
    بذار/محصول مجهول ⇒ ``available=False`` بسبب صريح (لا خطّ زمن مُلفَّق). 503 عند
    تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            crop, sowing_date, lat, lon = await _active_season_crop_and_sowing(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة مراحل نموّ الموسم", e) from e
    weather = await _season_thermal_time(user, crop, sowing_date, lat, lon)
    return _shape_phenology(crop, sowing_date, weather=weather)


@router.get("/api/v1/fields/{field_id}/stage-actions")
async def field_stage_actions(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """إجراءات الطور الحاليّ المقترَحة للموسم النشط — اقتراحات فقط (لا كتابة مهامّ).

    يقرأ الموسم النشط كما نقطة phenology، ثمّ يبني اقتراح الإجراء من المرحلة الحاليّة
    (``key_action_ar`` + ``name_ar``). صدق: لا موسم/محصول مجهول ⇒ ``available=False``.
    503 عند تعذّر القاعدة. لا تُنشَأ مهامّ في القاعدة من هذه النقطة.
    """
    try:
        async with tenant_connection(user) as conn:
            crop, sowing_date, lat, lon = await _active_season_crop_and_sowing(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة إجراءات الطور الحاليّ", e) from e
    weather = await _season_thermal_time(user, crop, sowing_date, lat, lon)
    return _shape_stage_actions(crop, sowing_date, weather=weather)
