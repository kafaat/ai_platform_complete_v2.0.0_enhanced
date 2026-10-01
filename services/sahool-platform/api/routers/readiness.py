"""api/routers/readiness.py — تقرير جاهزيّة الإنتاج (production readiness).

نقطة إدارة تعرض نتيجة مُدقّق الجاهزيّة (core.prod_readiness) على لقطة بيئة التشغيل
الحاليّة: بنود حاجبة (blockers) وتحذيرات أمنيّة/تشغيليّة. مُقيَّدة بصلاحيّة التدقيق
(AUDIT_VIEW) كبقيّة نقاط الإدارة. المكان الوحيد الذي تُقرأ فيه os.environ.
"""

from __future__ import annotations

import logging
import os

from core.prod_readiness import _truthy, evaluate_readiness
from fastapi import APIRouter, Depends

from api.main import Permission, UserSchema, require_permission

router = APIRouter()

# SAHOOL-DEBUG-FLAG-INVISIBLE-AT-RUNTIME-01: دخولُ dev يُسجِّل تحذيراً عند الإقلاع
# (`main.py:165`) فتُقاس حالتُه من سجلّ Railway بلا قراءة القيم؛ و`SAHOOL_DEBUG` لم يكن
# يُسجِّل شيئاً فلا تُقاس حالتُه إلّا من اللوحة. سطرٌ واحد عند الاستيراد (والموجِّهُ يُستورَد
# عند الإقلاع) يُسجِّل **الحالةَ لا القيمة**. `main.py` عند سقف أسطره، فالسطرُ هنا.
DEBUG_FLAG_STATE = "on" if _truthy(os.environ.get("SAHOOL_DEBUG")) else "off"
logging.getLogger(__name__).warning("SAHOOL_DEBUG=%s", DEBUG_FLAG_STATE)


@router.get("/api/v1/admin/readiness")
async def production_readiness(
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """تقرير جاهزيّة الإنتاج من لقطة البيئة الحاليّة: ready + blockers + warnings."""
    return evaluate_readiness(dict(os.environ))
