"""routers/health.py — صحّة/جاهزيّة/مقاييس (Health · Readiness · Metrics)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات
مطابقة. التبعيّات المشتركة (الحالة/المساعِدات) تبقى في ``main`` وتُشار إليها
عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import main
from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/healthz")
@router.get("/health")
async def health() -> dict:
    return {"status": "alive", "service": "tts-service", "version": main.VERSION}


@router.get("/readyz")
async def readyz() -> dict:
    redis_ok = False
    if main._redis:
        try:
            await main._redis.ping()
            redis_ok = True
        except Exception as e:  # noqa: BLE001
            main.logger.debug("فحص صحّة Redis فشل: %s", type(e).__name__)
    return {
        "status": "ready",
        "redis": redis_ok,
        "voices_available": len(main.VOICES),
    }


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
