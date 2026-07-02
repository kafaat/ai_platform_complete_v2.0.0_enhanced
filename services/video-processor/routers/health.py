"""routers/health.py — فحوص الحياة والجاهزيّة (Health / Readiness)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات
مطابقة. التبعيّات المشتركة (الحالة) تبقى في ``main`` وتُشار إليها عبر ``main.X``.
``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/healthz")
@router.get("/health")
async def health():
    return {
        "status": "alive",
        "active_streams": sum(1 for s in main.STREAMS.values() if s.status == "active"),
        "max_streams": main.MAX_CONCURRENT_STREAMS,
    }


@router.get("/readyz")
async def readyz():
    dependencies = await main.check_video_dependencies()
    degraded = {k: v for k, v in dependencies.items() if not v.get("ok")}
    payload = {
        "status": "ready" if not degraded else "degraded",
        "version": "9.1.0",
        "dependencies": dependencies,
    }
    if degraded and main.VIDEO_STRICT_READY:
        raise HTTPException(status_code=503, detail=payload)
    return payload
