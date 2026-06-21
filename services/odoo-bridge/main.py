#!/usr/bin/env python3
"""
SAHOOL v9.1 — Odoo ERP Bridge (JSON-RPC/XML-RPC)
Bidirectional sync: Odoo ↔ SAHOOL

Syncs:
  Odoo → SAHOOL: products, suppliers, warehouses, accounts, UoM
  SAHOOL → Odoo: procurement orders, inventory moves, field costs, crop batches

Odoo API docs: https://www.odoo.com/documentation/18.0/developer/reference/external_api.html
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import asyncpg
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from jose import JWTError as _JE
from jose import jwt as _jwt
from pydantic import BaseModel, Field

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("odoo-bridge")
except ImportError:
    logging.basicConfig(
        level=logging.INFO, format='{"time":"%(asctime)s","svc":"odoo-bridge","msg":"%(message)s"}'
    )
    logger = logging.getLogger("odoo-bridge")

# ── Config ────────────────────────────────────────────────────
ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
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
    """Sync Odoo products → SAHOOL inventory items."""
    odoo = get_odoo()
    last_sync = await get_last_sync("product.product", "odoo_to_sahool")
    domain = [["write_date", ">", last_sync.isoformat()]] if last_sync else []

    products = await odoo.search_read(
        "product.product",
        domain,
        [
            "id",
            "name",
            "default_code",
            "categ_id",
            "uom_id",
            "list_price",
            "standard_price",
            "type",
            "write_date",
        ],
        limit=500,
    )

    pool = await get_pool()
    if not pool:
        return

    synced = 0
    async with pool.acquire() as conn:
        for p in products:
            category = p.get("categ_id")[1] if isinstance(p.get("categ_id"), list) else "General"
            uom = p.get("uom_id")[1] if isinstance(p.get("uom_id"), list) else "Unit"

            # عزل المستأجر: الكتالوج عالميّ افتراضيّاً (tenant_id=NULL)؛ لا نُسنده
            # لمستأجر إلّا حين يُضبط ODOO_SYNC_TENANT_ID صراحةً (لا تلفيق). نُدرج
            # العمود ديناميكيّاً ليبقى INSERT صالحاً سواء كان الكتالوج عالميّاً أو
            # مُسنداً، دون فرض tenant_id على مفتاح odoo_product_id الفريد العالميّ.
            if ODOO_SYNC_TENANT_ID:
                await conn.execute(
                    """INSERT INTO inventory_stock (item_name, category, unit, unit_cost_usd,
                            quantity_in_stock, reorder_level, supplier, odoo_product_id,
                            tenant_id, last_synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                        ON CONFLICT (odoo_product_id) DO UPDATE SET
                            item_name=$1, category=$2, unit=$3, unit_cost_usd=$4,
                            tenant_id=$9, last_synced_at=NOW()""",
                    p["name"],
                    category,
                    uom,
                    float(p.get("standard_price", 0) or 0),
                    0,  # qty managed by inventory moves
                    10,
                    "Odoo Sync",
                    str(p["id"]),
                    ODOO_SYNC_TENANT_ID,
                )
            else:
                await conn.execute(
                    """INSERT INTO inventory_stock (item_name, category, unit, unit_cost_usd,
                            quantity_in_stock, reorder_level, supplier, odoo_product_id, last_synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW())
                        ON CONFLICT (odoo_product_id) DO UPDATE SET
                            item_name=$1, category=$2, unit=$3, unit_cost_usd=$4,
                            last_synced_at=NOW()""",
                    p["name"],
                    category,
                    uom,
                    float(p.get("standard_price", 0) or 0),
                    0,  # qty managed by inventory moves
                    10,
                    "Odoo Sync",
                    str(p["id"]),
                )
            synced += 1

    await set_last_sync("product.product", "odoo_to_sahool", datetime.now(UTC))
    await log_sync_record(
        "odoo_to_sahool", "product.product", None, None, "success", f"Synced {synced} products"
    )
    logger.info(f"Products synced: {synced}")


async def sync_suppliers():
    """Sync Odoo res.partner (suppliers) → SAHOOL suppliers."""
    odoo = get_odoo()
    last_sync = await get_last_sync("res.partner", "odoo_to_sahool")
    domain = [["supplier_rank", ">", 0]]
    if last_sync:
        domain[0].append("|")
        domain[0].append(["write_date", ">", last_sync.isoformat()])

    partners = await odoo.search_read(
        "res.partner",
        domain,
        [
            "id",
            "name",
            "phone",
            "email",
            "street",
            "city",
            "country_id",
            "supplier_rank",
            "write_date",
        ],
        limit=200,
    )

    pool = await get_pool()
    if not pool:
        return

    synced = 0
    async with pool.acquire() as conn:
        for p in partners:
            country = p.get("country_id")[1] if isinstance(p.get("country_id"), list) else ""
            address = f"{p.get('street', '')} {p.get('city', '')} {country}".strip()
            # عزل المستأجر: كتالوج المورّدين عالميّ افتراضيّاً (المفتاح الفريد
            # odoo_partner_id عالميّ بلا tenant_id). نُسنده لمستأجر فقط حين يُضبط
            # ODOO_SYNC_TENANT_ID صراحةً — لا نُلفّق ملكيّة.
            if ODOO_SYNC_TENANT_ID:
                await conn.execute(
                    """INSERT INTO suppliers (name, contact_person, phone, email, address,
                            rating, categories, active, odoo_partner_id, tenant_id, last_synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW())
                        ON CONFLICT (odoo_partner_id) DO UPDATE SET
                            name=$1, phone=$3, email=$4, address=$5,
                            tenant_id=$10, last_synced_at=NOW()""",
                    p["name"],
                    p["name"],
                    p.get("phone", ""),
                    p.get("email", ""),
                    address,
                    4.0,
                    ["general"],
                    True,
                    str(p["id"]),
                    ODOO_SYNC_TENANT_ID,
                )
            else:
                await conn.execute(
                    """INSERT INTO suppliers (name, contact_person, phone, email, address,
                            rating, categories, active, odoo_partner_id, last_synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                        ON CONFLICT (odoo_partner_id) DO UPDATE SET
                            name=$1, phone=$3, email=$4, address=$5, last_synced_at=NOW()""",
                    p["name"],
                    p["name"],
                    p.get("phone", ""),
                    p.get("email", ""),
                    address,
                    4.0,
                    ["general"],
                    True,
                    str(p["id"]),
                )
            synced += 1

    await set_last_sync("res.partner", "odoo_to_sahool", datetime.now(UTC))
    await log_sync_record(
        "odoo_to_sahool", "res.partner", None, None, "success", f"Synced {synced} suppliers"
    )
    logger.info(f"Suppliers synced: {synced}")


async def sync_warehouses():
    """Sync Odoo stock.warehouse → SAHOOL (for multi-location inventory)."""
    odoo = get_odoo()
    whs = await odoo.search_read(
        "stock.warehouse", [], ["id", "name", "code", "partner_id"], limit=50
    )
    pool = await get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        for w in whs:
            await conn.execute(
                """INSERT INTO inventory_locations (location_name, location_code, odoo_warehouse_id)
                    VALUES ($1,$2,$3)
                    ON CONFLICT (odoo_warehouse_id) DO UPDATE SET location_name=$1, location_code=$2""",
                w["name"],
                w.get("code", ""),
                str(w["id"]),
            )
    logger.info(f"Warehouses synced: {len(whs)}")


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
    """Push SAHOOL field_cost_ledger → Odoo analytic entries (if Analytic Accounting enabled)."""
    pool = await get_pool()
    if not pool:
        return
    odoo = get_odoo()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM field_cost_ledger
               WHERE odoo_sync_status='pending' ORDER BY recorded_at LIMIT 100"""
        )

        for row in rows:
            try:
                # Map to Odoo analytic line or journal entry
                # Requires analytic account per field in Odoo
                vals = {
                    "name": f"{row['category']} — {row['item_name']}",
                    "amount": -float(row["total_cost_usd"]),  # negative = cost
                    "date": row["recorded_at"].strftime("%Y-%m-%d"),
                    "ref": f"SAHOOL-{row['ledger_id']}",
                }
                # Use analytic line if module installed
                entry_id = await odoo.create("account.analytic.line", vals)

                await conn.execute(
                    "UPDATE field_cost_ledger SET odoo_sync_status='synced', odoo_entry_id=$1 WHERE ledger_id=$2",
                    str(entry_id),
                    row["ledger_id"],
                )
                await log_sync_record(
                    "sahool_to_odoo",
                    "account.analytic.line",
                    entry_id,
                    str(row["ledger_id"]),
                    "success",
                )
            except Exception as e:
                await conn.execute(
                    "UPDATE field_cost_ledger SET odoo_sync_status='failed' WHERE ledger_id=$1",
                    row["ledger_id"],
                )
                await log_sync_record(
                    "sahool_to_odoo",
                    "account.analytic.line",
                    None,
                    str(row["ledger_id"]),
                    "failed",
                    str(e)[:500],
                )


# ══════════════════════════════════════════════════════════════
# Background Sync Scheduler
# ══════════════════════════════════════════════════════════════
async def periodic_sync():
    while True:
        # احترام مفتاح التبديل: لا تزامن Odoo إلّا حين ERP_PROVIDER=odoo.
        # حين none/erpnext (أو Odoo مُستثنى من البناء) → تخطٍّ نظيف بلا أخطاء.
        provider = os.getenv("ERP_PROVIDER", "erpnext").strip().lower()
        if provider != "odoo":
            logger.info(f"ERP_PROVIDER={provider} → تخطّي مزامنة Odoo (لا حاوية Odoo)")
            await asyncio.sleep(SYNC_INTERVAL_SEC)
            continue
        try:
            logger.info("Starting periodic Odoo sync...")
            await sync_products()
            await sync_suppliers()
            await sync_warehouses()
            await sync_procurement_orders_to_odoo()
            await sync_field_costs_to_odoo()
            logger.info("Periodic sync complete.")
        except Exception as e:
            logger.error(f"Periodic sync error: {e}")
        await asyncio.sleep(SYNC_INTERVAL_SEC)


# ══════════════════════════════════════════════════════════════
# Lifespan
# ══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    if SAHOOL_DB_URL:
        _pool = await asyncpg.create_pool(SAHOOL_DB_URL, min_size=1, max_size=5)
        logger.info("DB pool ready")
        # FINDING-001: ارفض الإقلاع إن تجاوز دور الاتّصال RLS (fail-closed افتراضيّاً).
        from shared.db_role_guard import assert_db_role_rls_safe

        await assert_db_role_rls_safe(_pool, service="odoo-bridge")
        await _run_migrations()
    # Odoo: نتّصل فقط حين يكون المزوّد المختار odoo (الأساسي erpnext لا يحتاج Odoo
    # — فلا محاولات اتصال/تحذيرات في بيئة بلا حاوية Odoo).
    if os.getenv("ERP_PROVIDER", "erpnext").strip().lower() == "odoo":
        try:
            odoo = get_odoo()
            await odoo.authenticate()
            logger.info("Odoo bridge initialized")
        except Exception as e:
            logger.warning(f"Odoo not reachable yet: {e}")
    else:
        logger.info("ERP_PROVIDER != odoo → تخطّي تهيئة Odoo (اختياري؛ الأساسي erpnext)")
    # Start background sync (احتفظ بالمرجع لمنع GC المبكّر)
    app.state.sync_task = asyncio.create_task(periodic_sync())
    yield
    if _odoo:
        await _odoo.close()
    if _pool:
        await _pool.close()


# C-08 FIX: JWT verification with audience
_JWT_PUBLIC = os.getenv("JWT_PUBLIC_KEY", "")
_JWT_SECRET = _JWT_PUBLIC if _JWT_PUBLIC else os.getenv("JWT_SECRET", "")
_JWT_ALG = "RS256" if _JWT_PUBLIC else "HS256"
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}


