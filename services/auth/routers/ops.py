"""routers/ops.py — المراقبة والصحّة (Observability/Health).

مسارات: GET /metrics · GET /health · GET /healthz · GET /readyz

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة تبقى في ``main`` ويُشار
إليها عبر ``main.X``.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

router = APIRouter()


@router.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/healthz")
@router.get("/health")
async def health():
    return {"status": "alive", "service": "auth", "version": "9.1.0"}


@router.get("/readyz")
async def readyz():
    try:
        async with main._acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ready", "redis": main._redis is not None}
    except Exception as e:
        # لا نُسرّب تفاصيل الاتصال/المضيف/المستخدم من استثناء asyncpg في readyz العام.
        raise HTTPException(503, "DB not ready") from e
