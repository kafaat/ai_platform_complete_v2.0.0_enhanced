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

    fail-closed (ERP-BRIDGE-FIX-01): إذا كان مزوّد ERP غير مهيّأ (none) يُرفَض
    الطلب بـHTTP 424 Failed Dependency — لا إرسال وهميّ إلى ERP، لا كتابة جزئية.
    الحالة "ERP معطّل" معروضة كبيانات في /readyz/capabilities؛ الرفض يحدث هنا
    عند محاولة المزامنة الفعلية لا عند إقلاع الحاوية.
    """
    provider = main.get_active_erp_provider()
    if provider.name == "none":
        raise HTTPException(
            424,
            {
                "error": "erp_provider_not_configured",
                "provider": provider.name,
                "detail": (
                    "ERP provider is not configured or credentials are missing. "
                    "Set ERP_PROVIDER and the corresponding credentials "
                    "(ERPNEXT_API_KEY/ERPNEXT_API_SECRET or ODOO_*). "
                    "Check /readyz/capabilities for current capability status."
                ),
            },
        )
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
