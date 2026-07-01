"""Agent approval/audit stores (V58.2) — swappable, persistent-ready, fail-safe.

v61.5 kept chat approvals/audits in process memory (lost on restart, not multi-worker
safe). This module makes the store a **pluggable backend** so production can persist to
Redis/DB without touching the harness contract:

- default ``memory`` (``InMemory*Store``) — always available, offline.
- ``redis`` (``Redis*Store``) — selected by ``SAHOOL_AGENT_STORE_BACKEND=redis`` +
  ``SAHOOL_AGENT_REDIS_URL``/``REDIS_URL``; **fails safe to memory** when redis is
  unavailable (no lib / unreachable). redis is imported lazily — never at module load.

Approvals are append-only in spirit: a decision updates status but the audit store is
strictly append. Records carry tenant_id/user_id/session_id/tool/params/input_hash/
provider/model/outcome/timestamp for forensic replay.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("ai_agronomist.agent_stores")

_APPROVAL_KEY = "sahool:agent:approval:"
_APPROVAL_PENDING_SET = "sahool:agent:approvals:pending"
_AUDIT_LIST = "sahool:agent:audit"
_DEFAULT_TTL_S = 7 * 24 * 3600  # pending approvals expire after a week if never decided.


@runtime_checkable
class ApprovalStore(Protocol):
    def save(self, request: dict[str, Any]) -> None: ...
    def get(self, approval_id: str) -> dict[str, Any] | None: ...
    def list_pending(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class AuditStore(Protocol):
    def append(self, record: dict[str, Any]) -> None: ...
    def recent(self, limit: int = 100) -> list[dict[str, Any]]: ...


# ── in-memory (default) ─────────────────────────────────────────────────────
class InMemoryApprovalStore:
    def __init__(self) -> None:
        self._d: dict[str, dict[str, Any]] = {}

    def save(self, request: dict[str, Any]) -> None:
        aid = str(request.get("id") or "")
        if aid:
            self._d[aid] = dict(request)

    def get(self, approval_id: str) -> dict[str, Any] | None:
        v = self._d.get(str(approval_id or ""))
        return dict(v) if v else None

    def list_pending(self) -> list[dict[str, Any]]:
        return [
            dict(v) for v in self._d.values() if str(v.get("status") or "").startswith("pending")
        ]


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._l: list[dict[str, Any]] = []

    def append(self, record: dict[str, Any]) -> None:
        self._l.append(dict(record))

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return [dict(r) for r in self._l[-max(0, limit) :]]


# ── redis (gated scaffold; fail-safe) ───────────────────────────────────────
class RedisApprovalStore:
    def __init__(self, client: Any, ttl_s: int = _DEFAULT_TTL_S) -> None:
        self._c = client
        self._ttl = ttl_s

    def save(self, request: dict[str, Any]) -> None:
        aid = str(request.get("id") or "")
        if not aid:
            return
        self._c.set(_APPROVAL_KEY + aid, json.dumps(request, ensure_ascii=False), ex=self._ttl)
        if str(request.get("status") or "").startswith("pending"):
            self._c.sadd(_APPROVAL_PENDING_SET, aid)
        else:
            self._c.srem(_APPROVAL_PENDING_SET, aid)

    def get(self, approval_id: str) -> dict[str, Any] | None:
        raw = self._c.get(_APPROVAL_KEY + str(approval_id or ""))
        return json.loads(raw) if raw else None

    def list_pending(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for aid in self._c.smembers(_APPROVAL_PENDING_SET) or []:
            rec = self.get(aid.decode() if isinstance(aid, bytes) else str(aid))
            if rec:
                out.append(rec)
        return out


class RedisAuditStore:
    def __init__(self, client: Any) -> None:
        self._c = client

    def append(self, record: dict[str, Any]) -> None:
        self._c.rpush(_AUDIT_LIST, json.dumps(record, ensure_ascii=False))

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        raw = self._c.lrange(_AUDIT_LIST, -max(0, limit), -1) or []
        return [json.loads(r) for r in raw]


def _redis_client_or_none() -> Any | None:
    if os.getenv("SAHOOL_AGENT_STORE_BACKEND", "memory").strip().lower() != "redis":
        return None
    url = os.getenv("SAHOOL_AGENT_REDIS_URL") or os.getenv("REDIS_URL")
    if not url:
        logger.warning("redis backend requested but no redis URL — falling back to memory")
        return None
    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001 — أيّ خلل ⇒ سقوط آمن للذاكرة
        logger.warning(
            "redis agent store unavailable (%s) — falling back to memory", type(exc).__name__
        )
        return None


def build_approval_store() -> ApprovalStore:
    client = _redis_client_or_none()
    return RedisApprovalStore(client) if client is not None else InMemoryApprovalStore()


def build_audit_store() -> AuditStore:
    client = _redis_client_or_none()
    return RedisAuditStore(client) if client is not None else InMemoryAuditStore()


def store_backend_name() -> str:
    return "redis" if _redis_client_or_none() is not None else "memory"
