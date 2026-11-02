"""routers/webhooks.py — استقبال أحداث Odoo اللحظيّة (Webhooks)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقل المُعالِج حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسار/المخرجات
مطابقة. التبعيّات المشتركة (الحالة/المساعِدات) تبقى في ``main`` وتُشار إليها
عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import asyncio
import functools

import main
from fastapi import APIRouter, Header, HTTPException

router = APIRouter()
_WEBHOOK_TASKS: set[asyncio.Task] = set()


@router.post("/v1/webhook/odoo")
async def odoo_webhook(payload: main.WebhookPayload, x_webhook_secret: str = Header(None)):
    """Receive real-time push from Odoo — يتطلّب سرّ webhook (كان مكشوفاً)."""
    # الأمان: webhook مالي/ERP — تحقّق من السرّ المشترك (منع حقن خارجي)
    if not main.WEBHOOK_SECRET:
        raise HTTPException(503, "WEBHOOK_SECRET غير مضبوط — webhook معطّل بأمان")
    # مقارنة ثابتة الزمن (منع هجوم التوقيت على السرّ)
    import hmac

    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, main.WEBHOOK_SECRET):
        raise HTTPException(401, "سرّ webhook غير صالح")
    if main.get_active_erp_provider().name != "odoo":
        raise HTTPException(409, "odoo_webhook_requires_odoo_provider")
    main.logger.info(f"Odoo webhook: {payload.model}:{payload.record_id} event={payload.event}")

    # Route to appropriate handler — عبر run_sync_job (R4): فشل المهمّة/غياب المخطّط يُسجَّل
    # ERROR بـrun_id وفي odoo_sync_log بدل «Task exception was never retrieved» صامت.
    step = None
    if payload.model == "product.product":
        step = ("products", main.sync_products)
    elif payload.model == "res.partner":
        step = ("suppliers", main.sync_suppliers)
    elif payload.model == "purchase.order":
        # Odoo PO updated → اسحب الحالة وحدّث procurement_orders + سجلّ مزامنة وارد.
        # record_id = معرّف purchase.order في Odoo (راجع docs/ODOO_INTEGRATION.md).
        step = (
            "procurement_inbound",
            functools.partial(main.sync_purchase_order_inbound, payload.record_id),
        )
    if step is None:
        return {"received": True, "model": payload.model}
    run_id = main.new_sync_run_id()
    task = asyncio.create_task(main.run_sync_job(run_id, [step], trigger="webhook"))
    _WEBHOOK_TASKS.add(task)  # مرجع قويّ يمنع جمع المهمّة قبل انتهائها
    task.add_done_callback(_WEBHOOK_TASKS.discard)
    return {"received": True, "model": payload.model, "run_id": run_id}
