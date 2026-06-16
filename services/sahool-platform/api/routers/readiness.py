"""api/routers/readiness.py — تقرير جاهزيّة الإنتاج (production readiness).

نقطة إدارة تعرض نتيجة مُدقّق الجاهزيّة (core.prod_readiness) على لقطة بيئة التشغيل
الحاليّة: بنود حاجبة (blockers) وتحذيرات أمنيّة/تشغيليّة. مُقيَّدة بصلاحيّة التدقيق
(AUDIT_VIEW) كبقيّة نقاط الإدارة. المكان الوحيد الذي تُقرأ فيه os.environ.
"""

from __future__ import annotations

import os

from core.prod_readiness import evaluate_readiness
from fastapi import APIRouter, Depends

from api.main import Permission, UserSchema, require_permission

router = APIRouter()


@router.get("/api/v1/admin/readiness")
async def production_readiness(
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """تقرير جاهزيّة الإنتاج من لقطة البيئة الحاليّة: ready + blockers + warnings."""
    return evaluate_readiness(dict(os.environ))
