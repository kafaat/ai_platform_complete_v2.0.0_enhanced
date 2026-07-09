"""routers/health.py — فحوص الحياة والجاهزيّة (health / readiness)
======================================================================
شريحة من تفكيك ``actuator_runtime.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات مطابقة.
``health`` تخدم ``/healthz`` و``/health`` معاً (مُزخرِفان كما في الأصل). الرموز المشتركة
تبقى في ``main`` وتُشار إليها عبر ``main.X``.
"""

from __future__ import annotations

import actuator_runtime as main
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/healthz")
@router.get("/health")
async def health():
    # نكشف الوضع الفعّال للمراقبة (الصدق): simulation يُعلَن صراحةً فلا يُظنّ تنفيذاً حقيقيّاً.
    # صدق أمنيّ: نُعلن أنّ MQTT مُهيّأ فقط — لا نكشف broker URL (تسريب بنية تحتيّة).
    return {
        "status": "alive",
        "service": "actuator",
        "mqtt_configured": bool(main.MQTT_BROKER_URL),
        "mode": main.ACTUATOR_MODE,
    }


@router.get("/readyz")
async def readyz():
    # جاهزيّة حقيقيّة: حين تُضبط DATABASE_URL يجب أن يكون pool القاعدة حيّاً
    # (تسجيل أوامر الأجهزة يعتمد عليه). نتحقّق بـSELECT 1؛ تعذُّره ⇒ 503 لا «جاهز» كاذب.
    # حين لا DATABASE_URL مضبوطة (وضع متدرّج معلَن: تسجيل الأوامر معطّل) ⇒ جاهز بصدق.
    if main._pool is not None:
        try:
            async with main._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as e:
            main.logger.warning(f"readyz: قاعدة البيانات غير جاهزة — {e}")
            raise HTTPException(503, {"status": "not_ready", "reason": "db"}) from e
    return {"status": "ready", "version": "9.1.0"}