def verify_token(token: str) -> dict:
    """Verify JWT with audience check."""
    try:
        payload = _jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALG], audience="sahool")
    except _JE as e:
        raise ValueError(f"Invalid token: {e}") from e
    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول يُعامَل كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise ValueError("Invalid token issuer")
    return payload


def require_auth(authorization: str = Header(None)) -> dict:
    """Reusable JWT auth dependency — نفس منطق مصادقة /sync.

    الأمان: نقاط القراءة كانت تكشف بيانات ERP بلا أيّ مصادقة
    (products/suppliers/config/logs/erp.provider). هذه التبعيّة تُطبّق
    نفس فحص /sync: سرّ JWT مضبوط + توكن Bearer صالح بجمهور sahool.
    تُرجِع حمولة التوكن عند النجاح، وترفع HTTPException عند الفشل.
    """
    if not _JWT_SECRET or len(_JWT_SECRET) < 32:
        raise HTTPException(503, "JWT_SECRET غير مضبوط — الوصول معطّل بأمان")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "توكن مطلوب")
    try:
        return verify_token(authorization.split(" ", 1)[1])
    except ValueError as e:
        raise HTTPException(401, "توكن غير صالح") from e


app = FastAPI(title="SAHOOL Odoo Bridge", version="9.1.0", lifespan=lifespan)


