"""Runtime implementation for ERP/Odoo bridge sync and provider state.

Extracted from ``main.py`` as a behavior-preserving P1 decomposition step.
Routes still import these names through ``main`` re-exports, while the mutable
ERP/Odoo/DB state now lives here instead of bloating the FastAPI entrypoint.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import httpx

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("erp-bridge")
except ImportError:
    logging.basicConfig(
        level=logging.INFO, format='{"time":"%(asctime)s","svc":"erp-bridge","msg":"%(message)s"}'
    )
    logger = logging.getLogger("erp-bridge")

# ── Config ────────────────────────────────────────────────────
ODOO_URL = os.getenv("ODOO_URL", "http://sahool-odoo:8069")
ODOO_DB = os.getenv("ODOO_DB", "sahool_erp")
ODOO_USER = os.getenv("ODOO_USER", "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")  # CRIT-ODOO-01: no default — must be set in env
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")  # preferred over password

SAHOOL_DB_URL = os.getenv("DATABASE_URL", "")
SAHOOL_API_URL = os.getenv("SAHOOL_API_URL", "http://sahool-auth:8000")
SAHOOL_AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")

SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", "300"))  # 5 min
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# ── صدق عزل المستأجر للكتالوج الوارد من Odoo ─────────────────────
# كتالوج Odoo (product.product / res.partner المورّدون) عالميّ على مستوى المنصّة
# بطبيعته، لا مملوكاً لمستأجر واحد: المفتاح الفريد لمزامنته في المنصّة هو معرّف
# Odoo نفسه عالميّاً — `ON CONFLICT (odoo_product_id)` و`ON CONFLICT (odoo_partner_id)`
# (راجع الفهارس الفريدة بلا tenant_id في migrations/v9_odoo_bridge.sql على
# market_products/market_suppliers: صفّ واحد لكلّ سجلّ Odoo عبر كلّ المنصّة).
# لذا لا نفرض tenant_id على صفوف الكتالوج المُزامَنة — فرضه يناقض المفتاح الفريد
# العالميّ ويُلفّق ملكيّةً لا وجود لها (الفهرس الفريد لـinventory_stock يُرحّب صراحةً
# بـtenant_id=NULL: COALESCE(tenant_id::text,'default')).
#
# لكن إن قرّر مشغّل أنّ نشره أحاديّ المستأجر وأراد إسناد الكتالوج لمستأجر صريح،
# نقرأ ODOO_SYNC_TENANT_ID من البيئة (UUID صريح، لا تلفيق). فارغ ⇒ كتالوج عالميّ.
ODOO_SYNC_TENANT_ID = os.getenv("ODOO_SYNC_TENANT_ID", "").strip() or None

_pool: asyncpg.Pool | None = None
_odoo_uid: int | None = None
_odoo_auth_cache: dict = {}


def _selected_erp_provider() -> str:
    """Return normalized ERP_PROVIDER. Unknown values fail-safe to none at provider factory."""
    return os.getenv("ERP_PROVIDER", "erpnext").strip().lower()


def get_active_erp_provider():
    """Build the selected ERP provider without constructing Odoo unless explicitly selected.

    ADR-0001: erp-bridge must work with ERPNext, Odoo, or no ERP at all; Odoo is optional.
    """
    try:
        from erp_provider import get_erp_provider
    except ModuleNotFoundError:
        # Unit tests and importlib-based loaders may execute this file without
        # services/odoo-bridge on sys.path. Load the sibling provider explicitly
        # instead of requiring process-global path mutation.
        bridge_dir = str(Path(__file__).resolve().parent)
        if bridge_dir not in sys.path:
            sys.path.insert(0, bridge_dir)
        from erp_provider import get_erp_provider

    selected = _selected_erp_provider()
    return get_erp_provider(odoo_client=get_odoo() if selected == "odoo" else None)


# ══════════════════════════════════════════════════════════════
# Odoo JSON-RPC Client
# ══════════════════════════════════════════════════════════════
class OdooClient:
    def __init__(self, url: str, db: str, username: str, password: str, api_key: str = ""):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.api_key = api_key
        self.uid: int | None = None
        self._session = httpx.AsyncClient(timeout=30.0)

    async def authenticate(self) -> int:
        """Authenticate and return user ID."""
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "common",
                "method": "authenticate",
                "args": [self.db, self.username, self.api_key or self.password, {}],
            },
            "id": 1,
        }
        r = await self._session.post(f"{self.url}/jsonrpc", json=payload)
        r.raise_for_status()
        result = r.json()
        if "error" in result:
            raise RuntimeError(f"Odoo auth failed: {result['error']}")
        self.uid = result["result"]
        logger.info(f"Odoo authenticated: uid={self.uid}")
        return self.uid

    async def call(self, model: str, method: str, args: list = None, kwargs: dict = None) -> Any:
        """Call Odoo object method via JSON-RPC."""
        if self.uid is None:
            await self.authenticate()
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    self.db,
                    self.uid,
                    self.api_key or self.password,
                    model,
                    method,
                    args or [],
                    kwargs or {},
                ],
            },
            "id": hashlib.md5(
                f"{model}:{method}:{datetime.now()}".encode(), usedforsecurity=False
            ).hexdigest()[:8],
        }
        r = await self._session.post(f"{self.url}/jsonrpc", json=payload)
        r.raise_for_status()
        result = r.json()
        if "error" in result:
            raise RuntimeError(f"Odoo RPC error: {result['error']}")
        return result["result"]

    async def search_read(
        self, model: str, domain: list, fields: list, limit: int = 0, order: str = ""
    ) -> list[dict]:
        kwargs = {"fields": fields}
        if limit:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return await self.call(model, "search_read", [domain], kwargs)

    async def create(self, model: str, values: dict) -> int:
        return await self.call(model, "create", [values])

    async def write(self, model: str, ids: list[int], values: dict) -> bool:
        return await self.call(model, "write", [ids, values])

    async def unlink(self, model: str, ids: list[int]) -> bool:
        return await self.call(model, "unlink", [ids])

    async def close(self):
        await self._session.aclose()


# Global client
_odoo: OdooClient | None = None


def get_odoo() -> OdooClient:
    global _odoo
    if _odoo is None:
        _odoo = OdooClient(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD, ODOO_API_KEY)
    return _odoo


# ══════════════════════════════════════════════════════════════
# Sync State Manager (DB)
# ══════════════════════════════════════════════════════════════
async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None and SAHOOL_DB_URL:
        _pool = await asyncpg.create_pool(SAHOOL_DB_URL, min_size=1, max_size=5)
    return _pool


async def _run_migrations():
    """يضمن وجود الجداول المطلوبة قبل أيّ مزامنة (تشغيل مستقلّ بلا مانيفست خارجيّ)."""
    pool = await get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS odoo_sync_state (
                entity       TEXT        NOT NULL,
                direction    TEXT        NOT NULL,
                last_sync_at TIMESTAMPTZ,
                PRIMARY KEY (entity, direction)
            )"""
        )
    logger.info("DB migrations applied")


