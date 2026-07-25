"""api/routers/varieties.py — كتالوج الأصناف المرجعيّ (قراءة صرفة، reference-only).

يُقدّم سِجِلّ أصناف الحبوب الغذائيّة اليمنيّة الموثّق المصدر عبر ``/api/v1/varieties/*``.
**قراءة فقط**: لا كتابة، ولا قرار. كلّ ردّ يحمل بوّابة الحوكمة الصريحة
``decision_engine_use_status = reference_only_not_operational`` — البيانات مرجعٌ للعرض/الخبير،
محجوبةٌ عن التنفيذ الآليّ حتى تحقّق خبير (DECISION-CENTER-UNIFY-01). يُسجَّل الموجِّه تلقائيّاً
عبر ``router_registry`` (كلّ وحدة في ``api/routers/`` تُصدّر ``router``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.food_grain_varieties import (
    REFERENCE_ONLY_STATUS,
    catalog_metadata,
    get_food_grain_variety,
    list_food_grain_varieties,
    quality_issues,
)
from api.main import UserSchema, get_current_user

router = APIRouter()


@router.get("/api/v1/varieties/food-grains")
def food_grain_varieties_endpoint(
    crop_code: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """كتالوج أصناف الحبوب الغذائيّة اليمنيّة الموثّق (اختياريّاً مُرشَّح بـ``crop_code``).

    مرجعيّ فقط: ``decision_engine_use_status=reference_only_not_operational`` — لا يُغذّي
    القرار آليّاً. يُرجِع الميتاداتا (المصدر/النَسَب) + الأصناف + قضايا الجودة (شفافيّة).
    """
    varieties = list_food_grain_varieties(crop_code=crop_code)
    return {
        "decision_engine_use_status": REFERENCE_ONLY_STATUS,
        "metadata": catalog_metadata(),
        "count": len(varieties),
        "varieties": varieties,
        "quality_issues": quality_issues(),
    }


@router.get("/api/v1/varieties/food-grains/{variety_id}")
def food_grain_variety_detail_endpoint(
    variety_id: str,
    user: UserSchema = Depends(get_current_user),
):
    """صنفٌ واحد بمعرّفه — مرجعيّ فقط (نفس بوّابة الحوكمة). 404 إن لم يوجد."""
    variety = get_food_grain_variety(variety_id)
    if variety is None:
        raise HTTPException(status_code=404, detail="variety not found in verified catalog")
    return {
        "decision_engine_use_status": REFERENCE_ONLY_STATUS,
        "variety": variety,
    }
