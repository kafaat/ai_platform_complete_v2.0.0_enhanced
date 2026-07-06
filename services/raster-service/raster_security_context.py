"""Tenant/security/source helpers for raster-service.

Extracted from main.py in phase 9 to keep main.py as a thin service façade while
preserving the existing private main._* compatibility API used by routers/tests.
"""

from __future__ import annotations

import hmac
import os
from contextvars import ContextVar
from urllib.parse import urlparse

from fastapi import HTTPException

REQ_TENANT: ContextVar[str | None] = ContextVar("req_tenant", default=None)

try:
    from shared.security.tenant_context import resolve_tenant_context as _resolve_tenant_context
except ImportError:  # pragma: no cover - service can still run from its folder in minimal CI

    def _resolve_tenant_context(
        request, tid: str | None = None, tenant_id: str | None = None
    ) -> str | None:
        def _clean(value: str | None) -> str | None:
            if not value:
                return None
            return value.strip() or None

        return _clean(request.headers.get("X-Tenant-Id")) or _clean(tid) or _clean(tenant_id)


def tenant_from_header(value: str | None) -> str | None:
    """Backwards-compatible normalizer used by tests and older call sites."""
    if not value:
        return None
    value = value.strip()
    return value or None


def tenant_from_request(request) -> str | None:
    """Extract the tenant context from trusted gateway header or tile query hints."""
    return _resolve_tenant_context(
        request,
        tid=request.query_params.get("tid"),
        tenant_id=request.query_params.get("tenant_id"),
    )


_field_owner_cache: dict[str, tuple[str | None, float]] = {}
_FIELD_OWNER_TTL_OK = 300.0
_FIELD_OWNER_TTL_MISS = 15.0


async def field_owner(field_id: str) -> str | None:
    """Trusted field owner lookup with short TTL caching."""
    import time as _t

    now = _t.monotonic()
    hit = _field_owner_cache.get(field_id)
    if hit is not None and hit[1] > now:
        return hit[0]
    import db_persist

    owner = await db_persist.field_owner_tenant(field_id)
    ttl = _FIELD_OWNER_TTL_OK if owner else _FIELD_OWNER_TTL_MISS
    _field_owner_cache[field_id] = (owner, now + ttl)
    return owner


async def require_field_tenant(
    field_id: str,
    *,
    hide_existence: bool = False,
    layers: dict[str, dict],
    field_layers: dict[str, list[str]],
    logger,
    owner_lookup=None,
) -> None:
    """Authorize field ownership using DB as source of truth when available."""
    req_tenant = REQ_TENANT.get()
    import db_persist

    try:
        owner = await (owner_lookup or field_owner)(field_id)
    except db_persist.OwnerLookupUnavailable as e:
        raise HTTPException(503, "تعذّر إثبات ملكيّة الحقل — أعد المحاولة لاحقاً") from e

    if owner:
        if not req_tenant or owner != req_tenant:
            raise HTTPException(
                404 if hide_existence else 403,
                "الحقل غير موجود" if hide_existence else "الحقل لا يخصّ مستأجِرك",
            )
        kept: list[str] = []
        for lid in field_layers.get(field_id, []):
            lyr = layers.get(lid)
            cached_owner = lyr.get("tenant_id") if lyr else None
            if cached_owner and cached_owner != req_tenant:
                logger.warning(
                    "pruning stale field layer tenant cache field=%s layer=%s cached=%s request=%s",
                    field_id,
                    lid,
                    cached_owner,
                    req_tenant,
                )
                continue
            kept.append(lid)
        if kept != field_layers.get(field_id, []):
            field_layers[field_id] = kept
        return

    # DB-less/field not known: fall back to in-memory defense only.
    for lid in field_layers.get(field_id, []):
        lyr = layers.get(lid)
        cached_owner = lyr.get("tenant_id") if lyr else None
        if cached_owner and cached_owner != req_tenant:
            raise HTTPException(
                404 if hide_existence else 403,
                "الحقل غير موجود" if hide_existence else "الحقل لا يخصّ مستأجِرك",
            )


def require_layer_tenant(layer_id: str, *, layers: dict[str, dict]) -> None:
    """Fast in-memory authorization for layer ownership."""
    req_tenant = REQ_TENANT.get()
    lyr = layers.get(layer_id)
    owner = lyr.get("tenant_id") if lyr else None
    if owner and owner != req_tenant:
        raise HTTPException(403, "الطبقة لا تخصّ مستأجِرك")


async def require_layer_tenant_authorized(
    layer_id: str, *, layers: dict[str, dict], logger
) -> None:
    """Authorize layer ownership with DB as source of truth when available."""
    req_tenant = REQ_TENANT.get()
    try:
        import db_persist

        db_owner = await db_persist.layer_owner_tenant(layer_id)
    except db_persist.OwnerLookupUnavailable as e:
        raise HTTPException(503, "تعذّر إثبات ملكيّة الطبقة — أعد المحاولة لاحقاً") from e

    if db_owner:
        if not req_tenant:
            raise HTTPException(403, "مستأجر الطلب مطلوب لقراءة الطبقة")
        if db_owner != req_tenant:
            raise HTTPException(403, "الطبقة لا تخصّ مستأجِرك")
        lyr = layers.get(layer_id)
        if lyr and lyr.get("tenant_id") and lyr.get("tenant_id") != req_tenant:
            logger.warning(
                "correcting stale layer tenant cache layer=%s cached=%s db=%s",
                layer_id,
                lyr.get("tenant_id"),
                db_owner,
            )
            lyr["tenant_id"] = db_owner
        return

    require_layer_tenant(layer_id, layers=layers)
    lyr = layers.get(layer_id)
    owner = lyr.get("tenant_id") if lyr else None
    if owner and not req_tenant:
        raise HTTPException(403, "مستأجر الطلب مطلوب لقراءة الطبقة")
    if not owner and not req_tenant:
        raise HTTPException(403, "مستأجر الطلب مطلوب لقراءة الطبقة")


def public_cog_url(cog_url: str | None) -> str | None:
    """Return cog_url only when it is public http(s); never expose internal storage URLs."""
    if not cog_url:
        return None
    low = cog_url.strip().lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        return None
    if any(h in low for h in ("sahool-", "minio", "localhost", "127.0.0.1", ":9000", ".internal")):
        return None
    return cog_url


def safe_raster_source(url: str | None, upload_dir: str, blocked_hosts: set[str]) -> str:
    """Validate a raster source before rasterio.open; blocks path traversal and SSRF."""
    if not url or not isinstance(url, str):
        raise HTTPException(400, "مصدر راستر غير صالح")
    if url.startswith("file://") or url.startswith("/"):
        raw = url[len("file://") :] if url.startswith("file://") else url
        path = os.path.realpath(raw)
        base = os.path.realpath(upload_dir)
        if path != base and not path.startswith(base + os.sep):
            raise HTTPException(400, "مسار ملفّ خارج المجلّد المسموح (traversal مرفوض)")
        return path
    if url.startswith(("http://", "https://")):
        host = (urlparse(url).hostname or "").lower()
        if host in blocked_hosts:
            raise HTTPException(400, "مضيف محجوب (SSRF)")
        return url
    raise HTTPException(400, "مخطّط URL غير مدعوم لمصدر الراستر")


def require_service_token(x_agent_token: str | None, agent_token: str) -> None:
    """Service-to-service authentication for write/storage endpoints."""
    if not agent_token:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الرفع معطّل بأمان")
    if not hmac.compare_digest(x_agent_token or "", agent_token):
        raise HTTPException(401, "توكن خدمة غير صالح")
