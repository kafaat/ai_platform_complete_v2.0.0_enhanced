"""
SAHOOL v9.1 — mcp_servers/shared/oauth_middleware.py (FULLY REWRITTEN)
FIX: FastAPI dependency-based OAuth 2.1 middleware with proper JWT validation
"""

from __future__ import annotations

import os
import re

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ توكن sahool الداخليّ (تدقيق B).
# هذا الوسيط يتحقّق من توكن sahool الداخليّ (نفس JWT_SECRET/HS256/aud=sahool)،
# لا من توكن OAuth خارجيّ من مُصدِر مستقلّ، لذا فرض المُصدِر هنا آمن.
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}

security = HTTPBearer(auto_error=False)


def _validate_tenant_id(tenant_id: str) -> str:
    if not tenant_id or not _TENANT_RE.match(tenant_id):
        raise ValueError(f"Invalid tenant_id: {tenant_id!r}")
    return tenant_id


async def set_tenant_context(conn, tenant_id: str) -> None:
    safe = _validate_tenant_id(tenant_id)
    await conn.execute("SELECT set_config('app.current_tenant', $1, true)", safe)


async def clear_tenant_context(conn) -> None:
    await conn.execute("SELECT set_config('app.current_tenant', '', true)")


def require_scope(required_scope: str):
    """FastAPI dependency factory for MCP scope enforcement."""

    async def _check(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
        if not credentials:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
        secret = os.getenv("JWT_SECRET", "")
        if len(secret) < 32:  # يفشل مغلقاً: لا سرّ ضعيف/قصير (تزوير توكنات)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "JWT_SECRET not configured or too weak (min 32 chars)",
            )
        try:
            payload = jwt.decode(
                credentials.credentials, secret, algorithms=["HS256"], audience="sahool"
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from e
        # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
        if payload.get("iss") not in _ALLOWED_ISS:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token issuer")
        scopes = payload.get("scope", "").split()
        if required_scope not in scopes and "admin" not in scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Scope '{required_scope}' required")
        # tenant_id إلزاميّ من التوكن — لا fallback إلى "default" (عزل مستأجِر).
        tid = payload.get("tenant_id")
        if not tid:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing tenant_id")
        try:
            _validate_tenant_id(tid)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid tenant_id") from e
        return payload

    return _check
