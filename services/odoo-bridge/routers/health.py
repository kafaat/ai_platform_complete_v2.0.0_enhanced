"""routers/health.py — فحوص الصحّة والجاهزيّة (Health / Readiness)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات
مطابقة. التبعيّات المشتركة (الحالة/المساعِدات) تبقى في ``main`` وتُشار إليها
عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import os

import main
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/healthz")
@router.get("/health")
async def health():
    # Odoo يُفحَص فقط حين يكون المزوّد المختار odoo؛ غير ذلك odoo_connected=null
    # (غير مفعَّل) بدل false مضلّل — الأساسي erpnext لا يمرّ عبر Odoo.
    provider = os.getenv("ERP_PROVIDER", "erpnext").strip().lower()
    odoo_ok = None
    uid = None
    if provider == "odoo":
        odoo_ok = False
        try:
            odoo = main.get_odoo()
            uid = odoo.uid if odoo.uid is not None else await odoo.authenticate()
            odoo_ok = True
        except Exception as e:  # noqa: BLE001
            main.logger.debug("فحص صحّة Odoo فشل: %s", type(e).__name__)
    return {
        "status": "alive",
        "erp_provider": provider,
        "odoo_connected": odoo_ok,  # null حين المزوّد ليس odoo (غير مفعَّل)
        "odoo_uid": uid,
        "sync_interval_sec": main.SYNC_INTERVAL_SEC,
    }


@router.get("/readyz")
async def readyz():
    # جاهزيّة حقيقيّة: حين تُضبط DATABASE_URL يجب أن يكون pool القاعدة حيّاً
    # (مزامنة ERP/الجسر تعتمد عليه). نتحقّق بـSELECT 1؛ تعذُّره ⇒ 503 لا «جاهز» كاذب.
    # حين لا DATABASE_URL مضبوطة (وضع متدرّج معلَن: لا قاعدة محلّيّة) ⇒ جاهز بصدق.
    if main._pool is not None:
        try:
            async with main._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as e:
            main.logger.warning(f"readyz: قاعدة البيانات غير جاهزة — {e}")
            raise HTTPException(503, {"status": "not_ready", "reason": "db"}) from e
    return {"status": "ready", "version": "9.1.0"}
