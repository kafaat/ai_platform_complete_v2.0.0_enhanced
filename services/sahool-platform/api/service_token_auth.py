"""api/service_token_auth.py — حارس التوكن الخدميّ مستقلّ (بلا دورة استيراد)
=========================================================================
نسخة مستقلّة من ``_require_service_token`` لا تستورد من ``api.main`` — كي تستطيع
وحدات الراوتر التي تُستورَد مباشرةً في الاختبارات (مثل phase9-12) أن تفرض المصادقة
على مستوى الراوتر (``APIRouter(dependencies=[Depends(_require_service_token)])``)
دون إطلاق دورة استيراد ``api.main`` (التي تُعيد استيراد الراوتر وهو جزئيّ بعد).

السلوك مطابق لنظيره في ``api.main``: fail-closed، مقارنة بزمن ثابت
(``hmac.compare_digest``) مع ``SAHOOL_AGENT_TOKEN``.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from shared.security.service_tenant_assertion import (
    TenantAssertionError,
    verify_tenant_assertion,
)


def _require_service_token(x_agent_token: str | None = Header(None, alias="X-Agent-Token")) -> None:
    """يحمي النقاط الداخليّة بالتوكن الخدميّ (fail-closed): يُرفض إن غاب السرّ أو اختلف."""
    expected = os.getenv("SAHOOL_AGENT_TOKEN", "")
    if not expected or not hmac.compare_digest(x_agent_token or "", expected):
        raise HTTPException(status_code=403, detail="نقطة داخليّة محميّة بـSAHOOL_AGENT_TOKEN")


# ─── Tenant assertions on service-to-service routes (W0-05, W0-07) ───────────────
# ``SAHOOL_AGENT_TOKEN`` is shared by about twenty services, so a valid token alone used to let
# any of them name any tenant in a query string or body (findings fields-5 / routes-5, scout-1).
# A caller now also proves which tenant it acts for: a short-lived HMAC assertion from
# ``shared.security.service_tenant_assertion`` bound to the caller's name, the tenant, the HTTP
# method, the path and ``X-Request-Id``. The caller must also be in the route's allowlist.
#
# One key per hop, so a holder of one key cannot speak on another hop:
#
# * ``PLATFORM_TENANT_ASSERTION_KEY``: ``/internal/fields/{id}/state`` and
#   ``/internal/events/ai-advice``; callers ``ai_agronomist`` and ``supervisor-agent``.
# * ``EDGE_SYNC_TENANT_ASSERTION_KEY``: ``/v1/edge/sync`` in service mode; caller
#   ``edge-inference``, the only service that holds this key. It is deliberately not
#   ``EDGE_TENANT_ASSERTION_KEY`` (the inbound hop video-processor/platform -> edge): with one
#   key for both hops, any caller of the edge could sign as ``edge-inference`` and write to
#   ``/v1/edge/sync`` directly, and the allowlist below would prove nothing.
#
# Everything fails closed: no key configured is 503, a missing assertion is 401, and a caller
# outside the allowlist, a wrong tenant, an expired or replayed assertion are 403.
# (Kept in this module: the platform's module count is a ratchet.)

MIN_KEY_LENGTH = 32


@dataclass(frozen=True)
class AssertionChannel:
    """One signed channel: its key variables and the callers allowed on it."""

    name: str
    key_env: str
    allowed_env: str
    default_allowed: tuple[str, ...]

    def keys(self) -> dict[str, str]:
        """``<PREFIX>_KEY`` (+ ``_KEY_ID``) and, during rotation, ``<PREFIX>_PREVIOUS_KEY``
        (+ ``_PREVIOUS_KEY_ID``). A key shorter than 32 characters counts as absent."""
        prefix = self.key_env.removesuffix("_KEY")
        keys: dict[str, str] = {}
        current = os.getenv(f"{prefix}_KEY", "")
        if len(current) >= MIN_KEY_LENGTH:
            keys[os.getenv(f"{prefix}_KEY_ID", "current")] = current
        previous = os.getenv(f"{prefix}_PREVIOUS_KEY", "")
        if len(previous) >= MIN_KEY_LENGTH:
            keys[os.getenv(f"{prefix}_PREVIOUS_KEY_ID", "previous")] = previous
        return keys

    def allowed_callers(self) -> frozenset[str]:
        raw = os.getenv(self.allowed_env)
        if raw is None:
            return frozenset(self.default_allowed)
        return frozenset(s.strip() for s in raw.split(",") if s.strip())


PLATFORM_INTERNAL = AssertionChannel(
    name="platform-internal",
    key_env="PLATFORM_TENANT_ASSERTION_KEY",
    allowed_env="PLATFORM_INTERNAL_ALLOWED_CALLERS",
    default_allowed=("ai_agronomist", "supervisor-agent"),
)

EDGE_SYNC = AssertionChannel(
    name="edge-sync",
    key_env="EDGE_SYNC_TENANT_ASSERTION_KEY",
    allowed_env="EDGE_SYNC_ALLOWED_CALLERS",
    default_allowed=("edge-inference",),
)


def _production() -> bool:
    return os.getenv("SAHOOL_ENV", "development").strip().lower() in {"production", "prod"}


def _claim_once(replay_key: str) -> None:
    """Consume the nonce once. Production has no in-process fallback (it would not be shared
    between workers); outside production an unset store only skips replay detection.

    A dedicated URL, not ``REDIS_URL``: the platform's cache user may not SET (redis ACL matrix,
    user ``sahool-platform-assertion``)."""
    redis_url = os.getenv("PLATFORM_TENANT_ASSERTION_REDIS_URL", "")
    if not redis_url:
        if _production():
            raise HTTPException(503, "tenant_assertion_replay_store_unavailable")
        return
    try:
        import redis

        client = redis.Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        first = client.set(replay_key, "1", nx=True, ex=70)
    except Exception as exc:  # noqa: BLE001 — store down ⇒ cannot prove freshness ⇒ closed
        raise HTTPException(503, "tenant_assertion_replay_store_unavailable") from exc
    if not first:
        raise HTTPException(403, "tenant_assertion_replayed")


def verify_request_tenant(
    channel: AssertionChannel,
    *,
    method: str,
    path: str,
    headers: Mapping[str, str],
    tenant_id: str,
    claim_once=_claim_once,
) -> str:
    """Return ``tenant_id`` only when the request carries a valid assertion for it.

    ``tenant_id`` is the tenant the route is about to act for (query, body or header); the
    assertion must name exactly that tenant, the caller in ``X-Service-Name``, and this request.
    """
    keys = channel.keys()
    if not keys:
        raise HTTPException(503, f"{channel.name}_tenant_assertion_unavailable")
    assertion = headers.get("x-tenant-assertion") or ""
    if not assertion:
        raise HTTPException(401, "tenant_assertion_required")
    caller = headers.get("x-service-name") or ""
    if caller not in channel.allowed_callers():
        raise HTTPException(403, "caller_not_allowed")
    if not tenant_id:
        raise HTTPException(403, "tenant_required")
    try:
        claims = verify_tenant_assertion(
            assertion,
            keys,
            caller,
            str(tenant_id),
            expected_method=method,
            expected_path=path,
            expected_request_id=headers.get("x-request-id") or "",
        )
    except TenantAssertionError as exc:
        raise HTTPException(403, f"invalid_tenant_assertion:{exc}") from None
    claim_once(claims.replay_key)
    return str(tenant_id)


def request_path(request: Request) -> str:
    """The path exactly as the caller sent and signed it (still percent-encoded)."""
    raw = request.scope.get("raw_path")
    if isinstance(raw, (bytes, bytearray)) and raw:
        return bytes(raw).decode("latin-1")
    return request.url.path


def verify_channel_tenant(channel: AssertionChannel, request: Request, tenant_id: str) -> str:
    return verify_request_tenant(
        channel,
        method=request.method,
        path=request_path(request),
        headers=request.headers,
        tenant_id=tenant_id,
    )


def verify_platform_internal_tenant(request: Request, tenant_id: str) -> str:
    """The check for ``/internal/fields/{id}/state`` and ``/internal/events/ai-advice``."""
    return verify_channel_tenant(PLATFORM_INTERNAL, request, tenant_id)
