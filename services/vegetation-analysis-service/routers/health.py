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
    # في real-only الإنتاجيّ تصبح جاهزيّة raster-service شرطاً صلباً (السلطة الوحيدة
    # للمشاهدات)؛ خارج الإنتاج تبقى اختياريّة كما كانت — بلا تبعيّة صلبة.
    real_only = bool(main.VEGETATION_REAL_ONLY)
    raster_ok = False
    raster_detail = "optional"
    if real_only:
        try:
            async with main.httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{main.RASTER_SERVICE_URL}/readyz")
            raster_ok = response.status_code == 200 and bool(response.json().get("ready", True))
            raster_detail = "ready" if raster_ok else f"http_{response.status_code}"
        except Exception as exc:  # noqa: BLE001 - الجاهزيّة تصف الواقع، لا ترمي
            raster_detail = f"unavailable:{type(exc).__name__}"
    else:
        raster_ok = True
    ready = raster_ok
    return {
        "status": "ready" if ready else "not_ready",
        "service": "vegetation-analysis-service",
        "ready": ready,
        "implemented_runtime": True,
        "runtime_mode": "authoritative-raster-only" if real_only else "development-compatible",
        "dependencies": {
            "platform_api": "optional",
            "raster_service": raster_detail,
            "nats": "best_effort_publish",
        },
    }


@router.get("/metrics")
async def metrics():
    return Response(main.generate_latest(), media_type=main.CONTENT_TYPE_LATEST)
