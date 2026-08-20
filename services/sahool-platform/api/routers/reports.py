"""api/routers/reports.py — التقارير والملخّصات (Reports & Summaries)
======================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الأربع حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

# نماذج/مساعِدات تقرير العمليّة (FieldReport/OperationReport/operation_to_csv)
# تُستورَد مباشرةً من وحدتها — نفس الرموز التي كان main يُعيد تصديرها (نُقل
# استيرادها هنا لإزالة F401 من main بعد نقل الدالّة).
from api.alert_models import _row_to_alert
from api.analytics_shapers import _count_by_key, _shape_area_by_crop, _shape_farm_summary
from api.main import (
    OperationReportRequest,
    Permission,
    UserSchema,
    _db_unavailable,
    get_current_user,
    require_permission,
    tenant_connection,
)
from api.reports import FieldReport, OperationReport, operation_to_csv

router = APIRouter()


@router.get("/api/v1/reports/farm-summary")
async def report_farm_summary(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """ملخّص المزرعة على مستوى المستأجِر — عدّادات حيّة من الجداول القائمة.

    يُجمّع: عدد المزارع/الحقول، إجماليّ المساحة، المواسم النشطة، العمليّات حسب
    الحالة، التنبيهات المفتوحة (active)، والمساحة حسب المحصول. مُرشَّح بالمستأجِر
    (RLS + tenant_id). 503 عند تعذّر القاعدة — لا أرقام مُلفَّقة.
    """
    try:
        async with tenant_connection(user) as conn:
            tid = str(user.tenant_id)
            farms_count = await conn.fetchval(
                "SELECT COUNT(*) FROM farms WHERE tenant_id = $1::uuid", tid
            )
            fields_count = await conn.fetchval(
                "SELECT COUNT(*) FROM fields WHERE tenant_id = $1::uuid", tid
            )
            total_area = await conn.fetchval(
                "SELECT COALESCE(SUM(area_ha), 0) FROM fields WHERE tenant_id = $1::uuid", tid
            )
            active_seasons = await conn.fetchval(
                "SELECT COUNT(*) FROM seasons WHERE tenant_id = $1::uuid AND status = 'active'",
                tid,
            )
            activity_rows = await conn.fetch(
                "SELECT status, COUNT(*) AS count FROM activities "
                "WHERE tenant_id = $1::uuid GROUP BY status",
                tid,
            )
            open_alerts = await conn.fetchval(
                "SELECT COUNT(*) FROM alerts WHERE tenant_id = $1::uuid AND status = 'active'",
                tid,
            )
            crop_rows = await conn.fetch(
                "SELECT crop, COALESCE(SUM(area_ha), 0) AS total_area_ha FROM fields "
                "WHERE tenant_id = $1::uuid GROUP BY crop",
                tid,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة ملخّص المزرعة", e) from e
    return _shape_farm_summary(
        farms_count=farms_count,
        fields_count=fields_count,
        total_area_ha=total_area,
        active_seasons_count=active_seasons,
        activities_by_status=_count_by_key(activity_rows, "status"),
        open_alerts_count=open_alerts,
        area_by_crop=_shape_area_by_crop(crop_rows),
    )


@router.get("/api/v1/reports/field/{field_id}/summary")
async def report_field_summary(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """ملخّص حقل واحد — مساحته/محصوله/تربته + موسمه النشط + عمليّاته + تنبيهاته.

    يؤكّد أنّ الحقل يخصّ المستأجِر (404) قبل التجميع. العمليّات تُعدّ حسب النوع
    والحالة، والتنبيهات الأخيرة تُعرض (٥). مُرشَّح بالمستأجِر (RLS). 503 عند تعذّر
    القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            field = await conn.fetchrow(
                "SELECT field_id, name, area_ha, crop, soil_type FROM fields WHERE field_id = $1",
                field_id,
            )
            if field is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            season = await conn.fetchrow(
                "SELECT season_id, crops, cultivar, sowing_date, season_end, status "
                "FROM seasons WHERE field_id = $1 AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1",
                field_id,
            )
            by_type_rows = await conn.fetch(
                "SELECT activity_type, COUNT(*) AS count FROM activities "
                "WHERE field_id = $1 GROUP BY activity_type",
                field_id,
            )
            by_status_rows = await conn.fetch(
                "SELECT status, COUNT(*) AS count FROM activities "
                "WHERE field_id = $1 GROUP BY status",
                field_id,
            )
            recent_alert_rows = await conn.fetch(
                "SELECT alert_id, field_id, alert_type, severity, title_ar, "
                "message_ar, status, created_at FROM alerts "
                "WHERE field_id = $1 ORDER BY created_at DESC LIMIT 5",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة ملخّص الحقل", e) from e

    import json as _json

    current_season = None
    if season is not None:
        crops = season["crops"]
        if isinstance(crops, str):
            try:
                crops = _json.loads(crops)
            except (ValueError, TypeError):
                crops = []
        current_season = {
            "season_id": season["season_id"],
            "crops": crops if isinstance(crops, list) else [],
            "cultivar": season["cultivar"],
            "sowing_date": season["sowing_date"].isoformat() if season["sowing_date"] else None,
            "season_end": season["season_end"].isoformat() if season["season_end"] else None,
            "status": season["status"],
        }
    by_status = _count_by_key(by_status_rows, "status")
    return {
        "field_id": field["field_id"],
        "name": field["name"],
        "area_ha": float(field["area_ha"]) if field["area_ha"] is not None else 0.0,
        "crop": field["crop"],
        "soil_type": field["soil_type"],
        "current_season": current_season,
        "activities_total": sum(by_status.values()),
        "activities_by_type": _count_by_key(by_type_rows, "activity_type"),
        "activities_by_status": by_status,
        "recent_alerts": [_row_to_alert(r).model_dump() for r in recent_alert_rows],
    }


def _soil_lab_signals(soil_result) -> dict:
    """يستخرج ph/مادة عضويّة/N/P/K من نتيجة فحص التربة (JSONB) بمفاتيح متسامحة.

    نمط ``_extract_ec`` (field_state_projection): أيّ قيمة غائبة ⇒ None — لا اختلاق.
    N/P/K معلوماتيّة فقط (بُعد المغذّيات يُعلَن needs_data بصدق مهما توفّرت).
    """
    import json as _json

    if isinstance(soil_result, str):
        try:
            soil_result = _json.loads(soil_result)
        except (ValueError, TypeError):
            soil_result = None
    if not isinstance(soil_result, dict):
        return {"ph": None, "organic_matter": None, "n_kg_ha": None, "p_ppm": None, "k_mg_kg": None}

    def _pick(*keys):
        for k in keys:
            v = soil_result.get(k)
            if isinstance(v, int | float) and not isinstance(v, bool):
                return float(v)
        return None

    return {
        "ph": _pick("ph", "pH", "soil_ph"),
        "organic_matter": _pick("organic_matter", "om", "om_pct", "organic_matter_pct"),
        "n_kg_ha": _pick("n_kg_ha", "nitrogen_kg_ha", "n"),
        "p_ppm": _pick("p_ppm", "phosphorus_ppm", "p"),
        "k_mg_kg": _pick("k_mg_kg", "potassium_mg_kg", "k"),
    }


@router.get("/api/v1/fields/{field_id}/sustainability")
async def field_sustainability(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مؤشّر استدامة الحقل (تربة + مياه + مغذّيات، بلا كربون) — تقرير قراءة فقط (RLS).

    يُعيد استخدام الإشارات الكنسيّة (``salinity_class``/``water_stress_class``/نضارة
    التربة) من الحالة القانونيّة + تحليل التربة (pH/مادة عضويّة) — **لا حساب جديد، لا
    تغيير حالة/قرار**. صدق: بُعد المغذّيات يُعلَن ``needs_data`` (توازن NPK غير مقيس —
    P محجوب، K معطّل)، بُعد غائب يُستبعَد (لا عقاب على ما لا يُقاس). 404 لحقل خارج
    المستأجِر؛ القاعدة غير مفعّلة/متعذّرة ⇒ 503 (لا استدامة مُلفَّقة).
    """
    from api.field_state_projection import recompute_field_state
    from api.field_sustainability import compute_field_sustainability

    try:
        async with tenant_connection(user) as conn:
            field = await conn.fetchrow("SELECT field_id FROM fields WHERE field_id = $1", field_id)
            if field is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            result = await recompute_field_state(conn, field_id)
            soil_row = await conn.fetchrow(
                "SELECT result FROM soil_lab_tests "
                "WHERE field_id = $1 AND status IN ('approved', 'published') "
                "AND sampled_on IS NOT NULL ORDER BY sampled_on DESC LIMIT 1",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حساب استدامة الحقل", e) from e

    state = result["state"]
    truths = (state.get("agronomic") or {}).get("operational_truths") or {}
    water_stress = state.get("water_stress") or {}
    inputs = state.get("inputs") or {}
    signals = {
        "salinity_class": truths.get("salinity_class"),
        "water_stress_class": water_stress.get("water_stress_class"),
        "soil_age_days": inputs.get("soil_age_days"),
        **_soil_lab_signals(soil_row["result"] if soil_row else None),
    }
    return {"field_id": field_id, "sustainability": compute_field_sustainability(signals)}


@router.get("/api/v1/reports/season/{season_id}/summary")
async def report_season_summary(
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """ملخّص موسم واحد — محصوله/صنفه/تواريخه + عدد المراحل + العمليّات المرتبطة.

    يؤكّد أنّ الموسم يخصّ المستأجِر (404). عدد المراحل من مصفوفة stages (JSONB)،
    والعمليّات المرتبطة تُعدّ بـseason_id. مُرشَّح بالمستأجِر (RLS). 503 عند تعذّر
    القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            season = await conn.fetchrow(
                "SELECT season_id, field_id, crops, cultivar, irrigation_type, "
                "sowing_date, season_end, stages, status FROM seasons "
                "WHERE season_id = $1",
                season_id,
            )
            if season is None:
                raise HTTPException(status_code=404, detail="الموسم غير موجود ضمن هذا المستأجِر")
            activities_count = await conn.fetchval(
                "SELECT COUNT(*) FROM activities WHERE season_id = $1", season_id
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة ملخّص الموسم", e) from e

    import json as _json

    def _arr(v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except (ValueError, TypeError):
                return []
        return v or []

    crops = _arr(season["crops"])
    stages = _arr(season["stages"])
    return {
        "season_id": season["season_id"],
        "field_id": season["field_id"],
        "crops": crops if isinstance(crops, list) else [],
        "cultivar": season["cultivar"],
        "irrigation_type": season["irrigation_type"],
        "sowing_date": season["sowing_date"].isoformat() if season["sowing_date"] else None,
        "season_end": season["season_end"].isoformat() if season["season_end"] else None,
        "status": season["status"],
        "stage_count": len(stages) if isinstance(stages, list) else 0,
        "activities_count": int(activities_count or 0),
    }


@router.post("/api/v1/reports/operation", response_class=PlainTextResponse)
def operation_report_csv(
    req: OperationReportRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تقرير المزرعة كاملة كـCSV (ثنائي اللغة + BOM للإكسل).

    عزل المستأجِر: التقرير نقيّ ولا يقرأ من DB، لكن جسم الطلب لا يجوز أن
    يفرض tenant_id أو يخلط حقول مستأجر آخر داخل CSV مُصدَّر.
    """
    # توحيد main↔cert: طبِّع str(...) على الطرفين — user.tenant_id قد يكون UUID والجسم str
    # (أو العكس)؛ المقارنة الخام تُنتج 403 كاذباً للجميع. str() يجعلهما متوافقَين.
    _uid = str(user.tenant_id)
    if str(req.tenant_id) != _uid:
        raise HTTPException(status_code=403, detail="tenant_mismatch")
    if any(str(f.tenant_id) != _uid for f in req.fields):
        raise HTTPException(status_code=403, detail="field_tenant_mismatch")

    fields = [
        FieldReport(
            field_id=f.field_id,
            field_name_ar=f.field_name_ar,
            farm_id=f.farm_id,
            tenant_id=f.tenant_id,
            area_ha=f.area_ha,
            crop=f.crop,
            season_label=f.season_label,
            planting_date=f.planting_date,
            harvest_date=f.harvest_date,
            lifecycle_stage=f.lifecycle_stage,
            irrigation_events=f.irrigation_events,
            total_water_m3=f.total_water_m3,
            fertilizer_events=f.fertilizer_events,
            total_nitrogen_kg=f.total_nitrogen_kg,
            avg_ndvi=f.avg_ndvi,
            estimated_yield_kg_ha=f.estimated_yield_kg_ha,
        )
        for f in req.fields
    ]
    report = OperationReport(
        tenant_id=req.tenant_id,
        operation_name_ar=req.operation_name_ar,
        fields=fields,
        period_start=req.period_start,
        period_end=req.period_end,
        generated_at=datetime.now(UTC).isoformat(),
    )
    return operation_to_csv(report, lang=req.lang)


@router.post("/api/v1/reports/build")
def build_report(
    body: dict,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يبني **مواصفة تقرير مُتحقَّق منها** من اختيار المستخدم — دالّة نقيّة (لا قاعدة).

    جسم الطلب هو اختيار التقرير ({"fields": [...], "entity"?, "filters"?}). يُعيد
    المواصفة المُتحقَّق منها + resolved_fields (metadata الحقول) + warnings (حقول
    مجهولة/كيان غير صالح...). هذا يُعيد **المواصفة فقط** لا بيانات مُجمَّعة — تجميع
    البيانات/التصيير (CSV/PDF) متابعة لاحقة. 422 عند اختيار غير صالح بنيويّاً."""
    from api.report_builder import build_report_spec

    try:
        return build_report_spec(body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
