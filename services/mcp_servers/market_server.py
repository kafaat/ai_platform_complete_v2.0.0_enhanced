#!/usr/bin/env python3
"""
SAHOOL v9.1 — Market MCP Server (FIXED)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal

import asyncpg
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPBearer
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field
from shared.oauth_middleware import require_scope  # FIX(أمان): حارس نطاق لنقاط MCP

logger = logging.getLogger("market-mcp")
logging.basicConfig(
    level=logging.INFO, format='{"time":"%(asctime)s","svc":"market-mcp","msg":"%(message)s"}'
)

DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
ODOO_BRIDGE_URL = os.getenv("ODOO_BRIDGE_URL", "http://sahool-odoo-bridge:8126")
SAHOOL_API_URL = os.getenv("SAHOOL_API_URL", "http://sahool-auth:8000")

_pool: asyncpg.Pool | None = None
security = HTTPBearer(auto_error=False)
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}


def verify_token(token: str) -> dict:
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise HTTPException(503, "JWT_SECRET غير مضبوط — الخدمة معطّلة بأمان")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience="sahool")
    except InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}") from e
    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(401, "Invalid token issuer")
    return payload


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None and DATABASE_URL:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    if _pool is None:
        raise HTTPException(503, "Database not configured")
    return _pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    if DATABASE_URL:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        logger.info("✅ Market MCP DB connected")
    else:
        logger.warning("DATABASE_URL not set — running in demo mode")
    logger.info("📦 Market MCP ready")
    yield
    if _pool:
        await _pool.close()


app = FastAPI(title="SAHOOL Market MCP", version="9.1.0", lifespan=lifespan)
# ✅ OTEL
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    logger.debug("OTEL غير مثبّت (اختياري)")


def record_to_dict(record) -> dict:
    """Convert asyncpg Record to JSON-serializable dict.
    Handles: UUID, Decimal, datetime, date objects.
    """
    import uuid
    from datetime import datetime

    d = dict(record)
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = float(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, date):
            d[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            d[k] = str(v)
    return d


async def _get_current_user(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required")
    return verify_token(auth[7:])


# ── Tool Implementations ───────────────────────────────────────


async def tool_search_products(args: dict) -> dict:
    pool = await get_pool()
    tenant_id = args.get("tenant_id")
    query = args.get("query", "")
    category = args.get("category")
    supplier_id = args.get("supplier_id")
    max_price = args.get("max_price_usd")
    in_stock = args.get("in_stock_only", True)
    limit = min(args.get("limit", 20), 100)
    conditions = ["1=1"]
    params = []
    if query:
        params.append(f"%{query}%")
        conditions.append(
            f"(product_name ILIKE ${len(params)} OR product_name_ar ILIKE ${len(params)} OR sku ILIKE ${len(params)})"
        )
    if category:
        params.append(category)
        conditions.append(f"category = ${len(params)}")
    if supplier_id:
        params.append(supplier_id)
        conditions.append(f"supplier_id = ${len(params)}::uuid")
    if max_price is not None:
        params.append(max_price)
        conditions.append(f"unit_price_usd <= ${len(params)}")
    if in_stock:
        conditions.append("stock_qty > 0")
    where_clause = " AND ".join(conditions)
    sql = f"""
        SELECT p.*, s.name as supplier_name, s.rating as supplier_rating, s.country as supplier_country
        FROM market_products p
        LEFT JOIN market_suppliers s ON p.supplier_id = s.supplier_id
        WHERE {where_clause}
        ORDER BY p.featured DESC, p.unit_price_usd ASC
        LIMIT ${len(params) + 1}
    """
    params.append(limit)
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id) if tenant_id else ""
        )  # CRIT-10/11 FIX
        rows = await conn.fetch(sql, *params)
    return {"products": [record_to_dict(r) for r in rows], "count": len(rows)}


async def tool_get_supplier(args: dict) -> dict:
    pool = await get_pool()
    tenant_id = args.get("tenant_id")
    sid = args.get("supplier_id")
    sname = args.get("supplier_name")
    if not sid and not sname:
        raise HTTPException(400, "supplier_id or supplier_name required")
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id) if tenant_id else ""
        )  # CRIT-10/11 FIX
        if sid:
            row = await conn.fetchrow(
                "SELECT * FROM market_suppliers WHERE supplier_id=$1::uuid", sid
            )
        else:
            row = await conn.fetchrow(
                "SELECT * FROM market_suppliers WHERE name ILIKE $1", f"%{sname}%"
            )
        if not row:
            return {"supplier": None, "products": []}
        products = await conn.fetch(
            "SELECT product_id, product_name, product_name_ar, category, unit_price_usd, stock_qty, currency FROM market_products WHERE supplier_id=$1::uuid AND active=true",
            str(row["supplier_id"]),
        )
    return {
        "supplier": record_to_dict(row),
        "products": [record_to_dict(p) for p in products],
        "product_count": len(products),
    }


async def tool_create_procurement(args: dict) -> dict:
    pool = await get_pool()
    tenant_id = args["tenant_id"]
    field_id = args.get("field_id")
    items = args["items"]
    delivery_date = args.get("delivery_date")
    notes = args.get("notes", "")
    auto_approve = args.get("auto_approve_below_usd", 500)
    total_estimated = 0.0
    for it in items:
        qty = float(it.get("quantity", 0))
        price = float(it.get("max_unit_price_usd", 0))
        total_estimated += qty * price
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id) if tenant_id else ""
        )  # CRIT-10/11 FIX
        async with conn.transaction():
            order_id = await conn.fetchval(
                """INSERT INTO market_procurement_orders
                    (tenant_id, field_id, status, total_estimated_usd, delivery_date, notes, auto_approve_threshold)
                    VALUES ($1::uuid, $2, $3, $4, $5, $6, $7)
                    RETURNING order_id""",
                tenant_id,
                field_id,
                "draft",
                total_estimated,
                delivery_date,
                notes,
                auto_approve,
            )
            for it in items:
                await conn.execute(
                    """INSERT INTO market_procurement_items
                        (order_id, product_id, product_name, quantity, unit, max_unit_price_usd, notes)
                        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7)""",
                    order_id,
                    it.get("product_id") if it.get("product_id") else None,
                    it["product_name"],
                    float(it["quantity"]),
                    it.get("unit", "kg"),
                    float(it.get("max_unit_price_usd", 0)),
                    it.get("notes", ""),
                )
            new_status = "draft"
            if total_estimated <= auto_approve:
                new_status = "approved"
                await conn.execute(
                    "UPDATE market_procurement_orders SET status=$1, approved_at=NOW() WHERE order_id=$2",
                    new_status,
                    order_id,
                )
            else:
                await conn.execute(
                    "UPDATE market_procurement_orders SET status=$1 WHERE order_id=$2",
                    "pending_approval",
                    order_id,
                )
    return {
        "order_id": str(order_id),
        "status": new_status,
        "total_estimated_usd": round(total_estimated, 2),
        "item_count": len(items),
        "auto_approved": total_estimated <= auto_approve,
        "message": "Order created."
        + (
            " Auto-approved (below threshold)."
            if total_estimated <= auto_approve
            else " Awaiting approval."
        ),
    }


async def tool_get_procurement_status(args: dict) -> dict:
    pool = await get_pool()
    tenant_id = args.get("tenant_id")
    order_id = args["order_id"]
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id) if tenant_id else ""
        )  # CRIT-10/11 FIX
        row = await conn.fetchrow(
            "SELECT * FROM market_procurement_orders WHERE order_id=$1::uuid", order_id
        )
        if not row:
            raise HTTPException(404, "Order not found")
        items = await conn.fetch(
            "SELECT * FROM market_procurement_items WHERE order_id=$1::uuid", order_id
        )
    result = record_to_dict(row)
    result["items"] = [record_to_dict(i) for i in items]
    return result


async def tool_create_sales_listing(args: dict) -> dict:
    pool = await get_pool()
    tenant_id = args["tenant_id"]
    batch_id = args.get("batch_id")
    crop = args["crop_type"]
    qty = float(args["quantity_kg"])
    price = float(args["price_per_kg_usd"])
    grade = args.get("quality_grade", "A")
    certs = args.get("certifications", [])
    from_date = args.get("available_from")
    until_date = args.get("available_until")
    pickup = args.get("pickup_location", "")
    notes = args.get("notes", "")
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id) if tenant_id else ""
        )  # CRIT-10/11 FIX
        listing_id = await conn.fetchval(
            """INSERT INTO market_sales_listings
                (tenant_id, batch_id, crop_type, quantity_kg, price_per_kg_usd,
                 quality_grade, certifications, available_from, available_until, pickup_location, notes, status)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING listing_id""",
            tenant_id,
            batch_id if batch_id else None,
            crop,
            qty,
            price,
            grade,
            certs,
            from_date,
            until_date,
            pickup,
            notes,
            "active",
        )
    return {
        "listing_id": str(listing_id),
        "status": "active",
        "": round(qty * price, 2),
        "qr_trace_url": f"/trace/{batch_id}" if batch_id else None,
    }


async def tool_search_sales(args: dict) -> dict:
    pool = await get_pool()
    tenant_id = args.get("tenant_id")
    crop = args.get("crop_type")
    grade = args.get("quality_grade")
    max_price = args.get("max_price_usd")
    available = args.get("available_now", True)
    limit = min(args.get("limit", 20), 100)
    conditions = ["status = 'active'"]
    params = []
    if crop:
        params.append(f"%{crop}%")
        conditions.append(f"crop_type ILIKE ${len(params)}")
    if grade:
        params.append(grade)
        conditions.append(f"quality_grade = ${len(params)}")
    if max_price is not None:
        params.append(max_price)
        conditions.append(f"price_per_kg_usd <= ${len(params)}")
    if available:
        conditions.append("(available_until IS NULL OR available_until >= CURRENT_DATE)")
        conditions.append("(available_from IS NULL OR available_from <= CURRENT_DATE)")
    where_clause = " AND ".join(conditions)
    sql = f"""
        SELECT * FROM market_sales_listings
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ${len(params) + 1}
    """
    params.append(limit)
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id) if tenant_id else ""
        )  # CRIT-10/11 FIX
        rows = await conn.fetch(sql, *params)
    return {"listings": [record_to_dict(r) for r in rows], "count": len(rows)}


async def tool_price_history(args: dict) -> dict:
    pool = await get_pool()
    tenant_id = args.get("tenant_id")
    category = args["category"]
    days = min(args.get("days", 90), 365)
    agg = args.get("aggregation", "weekly")
    trunc = {"daily": "day", "weekly": "week", "monthly": "month"}.get(agg, "week")
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id) if tenant_id else ""
        )  # CRIT-10/11 FIX
        rows = await conn.fetch(
            f"""
            SELECT DATE_TRUNC('{trunc}', recorded_date) as period,
                AVG(price_usd) as avg_price, MIN(price_usd) as min_price,
                MAX(price_usd) as max_price, COUNT(*) as sample_count
            FROM market_price_history
            WHERE category = $1 AND recorded_date >= CURRENT_DATE - $2::interval
            GROUP BY DATE_TRUNC('{trunc}', recorded_date)
            ORDER BY period DESC
            LIMIT 52
            """,
            category,
            f"{days} days",
        )
    return {
        "category": category,
        "days": days,
        "aggregation": agg,
        "history": [record_to_dict(r) for r in rows],
    }


async def tool_analytics_dashboard(args: dict) -> dict:
    pool = await get_pool()
    tenant_id = args["tenant_id"]
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id) if tenant_id else ""
        )  # CRIT-10/11 FIX
        proc = await conn.fetchrow(
            """SELECT COUNT(*) as total_orders, SUM(total_estimated_usd) as total_value,
                COUNT(*) FILTER (WHERE status='pending_approval') as pending_count,
                COUNT(*) FILTER (WHERE status='approved') as approved_count
                FROM market_procurement_orders
                WHERE tenant_id=$1::uuid AND created_at >= CURRENT_DATE - INTERVAL '30 days'""",
            tenant_id,
        )
        listings = await conn.fetchrow(
            """SELECT COUNT(*) as active_listings, SUM(quantity_kg) as total_kg_listed,
                SUM(total_value_usd) as total_listed_value
                FROM market_sales_listings
                WHERE tenant_id=$1::uuid AND status='active'""",
            tenant_id,
        )
        inventory = await conn.fetchrow(
            """SELECT COUNT(*) as product_count, SUM(stock_qty * unit_price_usd) as inventory_value_usd
                FROM market_products
                WHERE tenant_id=$1::uuid AND active=true""",
            tenant_id,
        )
        alerts = await conn.fetch(
            """SELECT product_name, category, unit_price_usd,
                    LAG(unit_price_usd) OVER (PARTITION BY product_id ORDER BY updated_at) as prev_price
             FROM market_products
             WHERE tenant_id=$1::uuid AND updated_at >= CURRENT_DATE - INTERVAL '7 days'
             ORDER BY updated_at DESC
             LIMIT 10""",
            tenant_id,
        )
    return {
        "tenant_id": tenant_id,
        "period": "last_30_days",
        "procurement": record_to_dict(proc),
        "sales_marketplace": record_to_dict(listings),
        "inventory": record_to_dict(inventory),
        "price_alerts": [record_to_dict(a) for a in alerts],
    }


# ── NEW tools required by market_skill.py ─────────────────────
async def tool_get_market_price(args: dict) -> dict:
    pool = await get_pool()
    tenant_id = args.get("tenant_id")
    crop = args.get("crop", "wheat")
    market = args.get("market", "sanaa")
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id) if tenant_id else ""
        )  # CRIT-10/11 FIX
        row = await conn.fetchrow(
            "SELECT AVG(price_usd) as avg_price FROM market_price_history WHERE category=$1 AND market_location=$2 AND recorded_date >= CURRENT_DATE - INTERVAL '7 days'",
            crop,
            market,
        )
    price = float(row["avg_price"]) if row and row["avg_price"] else 0.0
    return {
        "price_yer_kg": round(price * 250, 2),
        "price_usd_kg": round(price, 4),
        "trend": "stable",
        "updated": datetime.now(UTC).isoformat(),
    }


async def tool_get_price_trend(args: dict) -> dict:
    pool = await get_pool()
    tenant_id = args.get("tenant_id")
    crop = args.get("crop", "wheat")
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id) if tenant_id else ""
        )  # CRIT-10/11 FIX
        rows = await conn.fetch(
            "SELECT recorded_date, price_usd FROM market_price_history WHERE category=$1 ORDER BY recorded_date DESC LIMIT 30",
            crop,
        )
    prices = [float(r["price_usd"]) for r in rows if r["price_usd"]]
    current = prices[0] if prices else 0
    prev = prices[-1] if len(prices) > 1 else current
    change = ((current - prev) / prev * 100) if prev else 0
    return {
        "current_price": round(current, 4),
        "price_change_pct": round(change, 2),
        "forecast": "stable" if abs(change) < 5 else ("up" if change > 0 else "down"),
        "trend_data": [
            {"date": str(r["recorded_date"]), "price": float(r["price_usd"])} for r in rows[:7]
        ],
    }


async def tool_create_forward_contract(args: dict) -> dict:
    return {
        "contract_id": f"SAHOOL-FC-{uuid.uuid4().hex[:8].upper()}",
        "agreed_price_yer_kg": round(float(args.get("estimated_yield_kg", 1000)) * 0.3, 2),
        "total_contract_value_yer": round(float(args.get("estimated_yield_kg", 1000)) * 300, 2),
        "status": "pending",
        "next_steps": ["Verify crop quality at harvest", "Schedule delivery", "Issue invoice"],
    }


# ── MCP Endpoints ────────────────────────────────────────────
class MCPCallRequest(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


@app.get("/mcp/v1/tools/list", dependencies=[Depends(require_scope("market:read"))])
async def mcp_tools_list():
    return {
        "tools": [
            {
                "name": "market_search_products",
                "description": "Search agricultural products catalog",
            },
            {"name": "market_get_supplier", "description": "Get supplier details"},
            {"name": "market_create_procurement", "description": "Create procurement order"},
            {"name": "market_get_procurement_status", "description": "Check order status"},
            {"name": "market_create_sales_listing", "description": "List farm produce for sale"},
            {"name": "market_search_sales", "description": "Search crop sales listings"},
            {"name": "market_price_history", "description": "Get historical price trends"},
            {"name": "market_analytics_dashboard", "description": "Market analytics snapshot"},
            {"name": "get_market_price", "description": "Current market price for crop"},
            {"name": "get_price_trend", "description": "Price trend analysis"},
            {"name": "create_forward_contract", "description": "Create forward sales contract"},
        ]
    }


_MARKET_WRITE_TOOLS = {
    "market_create_procurement",
    "market_create_sales_listing",
    "create_forward_contract",
}


@app.post("/mcp/v1/tools/call")
async def mcp_tools_call(req: MCPCallRequest, user: dict = Depends(require_scope("market:read"))):
    handlers = {
        "market_search_products": tool_search_products,
        "market_get_supplier": tool_get_supplier,
        "market_create_procurement": tool_create_procurement,
        "market_get_procurement_status": tool_get_procurement_status,
        "market_create_sales_listing": tool_create_sales_listing,
        "market_search_sales": tool_search_sales,
        "market_price_history": tool_price_history,
        "market_analytics_dashboard": tool_analytics_dashboard,
        "get_market_price": tool_get_market_price,
        "get_price_trend": tool_get_price_trend,
        "create_forward_contract": tool_create_forward_contract,
    }
    handler = handlers.get(req.name)
    if not handler:
        raise HTTPException(404, f"Unknown tool: {req.name}")

    # عزل المستأجِر الحاسم: tenant_id من التوكن المُتحقَّق لا من جسم الطلب (كان قابلاً
    # للانتحال ⇒ قراءة/كتابة عابرة المستأجرين). نحقن المُتحقَّق فوق أيّ قيمة مُرسَلة.
    trusted_tenant = user.get("tenant_id")
    if not trusted_tenant:
        raise HTTPException(401, "Token missing tenant_id")
    args = dict(req.arguments or {})
    args["tenant_id"] = trusted_tenant
    # أدوات الكتابة/الصرف تتطلّب market:write (كانت بـmarket:read فقط ⇒ توكن قراءة يشتري).
    scopes = (user.get("scope", "") or "").split()
    if req.name in _MARKET_WRITE_TOOLS and not ("market:write" in scopes or "admin" in scopes):
        raise HTTPException(403, "scope 'market:write' required for write operations")
    try:
        result = await handler(args)
        return {
            "content": [
                {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
            ],
            "isError": False,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tool {req.name} error: {e}")
        return {
            "content": [
                {"type": "text", "text": json.dumps({"error": str(e)}, ensure_ascii=False)}
            ],
            "isError": True,
        }


# ── REST Endpoints (FIXED: auth required) ────────────────────
@app.get("/products")
async def api_search_products(
    q: str | None = None,
    category: str | None = None,
    limit: int = 20,
    user: dict = Depends(_get_current_user),
):
    return await tool_search_products(
        {"query": q or "", "category": category, "limit": limit, "tenant_id": user.get("tenant_id")}
    )


@app.get("/suppliers/{supplier_id}")
async def api_get_supplier(supplier_id: str, user: dict = Depends(_get_current_user)):
    return await tool_get_supplier({"supplier_id": supplier_id, "tenant_id": user.get("tenant_id")})


@app.post("/procurement")
async def api_create_procurement(body: dict, user: dict = Depends(_get_current_user)):
    # tenant من التوكن لا من الجسم (منع كتابة عابرة المستأجرين).
    return await tool_create_procurement({**(body or {}), "tenant_id": user.get("tenant_id")})


@app.get("/procurement/{order_id}")
async def api_get_procurement(order_id: str, user: dict = Depends(_get_current_user)):
    return await tool_get_procurement_status(
        {"order_id": order_id, "tenant_id": user.get("tenant_id")}
    )


@app.post("/sales")
async def api_create_sales(body: dict, user: dict = Depends(_get_current_user)):
    return await tool_create_sales_listing({**(body or {}), "tenant_id": user.get("tenant_id")})


@app.get("/sales")
async def api_search_sales(
    crop: str | None = None,
    grade: str | None = None,
    limit: int = 20,
    user: dict = Depends(_get_current_user),
):
    return await tool_search_sales(
        {
            "crop_type": crop,
            "quality_grade": grade,
            "limit": limit,
            "tenant_id": user.get("tenant_id"),
        }
    )


@app.get("/price-history/{category}")
async def api_price_history(category: str, days: int = 90, user: dict = Depends(_get_current_user)):
    return await tool_price_history(
        {"category": category, "days": days, "tenant_id": user.get("tenant_id")}
    )


@app.get("/analytics/{tenant_id}")
async def api_analytics(tenant_id: str, user: dict = Depends(_get_current_user)):
    # tenant من التوكن لا من المسار (منع قراءة تحليلات مستأجِر آخر).
    return await tool_analytics_dashboard({"tenant_id": user.get("tenant_id")})


@app.get("/healthz")
@app.get("/health")
async def health():
    db_ok = False
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Health check has no tenant context; probe DB connectivity with empty tenant.
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", ""
            )  # CRIT-10/11 FIX
            await conn.fetchval("SELECT 1")
            db_ok = True
    except Exception as e:  # noqa: BLE001
        logger.debug("فحص صحّة DB فشل: %s", type(e).__name__)
    return {"status": "alive", "service": "market-mcp", "db_connected": db_ok}


@app.get("/readyz")
async def readyz():
    return {"status": "ready", "version": "9.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
