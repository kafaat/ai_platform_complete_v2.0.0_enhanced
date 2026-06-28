"""routers/webhooks.py — استقبال أحداث Odoo اللحظيّة (Webhooks)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقل المُعالِج حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسار/المخرجات
مطابقة. التبعيّات المشتركة (الحالة/المساعِدات) تبقى في ``main`` وتُشار إليها
عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import asyncio

import main
from fastapi import APIRouter, Header, HTTPException

router = APIRouter()


@router.post("/webhook/odoo")
async def odoo_webhook(payload: main.WebhookPayload, x_webhook_secret: str = Header(None)):
    """Receive real-time push from Odoo — يتطلّب سرّ webhook (كان مكشوفاً)."""
    # الأمان: webhook مالي/ERP — تحقّق من السرّ المشترك (منع حقن خارجي)
    if not main.WEBHOOK_SECRET:
        raise HTTPException(503, "WEBHOOK_SECRET غير مضبوط — webhook معطّل بأمان")
    # مقارنة ثابتة الزمن (منع هجوم التوقيت على السرّ)
    import hmac

    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, main.WEBHOOK_SECRET):
        raise HTTPException(401, "سرّ webhook غير صالح")
    main.logger.info(f"Odoo webhook: {payload.model}:{payload.record_id} event={payload.event}")

    # Route to appropriate handler
    if payload.model == "product.product":
        asyncio.create_task(main.sync_products())
    elif payload.model == "res.partner":
        asyncio.create_task(main.sync_suppliers())
    elif payload.model == "purchase.order":
        # Odoo PO updated → اسحب الحالة وحدّث procurement_orders + سجلّ مزامنة وارد.
        # record_id = معرّف purchase.order في Odoo (راجع docs/ODOO_INTEGRATION.md).
        asyncio.create_task(main.sync_purchase_order_inbound(payload.record_id))

    return {"received": True, "model": payload.model}
