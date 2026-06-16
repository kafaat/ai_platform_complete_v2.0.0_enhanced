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

from core.season_phenology import (
    current_stage,
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


def _shape_phenology(crop: str | None, sowing_date: date | None, today: date | None = None) -> dict:
    """يشكّل ردّ الـphenology من اسم محصول + تاريخ بذار (دالّة نقيّة، لا قاعدة).

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
    stage = current_stage(crop_id, das)
    return {
        "available": True,
        "crop": crop,
        "crop_id": crop_id,
        "sowing_date": sowing_date.isoformat(),
        "days_after_sowing": das,
        "current_stage": stage,
        "current_stage_kc": stage_kc(crop_id, das),
        "timeline": timeline,
    }


def _shape_stage_actions(
    crop: str | None, sowing_date: date | None, today: date | None = None
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
    stage = current_stage(crop_id, das)
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
        "suggestions": suggestions,
        "note_ar": "اقتراحات إرشاديّة فقط — لا تُنشَأ مهامّ تلقائيّاً",
    }


async def _active_season_crop_and_sowing(conn, field_id: str):
    """يقرأ (اسم المحصول، تاريخ البذار) للموسم النشط للحقل — كما ``main``.

    SELECT crops, sowing_date FROM seasons WHERE field_id=$1 AND status='active'
    ORDER BY created_at DESC LIMIT 1. يتدهور لمحصول الحقل (fields.crop) إن غاب
    أوّل محصول للموسم. غياب الموسم ⇒ (محصول الحقل، None).
    """
    field_row = await conn.fetchrow("SELECT crop FROM fields WHERE field_id = $1", field_id)
    fallback_crop = field_row["crop"] if field_row is not None else None
    season = await conn.fetchrow(
        "SELECT crops, sowing_date FROM seasons "
        "WHERE field_id = $1 AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        field_id,
    )
    if season is None:
        return fallback_crop, None
    crop = _first_season_crop(season["crops"], fallback_crop)
    return crop, season["sowing_date"]


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
            crop, sowing_date = await _active_season_crop_and_sowing(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة مراحل نموّ الموسم", e) from e
    return _shape_phenology(crop, sowing_date)


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
            crop, sowing_date = await _active_season_crop_and_sowing(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة إجراءات الطور الحاليّ", e) from e
    return _shape_stage_actions(crop, sowing_date)
