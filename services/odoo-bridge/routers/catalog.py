"""routers/catalog.py — كتالوج ERP والإعداد والسجلّات (Catalog / Config / Logs)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت مُعالِجات
cert المصلّبة (تجريد مزوّد ERP) حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المساعِدات
المشتركة (مزوّد ERP/المسبح) تبقى في ``main`` وتُشار إليها عبر ``main.X``.
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
    selected = main._selected_erp_provider()
    try:
        provider = main.get_active_erp_provider()
        hp = await provider.health()
    except Exception as e:  # noqa: BLE001 — لا نُسرّب تفاصيل اتصال ERP/URL/اعتمادات
        main.logger.debug("ERP provider health failed: %s", type(e).__name__)
        return {"selected": selected, "status": "error", "error": "provider_unavailable"}
    return {"selected": selected, "active_provider": provider.name, "health": hp}


@router.get("/config")
async def get_config(_auth: dict = Depends(main.require_auth)):
    provider = main.get_active_erp_provider()
    connected = False
    try:
        connected = await provider.authenticate()
    except Exception as e:  # noqa: BLE001
        main.logger.debug("ERP config check failed: %s", type(e).__name__)
    # Generic and non-secret. Historic Odoo URL/UID are deliberately not exposed.
    return {
        "provider": main._selected_erp_provider(),
        "active_provider": provider.name,
        "enabled": provider.name != "none",
        "connected": connected,
    }


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


@router.get("/v1/products")
async def list_erp_products(limit: int = 20, _auth: dict = Depends(main.require_auth)):
    provider = main.get_active_erp_provider()
    products = await provider.list_products()
    return {"provider": provider.name, "products": products[:limit]}


@router.get("/suppliers")
async def list_erp_suppliers(limit: int = 20, _auth: dict = Depends(main.require_auth)):
    provider = main.get_active_erp_provider()
    suppliers = await provider.list_suppliers()
    return {"provider": provider.name, "suppliers": suppliers[:limit]}