async def get_last_sync(entity: str, direction: str) -> datetime | None:
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT last_sync_at FROM odoo_sync_state WHERE entity=$1 AND direction=$2",
            entity,
            direction,
        )
        return row["last_sync_at"] if row else None


async def set_last_sync(entity: str, direction: str, sync_at: datetime):
    pool = await get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO odoo_sync_state (entity, direction, last_sync_at)
                VALUES ($1,$2,$3)
                ON CONFLICT (entity, direction) DO UPDATE SET last_sync_at=$3""",
            entity,
            direction,
            sync_at,
        )


async def log_sync_record(
    direction: str,
    entity: str,
    odoo_id: int | None,
    sahool_id: str | None,
    status: str,
    details: str = "",
):
    pool = await get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO odoo_sync_log
                (direction, entity, odoo_id, sahool_id, status, details)
                VALUES ($1,$2,$3,$4,$5,$6)""",
            direction,
            entity,
            odoo_id,
            sahool_id,
            status,
            details,
        )


# ══════════════════════════════════════════════════════════════
# Odoo → SAHOOL Sync (Master Data)
# ══════════════════════════════════════════════════════════════
async def sync_products():
    """Sync selected ERP products → SAHOOL inventory items.

    ADR-0001: provider-neutral. Uses ERPProvider.list_products(); Odoo is just one optional
    implementation. Existing DB column names keep the historic `odoo_*` names, but values are
    namespaced by provider for non-Odoo providers to avoid collisions.
    """
    provider = get_active_erp_provider()
    if provider.name == "none":
        await log_sync_record(
            "erp_to_sahool", "products", None, None, "skipped", "ERP provider disabled"
        )
        logger.info("ERP disabled → products sync skipped")
        return

    last_sync = await get_last_sync(f"{provider.name}.products", "erp_to_sahool")
    since = last_sync.isoformat() if last_sync else None
    products = await provider.list_products(since=since)

    pool = await get_pool()
    if not pool:
        return

    synced = 0
    async with pool.acquire() as conn:
        for item in products:
            external_id = item.get("external_id") or item.get("code") or item.get("name")
            if external_id is None:
                logger.warning("ERP product skipped: missing external id")
                continue
            product_key = (
                str(external_id) if provider.name == "odoo" else f"{provider.name}:{external_id}"
            )
            name = item.get("name") or item.get("code") or product_key
            category = item.get("category") or "General"
            uom = item.get("uom") or "Unit"
            cost = float(item.get("cost") or 0)
            supplier = item.get("supplier") or f"{provider.name} Sync"

            if ODOO_SYNC_TENANT_ID:
                await conn.execute(
                    """INSERT INTO inventory_stock (item_name, category, unit, unit_cost_usd,
                            quantity_in_stock, reorder_level, supplier, odoo_product_id,
                            tenant_id, last_synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                        ON CONFLICT (odoo_product_id) DO UPDATE SET
                            item_name=$1, category=$2, unit=$3, unit_cost_usd=$4,
                            supplier=$7, tenant_id=$9, last_synced_at=NOW()""",
                    name,
                    category,
                    uom,
                    cost,
                    0,
                    10,
                    supplier,
                    product_key,
                    ODOO_SYNC_TENANT_ID,
                )
            else:
                await conn.execute(
                    """INSERT INTO inventory_stock (item_name, category, unit, unit_cost_usd,
                            quantity_in_stock, reorder_level, supplier, odoo_product_id, last_synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW())
                        ON CONFLICT (odoo_product_id) DO UPDATE SET
                            item_name=$1, category=$2, unit=$3, unit_cost_usd=$4,
                            supplier=$7, last_synced_at=NOW()""",
                    name,
                    category,
                    uom,
                    cost,
                    0,
                    10,
                    supplier,
                    product_key,
                )
            synced += 1

    now = datetime.now(UTC)
    await set_last_sync(f"{provider.name}.products", "erp_to_sahool", now)
    # Backward-compatible marker for existing dashboards when provider is Odoo.
    if provider.name == "odoo":
        await set_last_sync("product.product", "odoo_to_sahool", now)
    await log_sync_record(
        "erp_to_sahool",
        "products",
        None,
        None,
        "success",
        f"Synced {synced} products from {provider.name}",
    )
    logger.info("Products synced from %s: %s", provider.name, synced)


