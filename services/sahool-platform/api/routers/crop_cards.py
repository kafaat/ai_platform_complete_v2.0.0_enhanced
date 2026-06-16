"""api/routers/crop_cards.py — بطاقات المحاصيل والأصناف (Crop & Variety Cards).

ميزة «بطاقة المحصول»: تعرض المعرفة المرجعيّة المُهيكَلة (محايدة الموقع) لبطاقات
المحاصيل (فيزياء/فسيولوجيا: Kc، ملوحة، حراري، حاكمات) وبطاقات الأصناف المحلّية
(UPOV/Bioversity: جواز + تمايز + صفات)، من ``core.crop_cards`` (ملفّات YAML مُتحقَّقة،
بلا قاعدة بيانات). مُقيَّدة بالدور (FIELD_VIEW) اتّساقاً مع لوحات الحقل المرجعيّة.
"""

from __future__ import annotations

from datetime import date

from core.crop_cards.loader import (
    list_crop_cards,
    list_variety_cards,
    load_crop_card,
    load_variety_card,
    varieties_of_crop,
)
from core.variety_suitability import (
    expected_harvest,
    salinity_suitability,
    variety_disease_watch,
)
from fastapi import APIRouter, Depends, HTTPException, Query

from api.main import Permission, UserSchema, require_permission

router = APIRouter()


@router.get("/api/v1/crop-cards")
async def crop_cards_index(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """فهرس بطاقات المحاصيل المتاحة + أصناف كلّ محصول (معرفة مرجعيّة، لا قاعدة)."""
    crops = []
    for cid in list_crop_cards():
        card = load_crop_card(cid)
        crops.append(
            {
                "crop_id": cid,
                "name_ar": (card or {}).get("name_ar"),
                "name_en": (card or {}).get("name_en"),
                "crop_family": (card or {}).get("crop_family"),
                "varieties": varieties_of_crop(cid),
            }
        )
    return {
        "total_crops": len(crops),
        "total_varieties": len(list_variety_cards()),
        "crops": crops,
        "note_ar": "بطاقات محايدة الموقع — فيزياء/فسيولوجيا بمصادر موثّقة، لا معايرة/إنتاج.",
    }


@router.get("/api/v1/crop-cards/crop/{crop_id}")
async def crop_card_detail(
    crop_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """بطاقة محصول كاملة (فيزياء/فسيولوجيا) + معرّفات أصنافها. 404 إن لم تُوجَد."""
    card = load_crop_card(crop_id)
    if card is None:
        raise HTTPException(status_code=404, detail="بطاقة المحصول غير موجودة")
    return {"card": card, "varieties": varieties_of_crop(crop_id)}


@router.get("/api/v1/crop-cards/variety/{variety_id}")
async def variety_card_detail(
    variety_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """بطاقة صنف كاملة (جواز + تمايز + صفات). 404 إن لم تُوجَد."""
    card = load_variety_card(variety_id)
    if card is None:
        raise HTTPException(status_code=404, detail="بطاقة الصنف غير موجودة")
    return card


# ─── دعم القرار الواعي بالصنف (variety_suitability) — حساب لكلّ حقل ──────────
@router.get("/api/v1/crop-cards/variety/{variety_id}/salinity-suitability")
async def variety_salinity_suitability(
    variety_id: str,
    ece: float = Query(description="ملوحة التربة/الماء المقيسة ECe (dS/m)"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """ملاءمة ملوحة حقل لصنف: عتبة الصنف (عتبة المحصول + معامل تحمّل الصنف) مقابل
    القياس + خسارة الغلّة المتوقّعة (Maas-Hoffman). 404 إن جُهِل الصنف."""
    if load_variety_card(variety_id) is None:
        raise HTTPException(status_code=404, detail="بطاقة الصنف غير موجودة")
    return salinity_suitability(variety_id, ece)


@router.get("/api/v1/crop-cards/variety/{variety_id}/expected-harvest")
async def variety_expected_harvest(
    variety_id: str,
    sowing_date: str = Query(description="تاريخ البذار ISO (YYYY-MM-DD)"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تواريخ التزهير/الحصاد المتوقّعة للصنف من تاريخ بذار + أيّام النضج (phenology).
    404 إن جُهِل الصنف، 422 على تاريخ غير صالح."""
    if load_variety_card(variety_id) is None:
        raise HTTPException(status_code=404, detail="بطاقة الصنف غير موجودة")
    try:
        sow = date.fromisoformat(sowing_date.strip())
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=422, detail="تاريخ بذار غير صالح (YYYY-MM-DD)") from e
    return expected_harvest(variety_id, sow)


@router.get("/api/v1/crop-cards/variety/{variety_id}/disease-watch")
async def variety_disease_watch_endpoint(
    variety_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مقاومات الصنف المُوثَّقة + إرشاد المسح الميدانيّ. 404 إن جُهِل الصنف."""
    if load_variety_card(variety_id) is None:
        raise HTTPException(status_code=404, detail="بطاقة الصنف غير موجودة")
    return variety_disease_watch(variety_id)
