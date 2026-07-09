#!/usr/bin/env python3
"""
SAHOOL v9.1 — ERP Bridge (Odoo / ERPNext / none)
Bidirectional sync: ERP ↔ SAHOOL

Syncs:
  ERP → SAHOOL: products, suppliers, warehouses, accounts, UoM
  SAHOOL → ERP: procurement orders, inventory moves, field costs, crop batches

Odoo API docs: https://www.odoo.com/documentation/18.0/developer/reference/external_api.html
"""

from __future__ import annotations

import asyncio
import hashlib  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
import logging
import os
import sys  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
from contextlib import asynccontextmanager
from datetime import UTC, datetime  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
from pathlib import Path  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
from typing import Any  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)

import asyncpg
import httpx  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
from fastapi import FastAPI, Header, HTTPException
from jose import JWTError as _JE
from jose import jwt as _jwt
from pydantic import BaseModel, Field

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("erp-bridge")
except ImportError:
    logging.basicConfig(
        level=logging.INFO, format='{"time":"%(asctime)s","svc":"erp-bridge","msg":"%(message)s"}'
    )
    logger = logging.getLogger("erp-bridge")

# ── ERP runtime (P1 decomposition) ─────────────────────────────
import erp_runtime as _erp_runtime  # noqa: E402
from erp_runtime import (  # noqa: E402,F401
    ODOO_API_KEY,
    ODOO_DB,
    ODOO_PASSWORD,
    ODOO_SYNC_TENANT_ID,
    ODOO_URL,
    ODOO_USER,
    SAHOOL_AGENT_TOKEN,
    SAHOOL_API_URL,
    SAHOOL_DB_URL,
    SYNC_INTERVAL_SEC,
    WEBHOOK_SECRET,
    OdooClient,
    _run_migrations,
    _selected_erp_provider,
    get_active_erp_provider,
    get_last_sync,
    get_odoo,
    get_pool,
    log_sync_record,
    periodic_sync,
    set_last_sync,
    sync_field_costs_to_odoo,
    sync_procurement_orders_to_odoo,
    sync_products,
    sync_purchase_order_inbound,
    sync_suppliers,
    sync_warehouses,
)


# ══════════════════════════════════════════════════════════════
# Lifespan
# ══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    if SAHOOL_DB_URL:
        _erp_runtime._pool = await asyncpg.create_pool(SAHOOL_DB_URL, min_size=1, max_size=5)
        logger.info("DB pool ready")
        # FINDING-001: ارفض الإقلاع إن تجاوز دور الاتّصال RLS (fail-closed افتراضيّاً).
        from shared.db_role_guard import assert_db_role_rls_safe

        await assert_db_role_rls_safe(_erp_runtime._pool, service="erp-bridge")
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
    if _erp_runtime._odoo:
        await _erp_runtime._odoo.close()
    if _erp_runtime._pool:
        await _erp_runtime._pool.close()


# C-08 FIX: JWT verification with audience
_JWT_PUBLIC = os.getenv("JWT_PUBLIC_KEY", "")
_JWT_SECRET = _JWT_PUBLIC if _JWT_PUBLIC else os.getenv("JWT_SECRET", "")
_JWT_ALG = "RS256" if _JWT_PUBLIC else "HS256"
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}

# تحصين الإنتاج (fail-closed، تماثُل مع auth/المنصّة): RS256 إلزاميّ — HS256 سرّ متماثل
# مشترَك لا يُنهي shared trust domain (أيّ خدمة تحمله تُزوّر توكناً). في الإنتاج بلا
# JWT_PUBLIC_KEY نرفض الإقلاع ما لم يُعطَّل صراحةً (مهرب ترحيل SAHOOL_ALLOW_HS256_IN_PROD=1).
if (
    not os.getenv("JWT_PUBLIC_KEY", "").strip()
    and os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"
    and os.getenv("SAHOOL_ALLOW_HS256_IN_PROD", "").strip().lower()
    not in {"1", "true", "yes", "on"}
):
    raise RuntimeError(
        "RS256 مطلوب في الإنتاج: اضبط JWT_PUBLIC_KEY (HS256 لا يُنهي shared trust domain). "
        "للترحيل المؤقّت فقط: SAHOOL_ALLOW_HS256_IN_PROD=1."
    )


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


app = FastAPI(title="SAHOOL ERP Bridge", version="9.1.0", lifespan=lifespan)


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
# تسجيل الراوترات المفكَّكة (نمط تفكيك raster/auth — محفوظ السلوك)
# يُستدعى في نهاية الملفّ بعد تعريف app وكلّ المساعِدات/النماذج/مزوّد ERP كي
# تُحلّ وحدات routers/ رموزها عبر main.X بلا استيراد دائريّ.
# ══════════════════════════════════════════════════════════════
from router_registry import register_routers  # noqa: E402

register_routers(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
