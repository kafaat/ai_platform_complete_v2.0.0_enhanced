"""routers/sync.py — تشغيل المزامنة اليدويّة (Manual Sync)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقل المُعالِج حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسار/المخرجات
مطابقة. التبعيّات المشتركة (الحالة/المساعِدات) تبقى في ``main`` وتُشار إليها
عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

router = APIRouter()


@router.post("/sync")
async def trigger_sync(
    req: main.SyncRequest,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(main.require_auth),
):
    """Trigger manual sync — يتطلّب توكناً صالحاً (كان مكشوفاً).

    الأمان: المزامنة تكتب لـERP — تتطلّب مصادقة (نفس require_auth المطبَّقة
    على نقاط القراءة).
    """
    if req.entity == "all" or req.entity == "products":
        background_tasks.add_task(main.sync_products)
    if req.entity == "all" or req.entity == "suppliers":
        background_tasks.add_task(main.sync_suppliers)
    if req.entity == "all" or req.entity == "warehouses":
        background_tasks.add_task(main.sync_warehouses)
    if req.entity == "all" or req.entity == "procurement":
        if main.get_active_erp_provider().name == "odoo":
            background_tasks.add_task(main.sync_procurement_orders_to_odoo)
        elif req.entity == "procurement":
            raise HTTPException(409, "procurement_sync_requires_odoo_provider")
    if req.entity == "all" or req.entity == "costs":
        background_tasks.add_task(main.sync_field_costs_to_odoo)
    return {"status": "queued", "entity": req.entity, "direction": req.direction}
