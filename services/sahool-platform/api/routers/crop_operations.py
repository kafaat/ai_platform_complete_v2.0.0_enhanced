"""api/routers/crop_operations.py — تقويم العمليّات الحقليّة المرتبط بمراحل النموّ.

ميزة «تقويم العمليّات»: تعرض الخريطة المُهيكَلة (محايدة الموقع) من كلّ مرحلة نموّ
طوريّة (FAO-56) إلى قائمة العمليّات الحقليّة المُصنَّفة الموصى بها، من
``core.crop_operations`` (بناءً على فينولوجيا بطاقة المحصول، بلا قاعدة بيانات).

أغنى من ``/api/v1/fields/{id}/stage-actions`` (إجراء المرحلة الحاليّة المفرد فقط):
هنا التقويم الكامل لكلّ مراحل المحصول بعمليّات متعدّدة مُصنَّفة لكلّ مرحلة. مُقيَّدة
بالدور (FIELD_VIEW) اتّساقاً مع لوحات الحقل/البطاقات المرجعيّة.
"""

from __future__ import annotations

from core.crop_cards.loader import load_crop_card
from core.crop_operations import crop_operations_calendar
from fastapi import APIRouter, Depends, HTTPException

from api.main import Permission, UserSchema, require_permission

router = APIRouter()


@router.get("/api/v1/crops/{crop_id}/operations-calendar")
async def crop_operations_calendar_endpoint(
    crop_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تقويم العمليّات الكامل لمحصول: كلّ مرحلة نموّ + عمليّاتها المُصنَّفة. 404 إن لم تُوجَد بطاقة المحصول."""
    if load_crop_card(crop_id) is None:
        raise HTTPException(status_code=404, detail="بطاقة المحصول غير موجودة")
    return crop_operations_calendar(crop_id)
