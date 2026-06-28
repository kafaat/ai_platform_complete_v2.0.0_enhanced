"""routers/health.py — فحوص الصحّة والجاهزيّة والمقاييس (Health/Readiness/Metrics)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات
مطابقة. التبعيّات المشتركة (الحالة/المساعِدات) تبقى في ``main`` وتُشار إليها
عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/healthz")
@router.get("/health")
async def health():
    return {"status": "alive", "service": "soil-service", "version": main.VERSION}


@router.get("/readyz")
async def readyz():
    try:
        if main._pool:
            async with main._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        return {"status": "ready"}
    except Exception as e:
        # لا نُرجِع str(e) (يسرّب DSN/تفاصيل اتّصال) — رسالة عامّة + تسجيل داخليّ
        main.logger.warning("readyz فشل: %s", e)
        raise HTTPException(503, "not ready") from e


@router.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
