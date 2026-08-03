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
from datetime import UTC, date, datetime

from core.season_phenology import (
    current_stage,
    resolve_crop_id,
    season_timeline,
    stage_kc,
)
from fastapi import APIRouter, Depends, HTTPException, Query

from api.canonical_phenology_state import (
    PhenologyObservation,
    build_canonical_phenology_state,
    state_payload,
)
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


async def _active_season_identity(conn, field_id: str):
    """(season_id، الصنف) للموسم النشط — ما تحتاجه الحالة الكنسيّة زيادةً على أعلاه.

    استعلام منفصل عن ``_active_season_crop_and_sowing`` عمداً: ذاك يخدم الردّ
    الافتراضيّ ولا يجوز أن يتغيّر شكله من أجل مسار اختياريّ.
    """
    row = await conn.fetchrow(
        "SELECT season_id, cultivar FROM seasons "
        "WHERE field_id = $1 AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        field_id,
    )
    if row is None:
        return None, None
    return row["season_id"], row["cultivar"]


async def _season_phenology_observations(conn, field_id: str, season_id: str):
    """رصدات الطور المُدامة (v224) للحقل/الموسم — مصدرها الوحيد جدولها.

    لا تُختلَق رصدة عند غياب الجدول أو خلوّه: الغياب يعني **لا رصد**، وهو ما تعبّر
    عنه الحالة الكنسيّة بحالة ``predicted`` لا بمرحلة مُلفَّقة تُقدَّم كأنّها مرصودة.
    """
    rows = await conn.fetch(
        "SELECT observation_id, source, stage, observed_at, confidence, evidence_digest "
        "FROM phenology_observations WHERE field_id = $1 AND season_id = $2 "
        "ORDER BY observed_at DESC",
        field_id,
        season_id,
    )
    return [
        PhenologyObservation(
            observation_id=row["observation_id"],
            source=row["source"],
            stage=row["stage"],
            observed_at=row["observed_at"],
            confidence=float(row["confidence"]),
            evidence_digest=row["evidence_digest"],
        )
        for row in rows
    ]


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
    canonical: bool = Query(
        False,
        description=(
            "يُرجِع الحالة الطوريّة الكنسيّة (مرصود/متوقَّع مفصولان + نَسَب الأدلّة) "
            "بدل خطّ الزمن التقويميّ. الافتراضيّ False فالردّ القائم لا يتغيّر."
        ),
    ),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """خطّ زمن مراحل النموّ للموسم النشط للحقل + المرحلة الحاليّة وKc الطوريّ.

    يقرأ الموسم النشط (crops + sowing_date) عبر الاتّصال المنطاقيّ (RLS)، ثمّ يبني
    الردّ من المنطق النقيّ في ``core.season_phenology``. صدق: لا موسم نشط/لا تاريخ
    بذار/محصول مجهول ⇒ ``available=False`` بسبب صريح (لا خطّ زمن مُلفَّق). 503 عند
    تعذّر القاعدة.

    ``?canonical=true`` (اختياريّ، **بلا مسار جديد** — سابقة INT-004A): يُرجِع
    ``canonical_phenology_state`` الذي **يفصل المرصود عن المتوقَّع**. الردّ الافتراضيّ
    يشتقّ ``current_stage`` من عمر التقويم وحده ويقدّمه بلا تمييز؛ الحالة الكنسيّة
    تجعل رصدة الحقل الحديثة الموثوقة هي الآمرة، وتعلن ``blocked`` عند تعارض رصدتين
    عاليتي الثقة بدل الارتداد الصامت إلى التقويم.

    **حدّ صدق مقيس:** ``accumulated_gdd`` يُمرَّر ``None`` هنا. تراكميّ GDD القانونيّ
    مملوك لمحرّك الطقس ويحتاج سلسلة حرارة يوميّة لا تملكها هذه النقطة، و
    ``wofost_seasons.gdd_accumulated`` مخرَج محاكاة لا قياس — تمريره كان سيغسل ناتج
    محاكاة كأنّه حرارة مقيسة. فالنتيجة تُعلِن القيد ولا تخترع رقماً.
    """
    try:
        async with tenant_connection(user) as conn:
            crop, sowing_date = await _active_season_crop_and_sowing(conn, field_id)
            if not canonical:
                return _shape_phenology(crop, sowing_date)
            season_id, cultivar_id = await _active_season_identity(conn, field_id)
            if season_id is None or sowing_date is None or not crop:
                return {
                    "available": False,
                    "reason_ar": "لا موسم نشط بتاريخ بذار ومحصول — لا حالة طوريّة كنسيّة",
                }
            observations = await _season_phenology_observations(conn, field_id, season_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة مراحل نموّ الموسم", e) from e
    state = build_canonical_phenology_state(
        tenant_id=str(user.tenant_id),
        field_id=field_id,
        season_id=str(season_id),
        crop=crop,
        cultivar_id=cultivar_id,
        sowing_date=sowing_date,
        as_of=datetime.now(UTC),
        accumulated_gdd=None,
        observations=observations,
    )
    return {"available": True, **state_payload(state)}


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
