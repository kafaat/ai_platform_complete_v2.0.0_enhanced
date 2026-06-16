"""api/routers/districts.py — طبقة المعرفة الإقليميّة (Districts knowledge layer).

تعرض «نوافذ خطر الآفات» الإقليميّة (pest risk windows) لكلّ منطقة زراعيّة-بيئيّة،
من ``core.districts`` (ملفّات YAML مُتحقَّقة، بلا قاعدة بيانات). خلافاً لبطاقات
المحاصيل (محايدة الموقع)، هذه الطبقة إقليميّة بالتصميم. القرائن معرفيّة
(knowledge priors) تُصقَل بالمسح/الإرشاد المحلّيّ. مُقيَّدة بالدور (FIELD_VIEW)
اتّساقاً مع لوحات الحقل المرجعيّة.
"""

from __future__ import annotations

from core.districts.loader import (
    active_pests,
    list_districts,
    load_district,
)
from fastapi import APIRouter, Depends, HTTPException, Query

from api.main import Permission, UserSchema, require_permission

router = APIRouter()


@router.get("/api/v1/districts")
async def districts_index(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """فهرس المناطق المتاحة + ملخّص (الاسم/المنطقة الزراعيّة-البيئيّة)."""
    districts = []
    for did in list_districts():
        card = load_district(did)
        districts.append(
            {
                "district_id": did,
                "name_ar": (card or {}).get("name_ar"),
                "agro_ecological_zone_ar": (card or {}).get("agro_ecological_zone_ar"),
                "altitude_range_m": (card or {}).get("altitude_range_m"),
            }
        )
    return {
        "total_districts": len(districts),
        "districts": districts,
        "note_ar": "نوافذ خطر إقليميّة (قرائن معرفيّة) تُصقَل بالمسح الميدانيّ والإرشاد المحلّيّ.",
    }


@router.get("/api/v1/districts/{district_id}")
async def district_detail(
    district_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """بطاقة منطقة كاملة (نوافذ خطر الآفات بمصادرها). 404 إن لم تُوجَد."""
    card = load_district(district_id)
    if card is None:
        raise HTTPException(status_code=404, detail="المنطقة غير موجودة")
    return card


@router.get("/api/v1/districts/{district_id}/active-pests")
async def district_active_pests(
    district_id: str,
    month: int = Query(description="الشهر (1–12)"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """الآفات النشطة في الشهر المطلوب لمنطقة. 422 إن لم يكن الشهر 1..12،
    404 إن جُهِلت المنطقة. قائمة فارغة صادقة إن لم تنطبق نافذة."""
    if not (1 <= month <= 12):
        raise HTTPException(status_code=422, detail="الشهر يجب أن يكون بين 1 و12")
    if load_district(district_id) is None:
        raise HTTPException(status_code=404, detail="المنطقة غير موجودة")
    pests = active_pests(district_id, month)
    return {
        "district_id": district_id,
        "month": month,
        "active_pest_count": len(pests),
        "active_pests": pests,
    }
