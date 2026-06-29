"""routers/health.py — فحوص الحياة والجاهزيّة (Health / Readiness)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات
مطابقة. التبعيّات المشتركة (الحالة) تبقى في ``main`` وتُشار إليها عبر ``main.X``.
``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import main
from fastapi import APIRouter

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
    # بلا تبعيّة صلبة قصداً: لا pool قاعدة ولا عميل Redis متّصل (REDIS_URL غير
    # مُستهلَك هنا). النشر عبر MQTT والنداءات الخلفيّة (edge/zlmedia) محاولة-أفضل
    # لا تُعطِّل الإقلاع. لا شيء صلب ننتظره ⇒ جاهز بصدق.
    return {"status": "ready", "version": "9.1.0"}