async def sync_suppliers():
    """Sync selected ERP suppliers → SAHOOL suppliers."""
    provider = get_active_erp_provider()
    if provider.name == "none":
        await log_sync_record(
            "erp_to_sahool", "suppliers", None, None, "skipped", "ERP provider disabled"
        )
        logger.info("ERP disabled → suppliers sync skipped")
        return

    last_sync = await get_last_sync(f"{provider.name}.suppliers", "erp_to_sahool")
    since = last_sync.isoformat() if last_sync else None
    suppliers = await provider.list_suppliers(since=since)

    pool = await get_pool()
    if not pool:
        return

    synced = 0
    async with pool.acquire() as conn:
        for item in suppliers:
            external_id = item.get("external_id") or item.get("code") or item.get("name")
            if external_id is None:
                logger.warning("ERP supplier skipped: missing external id")
                continue
            supplier_key = (
                str(external_id) if provider.name == "odoo" else f"{provider.name}:{external_id}"
            )
            name = item.get("name") or supplier_key
            phone = item.get("phone") or ""
            email = item.get("email") or ""
            address = item.get("address") or ""

            if ODOO_SYNC_TENANT_ID:
                await conn.execute(
                    """INSERT INTO suppliers (name, contact_person, phone, email, address,
                            rating, categories, active, odoo_partner_id, tenant_id, last_synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW())
                        ON CONFLICT (odoo_partner_id) DO UPDATE SET
                            name=$1, phone=$3, email=$4, address=$5,
                            tenant_id=$10, last_synced_at=NOW()""",
                    name,
                    name,
                    phone,
                    email,
                    address,
                    4.0,
                    ["general"],
                    True,
                    supplier_key,
                    ODOO_SYNC_TENANT_ID,
                )
            else:
                await conn.execute(
                    """INSERT INTO suppliers (name, contact_person, phone, email, address,
                            rating, categories, active, odoo_partner_id, last_synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                        ON CONFLICT (odoo_partner_id) DO UPDATE SET
                            name=$1, phone=$3, email=$4, address=$5, last_synced_at=NOW()""",
                    name,
                    name,
                    phone,
                    email,
                    address,
                    4.0,
                    ["general"],
                    True,
                    supplier_key,
                )
            synced += 1

    now = datetime.now(UTC)
    await set_last_sync(f"{provider.name}.suppliers", "erp_to_sahool", now)
    if provider.name == "odoo":
        await set_last_sync("res.partner", "odoo_to_sahool", now)
    await log_sync_record(
        "erp_to_sahool",
        "suppliers",
        None,
        None,
        "success",
        f"Synced {synced} suppliers from {provider.name}",
    )
    logger.info("Suppliers synced from %s: %s", provider.name, synced)


