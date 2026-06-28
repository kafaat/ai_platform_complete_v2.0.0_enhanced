"""routers/health.py — نقاط التشغيل (Liveness / Readiness / Metrics)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/الطرائق/المخرجات
مطابقة تماماً (بما فيها ازدواج ``/healthz`` + ``/health`` على نفس المُعالِج). التبعيّات
المشتركة تبقى في ``main`` وتُشار إليها عبر ``main.X``. ``register_routers(app)`` يضمّ
هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/healthz")
@router.get("/health")
async def healthz():
    return {"status": "alive", "service": "guardrails-engine", "tiers": 3}


@router.get("/readyz")
async def readyz():
    # جاهزيّة حقيقيّة: guardrails يُديم قرارات الموافقة البشريّة (HIL) في القاعدة
    # — إنشاء/اعتماد/رفض workflow و/validate حين يولّد workflow كلّها تكتب فيها
    # عبر تجمّع human_in_loop. حين تُضبط DATABASE_URL نتحقّق بـSELECT 1؛ تعذُّره ⇒ 503
    # لا «جاهز» كاذب. حين لا DATABASE_URL (وضع متدرّج معلَن) ⇒ جاهز بصدق.
    if os.getenv("DATABASE_URL", ""):
        from human_in_loop import _get_pool

        try:
            pool = await _get_pool()
            if pool is not None:
                async with pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
        except Exception as e:
            raise HTTPException(503, {"status": "not_ready", "reason": "db"}) from e
    return {"status": "ready"}


@router.get("/metrics")
async def metrics_endpoint():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from starlette.responses import Response

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
