"""SEASON-RECORD-ENTRY-01 slice 3b — auth edge-sign subrequest for the season-accept gate.

The nginx gateway calls this via ``auth_request`` on the season-**accept** path only. We:
  1. verify the JWT (``main.get_current_user``) — the single source of caller identity,
  2. derive season-reviewer authority from the single RBAC role — **{owner, expert} only**,
     admin deliberately excluded (agronomic ≠ operational; see ``SEASON_REVIEWER_SOURCE_ROLES``),
  3. sign a **destination-bound** HMAC over the CANONICAL method/path **nginx declares**
     (``X-Canonical-Method`` / ``X-Canonical-Path`` = the internal path after rewrite) plus the
     empty-body hash (accept carries no body),
  4. return the signed identity headers; nginx lifts them with ``auth_request_set`` and forwards
     them upstream to scout-ingest, which re-verifies against ITS OWN received method/path/body.

Why trusting ``X-Canonical-*`` here is safe (owner condition ③): nginx **strips** any client-sent
``X-Canonical-*`` before this subrequest and sets them itself — so the value is nginx-generated,
never client-controlled. The consuming service still computes method/path from its own request
(condition ①); this endpoint only signs what the trusted gateway declares.

Fail-closed: missing canonical destination, unset key, or a role without reviewer authority all
yield a non-2xx (nginx ``auth_request`` treats that as deny) — no silent signature.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated

import main  # الخدمة تُشغَّل من جذرها؛ نمط routers.* ⇒ import main (register_routers في النهاية)
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from shared.security.trusted_tenant import (
    compute_edge_attestation,
    edge_body_sha256,
    season_reviewer_roles_for,
)

router = APIRouter()


@router.get("/v1/auth/edge-sign")
async def edge_sign(
    response: Response,
    user: Annotated[dict, Depends(main.get_current_user)],
    x_canonical_method: Annotated[str | None, Header(alias="X-Canonical-Method")] = None,
    x_canonical_path: Annotated[str | None, Header(alias="X-Canonical-Path")] = None,
) -> dict:
    """Sign a destination-bound edge attestation for the gateway (accept path). Headers out."""
    # nginx **must** declare the canonical destination; missing ⇒ misconfig ⇒ deny (fail-closed).
    method = (x_canonical_method or "").strip().upper()
    path = (x_canonical_path or "").strip()
    if not method or not path:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "canonical destination required")

    secret = os.getenv("SEASON_EDGE_HMAC_KEY")
    if not secret:
        # مفتاح غير مُهيّأ ⇒ لا توقيع صامت (نفس درس service_token_ok / SEC-3.1) ⇒ deny.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "edge signing not configured")

    uid = str(user.get("sub", "")).strip()
    if not uid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no authenticated user")
    # التفويض المُعلَن: {owner, expert} ⇒ roles تحمل season-reviewer؛ غيرها ⇒ بلا (⇒ 403 عند القبول).
    roles = season_reviewer_roles_for(user.get("role"))
    ts = str(int(datetime.now(UTC).timestamp()))
    body_sha = edge_body_sha256(b"")  # accept بلا جسم — لكن نوقّع الهاش صراحةً لا نتركه ضمنيّاً
    attestation = compute_edge_attestation(uid, roles, method, path, body_sha, ts, secret)

    # nginx يرفعها بـauth_request_set ويمرّرها upstream (لا تُعاد للعميل — الطلب الفرعيّ داخليّ).
    response.headers["X-User-Id"] = uid
    response.headers["X-Roles"] = roles
    response.headers["X-Edge-Timestamp"] = ts
    response.headers["X-Edge-Attestation"] = attestation
    response.headers["X-Tenant-Id"] = str(user.get("tenant_id", "")).strip()
    return {"signed": True}