async def sync_warehouses():
    """Sync selected ERP warehouses/locations → SAHOOL inventory locations."""
    provider = get_active_erp_provider()
    if provider.name == "none":
        await log_sync_record(
            "erp_to_sahool", "warehouses", None, None, "skipped", "ERP provider disabled"
        )
        logger.info("ERP disabled → warehouses sync skipped")
        return

    whs = await provider.list_warehouses()
    pool = await get_pool()
    if not pool:
        return
    synced = 0
    async with pool.acquire() as conn:
        for w in whs:
            external_id = w.get("external_id") or w.get("code") or w.get("name")
            if external_id is None:
                logger.warning("ERP warehouse skipped: missing external id")
                continue
            warehouse_key = (
                str(external_id) if provider.name == "odoo" else f"{provider.name}:{external_id}"
            )
            await conn.execute(
                """INSERT INTO inventory_locations (location_name, location_code, odoo_warehouse_id)
                    VALUES ($1,$2,$3)
                    ON CONFLICT (odoo_warehouse_id) DO UPDATE SET location_name=$1, location_code=$2""",
                w.get("name") or warehouse_key,
                w.get("code") or warehouse_key,
                warehouse_key,
            )
            synced += 1
    await log_sync_record(
        "erp_to_sahool",
        "warehouses",
        None,
        None,
        "success",
        f"Synced {synced} warehouses from {provider.name}",
    )
    logger.info("Warehouses synced from %s: %s", provider.name, synced)


