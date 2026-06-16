"""api/routers/recommendations.py — التوصيات (Recommendations)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ السبع حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

import logging

from core.api_adapter import ApiRequest, handle_recommendation_request
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

# ApiRequest/handle_recommendation_request تُستورَدان مباشرةً من core.api_adapter —
# نفس الرمزين اللذين كان main يستوردهما (نُقل استيرادهما هنا لإزالة F401 من main
# بعد نقل دالّتي التوصية).
from api.field_models import FieldRecommendationRequest
from api.main import (
    OutcomeRecordRequest,
    Permission,
    RecommendationRequest,
    UserSchema,
    _db_unavailable,
    _resolve_recommendation_policy,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.post("/api/v1/recommendations")
def recommendations(
    req: RecommendationRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
):
    """نقطة التوصية الجوهرية — تستخدم api_adapter كاملاً."""
    # تحقّق tenant isolation
    if req.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant recommendation request forbidden")

    api_req = ApiRequest(
        user=user,
        payload=req.model_dump(),
        path="/api/v1/recommendations",
        method="POST",
    )
    resp = handle_recommendation_request(api_req)
    return JSONResponse(status_code=resp.status_code, content=resp.body)


@router.post("/api/v1/recommendations/for-field")
def recommendations_for_field(
    req: FieldRecommendationRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
):
    """توصية لحقل دون أن يبني العميل «شهادة الجودة» (validation) يدويّاً.

    الواجهة كانت تعجز عن استدعاء /api/v1/recommendations لأنّه يتطلّب dict
    validation معقّداً (خرج بوّابة الجودة). هنا نبنيه خادميّاً من ملاحظات
    المستأجر عبر validate_observations ثمّ نستدعي المحرّك الحقيقيّ نفسه. صدق:
    عند نقص الملاحظات تُعاد توصية «محجوبة/محدودة» تُبيّن ما يلزم قياسه — لا
    سيناريو مفبرَك، وهو السلوك المُصمَّم لبوّابة الجودة."""
    import os as _os
    from pathlib import Path as _Path

    import validate_observations as _vo

    # جذر بيانات المستأجر (قابل للضبط). غيابه ⇒ شهادة منخفضة الجودة بصدق
    # (لا اختراع ملاحظات)، فيُعيد المحرّك توصية محدودة تُرشد لما يجب قياسه.
    root = _os.getenv(
        "SAHOOL_TENANT_DATA_ROOT",
        _os.path.join(_os.path.dirname(__file__), "..", "tenants"),
    )
    # تقوية: نُطبّع المسار ونتأكّد أنّ مجلّد المستأجر داخل الجذر (دفاع ضدّ "../"
    # أو فواصل مسار في tenant_id — تجنّب قراءة بيانات خارج عزل المستأجر).
    root_path = _Path(root).resolve()
    tenant_dir = (root_path / str(user.tenant_id)).resolve()
    if not tenant_dir.is_relative_to(root_path):
        raise HTTPException(status_code=400, detail="معرّف مستأجر غير صالح")
    try:
        validation = _vo.validate(tenant_dir)
    except Exception as e:  # noqa: BLE001 — صدق: لا توصية بلا شهادة جودة
        raise HTTPException(status_code=503, detail=f"تعذّر بناء شهادة الجودة: {e}") from e

    api_req = ApiRequest(
        user=user,
        payload={
            "tenant_id": user.tenant_id,
            # لا نخلط farm_id بـfield_id (كيانان مختلفان؛ authorize يفحص
            # farm_ids_access). نمرّره كما هو؛ المستخدم محدود الصلاحيّة يُرسله،
            # وذو الوصول الشامل (farm_ids_access فارغة) يمرّ بـ"".
            "farm_id": req.farm_id,
            "field_id": req.field_id,
            "crop": req.crop,
            "validation": validation,
            "current_indicators": req.current_indicators,
            "growth_stage": req.growth_stage,
            "district_id": req.district_id,
        },
        path="/api/v1/recommendations/for-field",
        method="POST",
    )
    resp = handle_recommendation_request(api_req)
    return JSONResponse(status_code=resp.status_code, content=resp.body)


@router.get("/api/v1/recommendations/engines")
async def recommendation_engines(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """كتالوج محرّكات التوصيات + السياسة الفعليّة لهذا المستأجِر (استبطان).

    يُرجع: الكتالوج الكامل (list_engines)، السياسة الخام من settings (أو null)،
    والمُعرّفات الفعليّة التي ستعمل لهذا المستأجِر (effective_enabled). السياسة
    تُضبَط عبر النقطة الموجودة لا نقطة كتابة جديدة:
        PUT /api/v1/settings  مع scope='platform', key='recommendation_engines',
        value مثل {"disabled": ["yield"]}.
    """
    import json as _json

    from api.recommendations_hub import list_engines

    engines = list_engines()
    policy_value = None
    enabled_ids: set[str] | None = None
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT value FROM settings WHERE scope = 'platform' "
                "AND key = 'recommendation_engines'"
            )
        if row is not None:
            policy_value = row["value"]
            if isinstance(policy_value, str):
                policy_value = _json.loads(policy_value)
            enabled_ids = await _resolve_recommendation_policy(policy_value)
    except Exception:  # noqa: BLE001 — best-effort: تعذّر القراءة ⇒ افتراضيّ (null)
        logging.exception("recommendation engines: policy read failed")
        policy_value = None
        enabled_ids = None

    # المُعرّفات الفعليّة: عند غياب سياسة (None) ⇒ كلّ محرّك بـ default_enabled=True.
    if enabled_ids is None:
        effective = [e["id"] for e in engines if e["default_enabled"]]
    else:
        effective = [e["id"] for e in engines if e["id"] in enabled_ids]
    return {
        "engines": engines,
        "policy": policy_value,
        "effective_enabled": effective,
    }


@router.post("/api/v1/recommendations/economic-adaptation")
def economic_adaptation_endpoint(
    crop_options: list[dict],
    area_ha: float | None = None,
    annual_revenue_usd: float | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
):
    """يكيّف خيارات المحاصيل حسب القدرة الاقتصاديّة (اقتراح متدرّج لا فرض).

    متّسق مع استقلاليّة المزارع: كلّ الخيارات تبقى مرئيّة، الترتيب اقتراح.
    """
    from core.economic_adaptation import adapt_recommendation

    return adapt_recommendation(
        crop_options, area_ha=area_ha, annual_revenue_usd=annual_revenue_usd
    )


@router.get("/api/v1/recommendations/capacity-profiles")
def capacity_profiles_endpoint():
    """ملفّات طبقات القدرة الاقتصاديّة (مرجع شفّاف)."""
    from core.economic_adaptation import get_capacity_profiles

    return get_capacity_profiles()


@router.post("/api/v1/recommendations/candidates")
def generate_crop_candidates(
    candidates: list[dict],
    goal: str = "max_profit",
    top_n: int = 3,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
):
    """يولّد بدائل زراعيّة مُقيَّمة حسب هدف المزارع — كلّ الخيارات مرئيّة (الوكالة).

    candidates: قائمة خيارات، كلّ منها dict بصفات موثّقة (crop_id, name_ar, is_suited,
    water_need_level, upfront_cost_level, profit_potential_level, is_staple, drought_score)
    — تُملأ من محرّكات سهول (الملاءمة/الماء/الاقتصاد/تحمّل الجفاف). تقييم حتميّ شفّاف.
    goal ∈ {max_profit, food_security, min_water, drought_resilience}.
    """
    from core.engines.candidate_generator import (
        CropCandidate,
        FarmerGoal,
        generate_candidates,
    )

    try:
        g = FarmerGoal(goal)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"هدف غير معروف: {goal}") from e
    if not isinstance(top_n, int) or top_n < 1:
        raise HTTPException(status_code=422, detail="top_n يجب أن يكون عدداً صحيحاً موجباً")

    def _req_bool(c: dict, key: str) -> bool:
        # JSON يجب أن يكون true/false صريحاً (لا "false" نصّاً تصبح True بصمت)
        v = c.get(key, False)
        if not isinstance(v, bool):
            raise HTTPException(status_code=422, detail=f"{key} يجب أن يكون true/false")
        return v

    def _req_score(c: dict):
        v = c.get("drought_score")
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise HTTPException(status_code=422, detail="drought_score يجب أن يكون رقماً [0,1]")
        v = float(v)
        if not 0.0 <= v <= 1.0:
            raise HTTPException(status_code=422, detail="drought_score خارج المدى [0,1]")
        return v

    objs: list = []
    for c in candidates:
        if not isinstance(c, dict) or "crop_id" not in c:
            raise HTTPException(status_code=422, detail="كلّ خيار يجب أن يكون كائناً فيه crop_id")
        objs.append(
            CropCandidate(
                crop_id=str(c["crop_id"]),
                name_ar=str(c.get("name_ar", c["crop_id"])),
                is_suited=_req_bool(c, "is_suited"),
                water_need_level=str(c.get("water_need_level", "mid")),
                upfront_cost_level=str(c.get("upfront_cost_level", "mid")),
                profit_potential_level=str(c.get("profit_potential_level", "unknown")),
                is_staple=_req_bool(c, "is_staple"),
                drought_score=_req_score(c),
            )
        )

    return generate_candidates(objs, g, top_n=top_n)


@router.post("/api/v1/recommendations/outcomes", status_code=201)
async def record_recommendation_outcome(
    req: OutcomeRecordRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
):
    """يسجّل نتيجة توصية (توقّع/فعليّ + قبول/نضج) — مسار الكتابة لحلقة التعلّم (v49).

    تقرأ هذه الصفوفَ نقطتا learning/activation-status و prediction-calibration حيّاً.
    tenant عبر RLS (WITH CHECK يفرض المستأجِر). صدق: يسجّل المُرسَل فقط (لا اختراع).
    """
    # اتّساق: matured_within_lag يعني نضج نتيجة فعليّة — يستلزم actual_yield_t_ha.
    if req.matured_within_lag and req.actual_yield_t_ha is None:
        raise HTTPException(
            status_code=422,
            detail="matured_within_lag=true يستلزم actual_yield_t_ha (نتيجة فعليّة)",
        )
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """INSERT INTO recommendation_outcomes
                       (tenant_id, field_id, farm_id, season_id, crop, recommendation_id,
                        predicted_yield_t_ha, actual_yield_t_ha, accepted, matured_within_lag,
                        outcome_recorded_at)
                   VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                           CASE WHEN $8 IS NOT NULL THEN now() ELSE NULL END)
                   RETURNING outcome_id""",
                str(getattr(user, "tenant_id", "")),
                req.field_id,
                req.farm_id,
                req.season_id,
                req.crop,
                req.recommendation_id,
                req.predicted_yield_t_ha,
                req.actual_yield_t_ha,
                req.accepted,
                req.matured_within_lag,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تسجيل نتيجة التوصية", e) from e
    return {"outcome_id": row["outcome_id"], "recorded": True}
