"""
SAHOOL v9.1 — mcp_servers/shared/oauth_middleware.py (FULLY REWRITTEN)
FIX: FastAPI dependency-based OAuth 2.1 middleware with proper JWT validation
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import asynccontextmanager

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from shared.security.access_tokens import (
    AccessTokenConfigurationError,
    InvalidAccessTokenError,
    decode_access_token,
)

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
# هذا الوسيط يتحقّق من توكن sahool الداخليّ (aud=sahool، مُصدِرٌ داخليّ) لا من توكن OAuth
# خارجيّ، لذا يُفرَض المُصدِر — في ``shared.security.access_tokens`` مع الجمهور والمطالبات
# المطلوبة (JWT-DECODE-OUTSIDE-SHARED-SECURITY-01).

security = HTTPBearer(auto_error=False)


def _validate_tenant_id(tenant_id: str) -> str:
    if not isinstance(tenant_id, str) or not _TENANT_RE.fullmatch(tenant_id):
        raise ValueError(f"Invalid tenant_id: {tenant_id!r}")
    return tenant_id


@asynccontextmanager
async def tenant_transaction(conn, tenant_id: str):
    """معاملةٌ مُنطّقةٌ بالمستأجِر — المُساعِدُ يملكها فلا يُستعمَل خارجها.

    حلّت محلّ ``set_tenant_context``/``clear_tenant_context``، وكانتا تنفّذان
    ``set_config(…, true)`` على الاتّصال كما هو. **مقيسٌ على PG16 بدورٍ مقيَّد:** خارج
    معاملةٍ صريحة العبارةُ معاملةُ نفسِها، فيُعيد ``set_config`` القيمةَ ثمّ تقرأ العبارةُ
    التالية ``''`` — ضبطٌ بلا أثر، وسياسةُ ``NULLIF`` تُعيد صفراً بلا استثناء. و«المسح»
    بضبط ``''`` محلّيّاً لا يمسح شيئاً يبقى بعد المعاملة أصلاً، وداخلها يفتح سياساتِ
    «فاشلٍ-مفتوحٍ عند الغياب» (``audit_log`` · ``invitations`` · ``break_glass_grants``)
    على كلّ المستأجرين. ولم يكن لأيٍّ منهما مُستدعٍ: فخٌّ كامن أُغلق قبل أن يُستعمَل.
    """
    safe = _validate_tenant_id(tenant_id)
    async with conn.transaction():
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", safe)
        yield conn


def verify_sahool_bearer(token: str) -> dict:
    """المفتاحُ من البيئة (RS256 إن وُجد ``JWT_PUBLIC_KEY``، وإلّا HS256) ثمّ الفكُّ المشترك.

    تستعمله نقاطُ MCP (``_authenticate_token``) ومساراتُ REST في market-mcp معاً — كانت
    الأخيرةُ تفكّ بـHS256 و``JWT_SECRET`` وحدهما فترفض كلَّ توكن RS256 صادرٍ من auth.
    """
    secret = os.getenv("JWT_SECRET", "")
    public_key = os.getenv("JWT_PUBLIC_KEY", "").strip()
    production = os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"
    allow_hs256 = os.getenv("SAHOOL_ALLOW_HS256_IN_PROD", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not public_key and production and not allow_hs256:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "RS256 verification required")
    if not public_key and len(secret) < 32:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "JWT_SECRET not configured or too weak (min 32 chars)",
        )
    try:
        return decode_access_token(
            token, public_key or secret, "RS256" if public_key else "HS256", backend="pyjwt"
        )
    except AccessTokenConfigurationError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "JWT not configured") from e
    except InvalidAccessTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from e


def _authenticate_token(token: str, required_scope: str) -> dict:
    """Validate one bearer token; shared by dependency and pre-body middleware."""
    payload = verify_sahool_bearer(token)
    scope = payload.get("scope", "")
    if not isinstance(scope, str):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid token scope")
    scopes = scope.split()
    if required_scope not in scopes and "admin" not in scopes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Scope '{required_scope}' required")
    tid = payload.get("tenant_id")
    if not tid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing tenant_id")
    try:
        _validate_tenant_id(tid)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid tenant_id") from e
    return payload


def idempotency_key(user: dict, request_id: str | None, name: str, arguments: dict) -> str | None:
    """A caller's key cannot select another tenant/user/tool/input's result."""
    if not request_id:
        return None
    identity = [user["tenant_id"], user.get("sub"), request_id, name, arguments]
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _bearer_from_header(value: str | None) -> str:
    if not value:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    scheme, sep, token = value.partition(" ")
    if not sep or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return token.strip()


class MCPPreAuthMiddleware(BaseHTTPMiddleware):
    """Authenticate selected MCP routes before Starlette/FastAPI reads the body."""

    def __init__(self, app, *, protected_paths: dict[str, str]):
        super().__init__(app)
        self._protected_paths = dict(protected_paths)

    async def dispatch(self, request: Request, call_next):
        required_scope = self._protected_paths.get(request.url.path)
        if required_scope is None:
            return await call_next(request)
        try:
            token = _bearer_from_header(request.headers.get("authorization"))
            _authenticate_token(token, required_scope)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
        return await call_next(request)


def require_scope(required_scope: str):
    """FastAPI dependency factory for MCP scope enforcement."""

    async def _check(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
        if not credentials:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
        return _authenticate_token(credentials.credentials, required_scope)

    return _check