# ══════════════════════════════════════════════════════════════
# API Models
# ══════════════════════════════════════════════════════════════
class SyncRequest(BaseModel):
    entity: str = Field(..., pattern="^(products|suppliers|warehouses|procurement|costs|all)$")
    direction: str = Field(
        "bidirectional", pattern="^(odoo_to_sahool|sahool_to_odoo|bidirectional)$"
    )
    tenant_id: str | None = None


class WebhookPayload(BaseModel):
    event: str  # e.g. "purchase.order:confirmed", "product.product:write"
    model: str
    record_id: int
    data: dict = Field(default_factory=dict)
    signature: str | None = None
    # L6 FIX: أُزيل مُحقّق "التوقيع" الميّت (كان pass فقط) لئلّا يوحي بتحقّق
    # توقيع غير موجود. التحقّق الفعلي يجري في نقطة /webhook/odoo عبر
    # hmac.compare_digest على رأس X-Webhook-Secret (يفشل-مغلقاً).


class OdooConfigResponse(BaseModel):
    url: str
    db: str
    user: str
    connected: bool
    uid: int | None = None
    version: str | None = None


# ══════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════
@app.get("/healthz")
@app.get("/health")
async def health():
    # Odoo يُفحَص فقط حين يكون المزوّد المختار odoo؛ غير ذلك odoo_connected=null
    # (غير مفعَّل) بدل false مضلّل — الأساسي erpnext لا يمرّ عبر Odoo.
    provider = os.getenv("ERP_PROVIDER", "erpnext").strip().lower()
    odoo_ok = None
    uid = None
    if provider == "odoo":
        odoo_ok = False
        try:
            odoo = get_odoo()
            uid = odoo.uid if odoo.uid is not None else await odoo.authenticate()
            odoo_ok = True
        except Exception as e:  # noqa: BLE001
            logger.debug("فحص صحّة Odoo فشل: %s", type(e).__name__)
    return {
        "status": "alive",
        "erp_provider": provider,
        "odoo_connected": odoo_ok,  # null حين المزوّد ليس odoo (غير مفعَّل)
        "odoo_uid": uid,
        "sync_interval_sec": SYNC_INTERVAL_SEC,
    }


