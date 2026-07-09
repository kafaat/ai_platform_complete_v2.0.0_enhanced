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
    return {"status": "alive", "service": "vegetation-analysis-service"}


@router.get("/readyz")
async def readyz():
    # بلا تبعيّة صلبة قصداً: لا pool قاعدة خاصّ بها، وNATS best-effort فقط.
    # لذلك readiness يصف حقيقة runtime: الخدمة جاهزة للحساب التقديري/الرستر pass-through،
    # مع وسم التبعيات الاختيارية بدلاً من جعلها شرطاً صلباً.
    return {
        "status": "ready",
        "service": "vegetation-analysis-service",
        "ready": True,
        "implemented_runtime": True,
        "runtime_mode": "vegetation-estimate-with-raster-pass-through",
        "dependencies": {
            "platform_api": "optional",
            "raster_service": "optional_fail_soft",
            "nats": "best_effort_publish",
        },
    }


@router.get("/metrics")
async def metrics():
    return Response(main.generate_latest(), media_type=main.CONTENT_TYPE_LATEST)