# ══════════════════════════════════════════════════════════════
# SAHOOL → Odoo Sync (Transactions)
# ══════════════════════════════════════════════════════════════
async def sync_procurement_orders_to_odoo():
    """Push SAHOOL procurement_orders → Odoo purchase.orders."""
    pool = await get_pool()
    if not pool:
        return
    odoo = get_odoo()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT order_id, tenant_id, status, notes, created_at
               FROM procurement_orders
               WHERE odoo_sync_status IN ('pending','failed')
               ORDER BY created_at LIMIT 50"""
        )

        for row in rows:
            try:
                # 1. Find or create partner in Odoo
                # 2. Create purchase.order
                # 3. Create purchase.order.line for each item
                items = await conn.fetch(
                    "SELECT * FROM procurement_order_items WHERE order_id=$1", row["order_id"]
                )
                if not items:
                    continue

                # صدق: لا تُلفّق تطابق مورّد/منتج. حُلّ كلّ ربط من Odoo فعليّاً؛
                # إن تعذّر ربط حقيقيّ، لا تدفع أمر شراء مُزيَّفاً مربوطاً بشريك/منتج
                # عشوائيّ (partner_id=1 / prod_id=1 السابقان كانا يخترعان تطابقاً
                # خاطئاً-لكن-معقولاً صامتاً). نفشل صريحاً ونعلّم الأمر failed ونتابع.
                #
                # ١) حُلّ المورّد (partner) من Odoo. لا مصدر مورّد على مستوى الأمر
                #    هنا، لكن لكي لا نُلفّق partner عشوائيّاً نُلزم وجود مفتاح صريح:
                #    procurement_orders.supplier_id (إن وُجد) أو procurement_order_items
                #    عبر اسم المورّد. غياب أيّ ربط ⇒ فشل صريح لا partner_id=1.
                supplier_name = items[0].get("supplier") if items else None
                supplier_id = None
                if supplier_name:
                    partner_rows = await odoo.search_read(
                        "res.partner",
                        [["name", "ilike", supplier_name], ["supplier_rank", ">", 0]],
                        ["id"],
                        limit=1,
                    )
                    supplier_id = partner_rows[0]["id"] if partner_rows else None

                if not supplier_id:
                    reason = (
                        "لا مورّد قابل للحلّ في Odoo "
                        f"(supplier={supplier_name!r}) — لن يُدفع أمر شراء مُلفَّق"
                    )
                    await conn.execute(
                        "UPDATE procurement_orders SET odoo_sync_status='failed', "
                        "odoo_sync_error=$1 WHERE order_id=$2",
                        reason[:500],
                        row["order_id"],
                    )
                    await log_sync_record(
                        "sahool_to_odoo",
                        "purchase.order",
                        None,
                        str(row["order_id"]),
                        "failed",
                        reason[:500],
                    )
                    logger.error(f"PO {row['order_id']} غير مدفوع: {reason}")
                    continue

                # ٢) حُلّ كلّ منتج فعليّاً قبل أيّ كتابة في Odoo. أيّ منتج غير قابل
                #    للحلّ ⇒ فشل صريح للأمر كلّه (لا prod_id=1 مُلفَّق).
                resolved_lines = []
                unresolved_item = None
                for it in items:
                    prod_domain = [["name", "ilike", it["item_name"]]]
                    prods = await odoo.search_read("product.product", prod_domain, ["id"], limit=1)
                    if not prods:
                        unresolved_item = it["item_name"]
                        break
                    resolved_lines.append((prods[0]["id"], it))

                if unresolved_item is not None:
                    reason = (
                        f"لا منتج قابل للحلّ في Odoo (item={unresolved_item!r}) — "
                        "لن يُدفع أمر شراء مُلفَّق"
                    )
                    await conn.execute(
                        "UPDATE procurement_orders SET odoo_sync_status='failed', "
                        "odoo_sync_error=$1 WHERE order_id=$2",
                        reason[:500],
                        row["order_id"],
                    )
                    await log_sync_record(
                        "sahool_to_odoo",
                        "purchase.order",
                        None,
                        str(row["order_id"]),
                        "failed",
                        reason[:500],
                    )
                    logger.error(f"PO {row['order_id']} غير مدفوع: {reason}")
                    continue

                # ٣) كلّ الروابط حقيقيّة — ادفع أمر الشراء وأسطره (السلوك دون تغيير
                #    عند توفّر ربط حقيقيّ).
                po_vals = {
                    "partner_id": supplier_id,  # مورّد محلول فعليّاً (لا default=1)
                    "origin": f"SAHOOL-{row['order_id']}",
                    "notes": row.get("notes", "") + "\nSynced from SAHOOL",
                    "date_order": row["created_at"].isoformat()
                    if row["created_at"]
                    else datetime.now(UTC).isoformat(),
                }
                po_id = await odoo.create("purchase.order", po_vals)

                for prod_id, it in resolved_lines:
                    line_vals = {
                        "order_id": po_id,
                        "product_id": prod_id,
                        "product_qty": float(it["quantity"]),
                        "price_unit": float(it.get("unit_cost_usd", 0) or 0),
                        "name": it["item_name"],
                    }
                    await odoo.create("purchase.order.line", line_vals)

                # Update SAHOOL
                await conn.execute(
                    "UPDATE procurement_orders SET odoo_sync_status='synced', odoo_document_id=$1 WHERE order_id=$2",
                    str(po_id),
                    row["order_id"],
                )
                await log_sync_record(
                    "sahool_to_odoo", "purchase.order", po_id, str(row["order_id"]), "success"
                )
                logger.info(f"PO synced to Odoo: {po_id}")

            except Exception as e:
                await conn.execute(
                    "UPDATE procurement_orders SET odoo_sync_status='failed', odoo_sync_error=$1 WHERE order_id=$2",
                    str(e)[:500],
                    row["order_id"],
                )
                await log_sync_record(
                    "sahool_to_odoo",
                    "purchase.order",
                    None,
                    str(row["order_id"]),
                    "failed",
                    str(e)[:500],
                )
                logger.error(f"PO sync failed {row['order_id']}: {e}")


# ══════════════════════════════════════════════════════════════
# Odoo → SAHOOL (Purchase Order status pull-back / inbound leg)
# ══════════════════════════════════════════════════════════════
# خريطة حالات purchase.order في Odoo → مفردات حالة procurement_orders في SAHOOL.
#
# صدق المصدر: جدول procurement_orders يُنشأ في خدمة أخرى (لا DDL له داخل هذا
# المستودع)، فلا CHECK enum قابل للاكتشاف هنا. المفردات المُعتمَدة مستخرَجة من
# الكتابات الفعلية في المنصّة:
#   - 'draft' / 'approved'        (docs/LIGHTWEIGHT_INTEGRATION.md, docs/UNIFIED_SETUP.md)
#   - 'draft' / 'pending_approval' / 'approved'  (services/mcp_servers/market_server.py)
# وامتدادات دورة الحياة الطبيعية ('ordered' / 'received' / 'cancelled') لتغطية
# حالات Odoo التي لا مقابل مباشر لها. إن فرضت الخدمة المالكة enum أضيق، تُضبط
# هذه القيم لاحقاً — لا نخترع حالة خارج هذه المفردات المرصودة.
ODOO_PO_STATE_TO_SAHOOL_STATUS = {
    "draft": "draft",  # RFQ مسوّدة
    "sent": "pending_approval",  # RFQ أُرسلت للمورّد
    "purchase": "ordered",  # أمر شراء مؤكَّد
    "done": "received",  # مقفَل/مستلَم
    "cancel": "cancelled",  # ملغى
}


async def sync_purchase_order_inbound(odoo_po_id: int):
    """Odoo purchase.order تغيّرت → اسحب حالتها وحدّث صفّ procurement_orders المرتبط.

    الاتجاه الوارد (odoo_to_sahool) المقابل للدفع الصادر في
    sync_procurement_orders_to_odoo. الربط عبر procurement_orders.odoo_document_id
    (الذي يُضبط = str(po_id) عند الدفع الصادر).
    """
    pool = await get_pool()
    if not pool:
        return
    odoo = get_odoo()

    # 1) اقرأ حالة الأمر من Odoo عبر search_read (طريقة القراءة الموجودة فعلاً
    #    على العميل — لا browse/read منفصل). نُقيّد بالـid لجلب صفّ واحد.
    try:
        po_rows = await odoo.search_read(
            "purchase.order",
            [["id", "=", odoo_po_id]],
            ["id", "name", "state"],
            limit=1,
        )
    except Exception as e:  # noqa: BLE001 — صدق: نُسجّل الفشل لا نُخفيه بـpass صامت
        await log_sync_record(
            "odoo_to_sahool", "purchase.order", odoo_po_id, None, "failed", str(e)[:500]
        )
        logger.error(f"Inbound PO read failed {odoo_po_id}: {e}")
        return

    if not po_rows:
        await log_sync_record(
            "odoo_to_sahool",
            "purchase.order",
            odoo_po_id,
            None,
            "failed",
            "purchase.order غير موجود في Odoo",
        )
        logger.warning(f"Inbound PO {odoo_po_id} not found in Odoo")
        return

    po = po_rows[0]
    odoo_state = po.get("state")
    sahool_status = ODOO_PO_STATE_TO_SAHOOL_STATUS.get(odoo_state)
    if sahool_status is None:
        # صدق: حالة Odoo غير معروفة — لا نخترع تطابقاً، نُسجّلها ونتوقّف.
        await log_sync_record(
            "odoo_to_sahool",
            "purchase.order",
            odoo_po_id,
            None,
            "failed",
            f"حالة Odoo غير معروفة: {odoo_state}",
        )
        logger.warning(f"Inbound PO {odoo_po_id} unknown Odoo state: {odoo_state}")
        return

    # 2) حدّث صفّ SAHOOL المرتبط (الربط = odoo_document_id المضبوط عند الدفع الصادر).
    async with pool.acquire() as conn:
        updated = await conn.fetch(
            """UPDATE procurement_orders
               SET status=$1
               WHERE odoo_document_id=$2
               RETURNING order_id""",
            sahool_status,
            str(odoo_po_id),
        )

    if not updated:
        # لا صفّ مرتبط: قد يكون الأمر أُنشئ في Odoo مباشرةً (لا أصل SAHOOL).
        # صدق: لا نختلق صفّاً — نُسجّل الحالة ونخرج.
        await log_sync_record(
            "odoo_to_sahool",
            "purchase.order",
            odoo_po_id,
            None,
            "skipped",
            f"لا procurement_orders مرتبط بـodoo_document_id={odoo_po_id} (state={odoo_state})",
        )
        logger.info(f"Inbound PO {odoo_po_id}: no linked SAHOOL order (state={odoo_state})")
        return

    sahool_order_id = str(updated[0]["order_id"])
    # 3) سجّل المزامنة في الاتجاه الوارد (يطابق توقيع log_sync_record الصادر).
    await log_sync_record(
        "odoo_to_sahool",
        "purchase.order",
        odoo_po_id,
        sahool_order_id,
        "success",
        f"{odoo_state} → {sahool_status}",
    )
    logger.info(
        f"Inbound PO {odoo_po_id} ({po.get('name')}): "
        f"{odoo_state} → {sahool_status} on order {sahool_order_id}"
    )


async def sync_field_costs_to_odoo():
    """Push SAHOOL field_cost_ledger → selected ERP provider.

    ADR-0001: provider-neutral. NullProvider marks costs synced locally; ERPNext/Odoo use
    provider-specific push_field_cost implementations. No Odoo client is constructed unless
    ERP_PROVIDER=odoo.
    """
    pool = await get_pool()
    if not pool:
        return
    provider = get_active_erp_provider()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM field_cost_ledger
               WHERE odoo_sync_status='pending' ORDER BY recorded_at LIMIT 100"""
        )

        for row in rows:
            ledger_id = row["ledger_id"]
            cost = {
                "amount": float(row.get("total_cost_usd", 0) or 0),
                "description": f"{row.get('category', 'cost')} — {row.get('item_name', 'field cost')}",
                "posting_date": row["recorded_at"].strftime("%Y-%m-%d")
                if row.get("recorded_at")
                else None,
                "ledger_id": str(ledger_id),
                "field_id": str(row.get("field_id")) if row.get("field_id") is not None else None,
                "tenant_id": str(row.get("tenant_id"))
                if row.get("tenant_id") is not None
                else None,
            }
            try:
                pushed = await provider.push_field_cost(cost)
                if pushed:
                    await conn.execute(
                        "UPDATE field_cost_ledger SET odoo_sync_status='synced', odoo_entry_id=$1 WHERE ledger_id=$2",
                        f"{provider.name}:{ledger_id}",
                        ledger_id,
                    )
                    await log_sync_record(
                        "sahool_to_erp",
                        "field_cost",
                        None,
                        str(ledger_id),
                        "success",
                        f"provider={provider.name}",
                    )
                else:
                    await conn.execute(
                        "UPDATE field_cost_ledger SET odoo_sync_status='failed' WHERE ledger_id=$1",
                        ledger_id,
                    )
                    await log_sync_record(
                        "sahool_to_erp",
                        "field_cost",
                        None,
                        str(ledger_id),
                        "failed",
                        f"provider={provider.name}: rejected",
                    )
            except NotImplementedError as e:
                # Provider selected but this deployment lacks required account mapping.
                await conn.execute(
                    "UPDATE field_cost_ledger SET odoo_sync_status='failed' WHERE ledger_id=$1",
                    ledger_id,
                )
                await log_sync_record(
                    "sahool_to_erp",
                    "field_cost",
                    None,
                    str(ledger_id),
                    "failed",
                    str(e)[:500],
                )
            except Exception as e:  # noqa: BLE001
                await conn.execute(
                    "UPDATE field_cost_ledger SET odoo_sync_status='failed' WHERE ledger_id=$1",
                    ledger_id,
                )
                await log_sync_record(
                    "sahool_to_erp",
                    "field_cost",
                    None,
                    str(ledger_id),
                    "failed",
                    type(e).__name__,
                )
                logger.warning("field_cost sync failed via %s: %s", provider.name, type(e).__name__)


# ══════════════════════════════════════════════════════════════
# Background Sync Scheduler
# ══════════════════════════════════════════════════════════════
async def periodic_sync():
    while True:
        provider = get_active_erp_provider()
        if provider.name == "none":
            logger.info("ERP provider disabled → periodic ERP sync skipped")
            await asyncio.sleep(SYNC_INTERVAL_SEC)
            continue
        try:
            logger.info("Starting periodic ERP sync via %s...", provider.name)
            await sync_products()
            await sync_suppliers()
            await sync_warehouses()
            # Procurement order push/pull is still Odoo-specific until the shared
            # ERPProvider interface grows a procurement contract. Do not construct
            # or require Odoo unless explicitly selected.
            if provider.name == "odoo":
                await sync_procurement_orders_to_odoo()
            await sync_field_costs_to_odoo()
            logger.info("Periodic ERP sync complete via %s.", provider.name)
        except Exception as e:  # noqa: BLE001
            logger.error("Periodic ERP sync error: %s", type(e).__name__)
        await asyncio.sleep(SYNC_INTERVAL_SEC)