@app.get("/erp/provider")
async def erp_provider_status(_auth: dict = Depends(require_auth)):
    """يكشف مزوّد ERP النشط (مفتاح التبديل) وحالته.

    ERP_PROVIDER = odoo | erpnext | none — يحدّد المزوّد دون تغيير الكود.
    """
    import os

    from erp_provider import get_erp_provider

    selected = os.getenv("ERP_PROVIDER", "erpnext").strip().lower()
    # نمرّر OdooClient للمزوّد odoo (يعيد استخدام الموجود)
    try:
        provider = get_erp_provider(odoo_client=get_odoo() if selected == "odoo" else None)
        hp = await provider.health()
    except Exception as e:  # noqa: BLE001 — صدق: نُعلن الخطأ لا نخفيه
        return {"selected": selected, "status": "error", "error": str(e)}
    return {"selected": selected, "active_provider": provider.name, "health": hp}


@app.get("/config", response_model=OdooConfigResponse)
async def get_config(_auth: dict = Depends(require_auth)):
    odoo = get_odoo()
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
        logger.warning(f"Config check failed: {e}")
    return OdooConfigResponse(
        url=ODOO_URL, db=ODOO_DB, user=ODOO_USER, connected=connected, uid=uid, version=version
    )


@app.post("/sync")
async def trigger_sync(
    req: SyncRequest,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(require_auth),
):
    """Trigger manual sync — يتطلّب توكناً صالحاً (كان مكشوفاً).

    الأمان: المزامنة تكتب لـERP — تتطلّب مصادقة (نفس require_auth المطبَّقة
    على نقاط القراءة).
    """
    if req.entity == "all" or req.entity == "products":
        background_tasks.add_task(sync_products)
    if req.entity == "all" or req.entity == "suppliers":
        background_tasks.add_task(sync_suppliers)
    if req.entity == "all" or req.entity == "warehouses":
        background_tasks.add_task(sync_warehouses)
    if req.entity == "all" or req.entity == "procurement":
        background_tasks.add_task(sync_procurement_orders_to_odoo)
    if req.entity == "all" or req.entity == "costs":
        background_tasks.add_task(sync_field_costs_to_odoo)
    return {"status": "queued", "entity": req.entity, "direction": req.direction}


