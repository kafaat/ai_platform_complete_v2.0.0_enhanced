"""routers/catalog.py — كتالوج Odoo والإعداد والسجلّات (Catalog / Config / Logs)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات
مطابقة. التبعيّات المشتركة (الحالة/المساعِدات) تبقى في ``main`` وتُشار إليها
عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, Depends

router = APIRouter()


@router.get("/erp/provider")
async def erp_provider_status(_auth: dict = Depends(main.require_auth)):
    """يكشف مزوّد ERP النشط (مفتاح التبديل) وحالته.

    ERP_PROVIDER = odoo | erpnext | none — يحدّد المزوّد دون تغيير الكود.
    """
    import os

    from erp_provider import get_erp_provider

    selected = os.getenv("ERP_PROVIDER", "erpnext").strip().lower()
    # نمرّر OdooClient للمزوّد odoo (يعيد استخدام الموجود)
    try:
        provider = get_erp_provider(odoo_client=main.get_odoo() if selected == "odoo" else None)
        hp = await provider.health()
    except Exception as e:  # noqa: BLE001 — صدق: نُعلن الخطأ لا نخفيه
        return {"selected": selected, "status": "error", "error": str(e)}
    return {"selected": selected, "active_provider": provider.name, "health": hp}


@router.get("/config", response_model=main.OdooConfigResponse)
async def get_config(_auth: dict = Depends(main.require_auth)):
    odoo = main.get_odoo()
    connected = False
    uid = odoo.uid
    version = None
    try:
        if uid is None:
            uid = await odoo.authenticate()
        version_info = await odoo.call("common", "version")
        version = version_info.get("server_version")
        connected = True
    except Exception as e:
        main.logger.warning(f"Config check failed: {e}")
    return main.OdooConfigResponse(
        url=main.ODOO_URL,
        db=main.ODOO_DB,
        user=main.ODOO_USER,
        connected=connected,
        uid=uid,
        version=version,
    )


@router.get("/logs")
async def get_logs(
    limit: int = 50, entity: str | None = None, _auth: dict = Depends(main.require_auth)
):
    pool = await main.get_pool()
    if not pool:
        return {"logs": []}
    async with pool.acquire() as conn:
        if entity:
            rows = await conn.fetch(
                "SELECT * FROM odoo_sync_log WHERE entity=$1 ORDER BY created_at DESC LIMIT $2",
                entity,
                limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM odoo_sync_log ORDER BY created_at DESC LIMIT $1", limit
            )
    return {"logs": [dict(r) for r in rows]}


@router.get("/products")
async def list_odoo_products(limit: int = 20, _auth: dict = Depends(main.require_auth)):
    odoo = main.get_odoo()
    products = await odoo.search_read(
        "product.product",
        [],
        ["id", "name", "default_code", "list_price", "standard_price", "qty_available"],
        limit=limit,
    )
    return {"products": products}


@router.get("/suppliers")
async def list_odoo_suppliers(limit: int = 20, _auth: dict = Depends(main.require_auth)):
    odoo = main.get_odoo()
    suppliers = await odoo.search_read(
        "res.partner",
        [["supplier_rank", ">", 0]],
        ["id", "name", "phone", "email", "supplier_rank"],
        limit=limit,
    )
    return {"suppliers": suppliers}
