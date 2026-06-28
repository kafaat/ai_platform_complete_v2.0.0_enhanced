"""routers/health.py — مسارات التشغيل/الصحّة (health/readiness/metrics)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات
مطابقة. التبعيّات المشتركة (الحالة/المساعِدات) تبقى في ``main`` وتُشار إليها
عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import main
from fastapi import APIRouter
from starlette.responses import Response

router = APIRouter()


@router.get("/healthz")
@router.get("/health")
async def healthz():
    return {"status": "alive", "service": "vegetation-analysis"}


@router.get("/readyz")
async def readyz():
    # بلا تبعيّة صلبة قصداً: لا pool قاعدة خاصّ بها (راجع رأس الملفّ)، ونشر NATS
    # محاولة-أفضل (فشله يُسجَّل تحذيراً ولا يُعطّل الخدمة). لا شيء صلب ننتظره ⇒ جاهز.
    return {"status": "ready"}


@router.get("/metrics")
async def metrics():
    return Response(main.generate_latest(), media_type=main.CONTENT_TYPE_LATEST)