@app.post("/webhook/odoo")
async def odoo_webhook(payload: WebhookPayload, x_webhook_secret: str = Header(None)):
    """Receive real-time push from Odoo — يتطلّب سرّ webhook (كان مكشوفاً)."""
    # الأمان: webhook مالي/ERP — تحقّق من السرّ المشترك (منع حقن خارجي)
    if not WEBHOOK_SECRET:
        raise HTTPException(503, "WEBHOOK_SECRET غير مضبوط — webhook معطّل بأمان")
    # مقارنة ثابتة الزمن (منع هجوم التوقيت على السرّ)
    import hmac

    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, WEBHOOK_SECRET):
        raise HTTPException(401, "سرّ webhook غير صالح")
    logger.info(f"Odoo webhook: {payload.model}:{payload.record_id} event={payload.event}")

    # Route to appropriate handler
    if payload.model == "product.product":
        asyncio.create_task(sync_products())
    elif payload.model == "res.partner":
        asyncio.create_task(sync_suppliers())
    elif payload.model == "purchase.order":
        # Odoo PO updated → اسحب الحالة وحدّث procurement_orders + سجلّ مزامنة وارد.
        # record_id = معرّف purchase.order في Odoo (راجع docs/ODOO_INTEGRATION.md).
        asyncio.create_task(sync_purchase_order_inbound(payload.record_id))

    return {"received": True, "model": payload.model}


@app.get("/logs")
async def get_logs(limit: int = 50, entity: str | None = None, _auth: dict = Depends(require_auth)):
    pool = await get_pool()
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


@app.get("/products")
async def list_odoo_products(limit: int = 20, _auth: dict = Depends(require_auth)):
    odoo = get_odoo()
    products = await odoo.search_read(
        "product.product",
        [],
        ["id", "name", "default_code", "list_price", "standard_price", "qty_available"],
        limit=limit,
    )
    return {"products": products}


@app.get("/suppliers")
async def list_odoo_suppliers(limit: int = 20, _auth: dict = Depends(require_auth)):
    odoo = get_odoo()
    suppliers = await odoo.search_read(
        "res.partner",
        [["supplier_rank", ">", 0]],
        ["id", "name", "phone", "email", "supplier_rank"],
        limit=limit,
    )
    return {"suppliers": suppliers}


@app.get("/readyz")
async def readyz():
    # جاهزيّة حقيقيّة: حين تُضبط DATABASE_URL يجب أن يكون pool القاعدة حيّاً
    # (مزامنة ERP/الجسر تعتمد عليه). نتحقّق بـSELECT 1؛ تعذُّره ⇒ 503 لا «جاهز» كاذب.
    # حين لا DATABASE_URL مضبوطة (وضع متدرّج معلَن: لا قاعدة محلّيّة) ⇒ جاهز بصدق.
    if _pool is not None:
        try:
            async with _pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as e:
            logger.warning(f"readyz: قاعدة البيانات غير جاهزة — {e}")
            raise HTTPException(503, {"status": "not_ready", "reason": "db"}) from e
    return {"status": "ready", "version": "9.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
