"""Agent approval/audit stores (V58.2) — swappable, persistent-ready, fail-safe.

v61.5 kept chat approvals/audits in process memory (lost on restart, not multi-worker
safe). This module makes the store a **pluggable backend** so production can persist to
Redis/DB without touching the harness contract:

- default ``memory`` (``InMemory*Store``) — always available, offline.
- ``redis`` (``Redis*Store``) — selected by ``SAHOOL_AGENT_STORE_BACKEND=redis`` +
  ``SAHOOL_AGENT_REDIS_URL``/``REDIS_URL``; **fails safe to memory** when redis is
  unavailable (no lib / unreachable). redis is imported lazily — never at module load.

Approvals are create-once: ``create`` never overwrites an existing id, and the only way a
record changes is ``transition`` (pending -> approved/denied), atomic in both backends. The
audit store is strictly append. Records carry tenant_id/user_id/session_id/tool/params/input_hash/
provider/model/outcome/timestamp for forensic replay.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections import deque
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("ai_agronomist.agent_stores")

_APPROVAL_KEY = "sahool:agent:approval:"
_APPROVAL_PENDING_SET = "sahool:agent:approvals:pending"
_AUDIT_LIST = "sahool:agent:audit"
_DEFAULT_TTL_S = 7 * 24 * 3600  # pending approvals expire after a week if never decided.

# The audit trail is a rolling window: only the newest records are kept (both backends),
# and bulky ``result``/``params`` values are replaced by a digest summary.
_DEFAULT_AUDIT_MAX_RECORDS = 10_000
AUDIT_FIELD_MAX_BYTES = 2048
_AUDIT_BOUNDED_FIELDS = ("result", "params")


def _audit_max_records(explicit: int | None = None) -> int:
    if explicit is not None and explicit > 0:
        return int(explicit)
    try:
        value = int(os.getenv("SAHOOL_AGENT_AUDIT_MAX_RECORDS", ""))
    except ValueError:
        return _DEFAULT_AUDIT_MAX_RECORDS
    return value if value > 0 else _DEFAULT_AUDIT_MAX_RECORDS


def _bounded_value(value: Any) -> Any:
    """``value`` itself when small; otherwise a fixed-size summary with its digest."""
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    except (TypeError, ValueError):  # circular/unsortable keys — keep a marker, not the value
        return {"truncated": True, "unserializable": True}
    if len(raw) <= AUDIT_FIELD_MAX_BYTES:
        return value
    summary: dict[str, Any] = {
        "truncated": True,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    if isinstance(value, dict):
        summary["keys"] = sorted(str(k)[:64] for k in value)[:32]
    return summary


def summarize_audit_record(record: dict[str, Any]) -> dict[str, Any]:
    """Copy of ``record`` with bulky tool ``result``/``params`` reduced to a summary."""
    out = dict(record)
    for key in _AUDIT_BOUNDED_FIELDS:
        if key in out:
            out[key] = _bounded_value(out[key])
    return out


class ApprovalExistsError(Exception):
    """``create`` found a record under this approval id; nothing was written.

    Approvals are create-once: an existing record (pending or decided) is never overwritten, so
    a second create cannot replace another chat's request or re-open a decided one.
    """


def _status_is_pending(record: dict[str, Any]) -> bool:
    return str(record.get("status") or "").startswith("pending")


def _transition_allowed(
    stored: dict[str, Any] | None,
    approval_id: str,
    tenant_id: str,
    expected_status: str,
    new_record: dict[str, Any],
) -> bool:
    """The stored record is the one being decided, in the state the decision was taken from.

    Refused unless: the record exists, the decided record names the same id, the stored status
    is ``expected_status``, and the stored ``tenant_id`` and ``input_hash`` equal both the caller's
    tenant and the decided record's (so a record replaced or re-hashed in between is not decided).
    """
    if not stored or str(new_record.get("id") or "") != approval_id:
        return False
    if str(stored.get("status") or "") != str(expected_status):
        return False
    stored_tenant = str(stored.get("tenant_id") or "")
    if not stored_tenant or stored_tenant != str(tenant_id):
        return False
    if str(new_record.get("tenant_id") or "") != stored_tenant:
        return False
    return stored.get("input_hash") == new_record.get("input_hash")


@runtime_checkable
class ApprovalStore(Protocol):
    def create(self, request: dict[str, Any]) -> None: ...
    def transition(
        self,
        approval_id: str,
        tenant_id: str,
        expected_status: str,
        new_record: dict[str, Any],
    ) -> bool: ...
    def get(self, approval_id: str) -> dict[str, Any] | None: ...
    def list_pending(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class AuditStore(Protocol):
    def append(self, record: dict[str, Any]) -> None: ...
    def recent(self, limit: int = 100) -> list[dict[str, Any]]: ...


# ── in-memory (default) ─────────────────────────────────────────────────────
class InMemoryApprovalStore:
    """Process-local store. One lock serialises create and transition (same rules as Redis)."""

    def __init__(self) -> None:
        self._d: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, request: dict[str, Any]) -> None:
        aid = str(request.get("id") or "")
        if not aid:
            raise ValueError("approval id required")
        with self._lock:
            if aid in self._d:
                raise ApprovalExistsError(aid)
            self._d[aid] = dict(request)

    def transition(
        self,
        approval_id: str,
        tenant_id: str,
        expected_status: str,
        new_record: dict[str, Any],
    ) -> bool:
        aid = str(approval_id or "")
        with self._lock:
            if not _transition_allowed(
                self._d.get(aid), aid, tenant_id, expected_status, new_record
            ):
                return False
            self._d[aid] = dict(new_record)
            return True

    def get(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock:
            v = self._d.get(str(approval_id or ""))
            return dict(v) if v else None

    def list_pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._d.values() if _status_is_pending(v)]


class InMemoryAuditStore:
    def __init__(self, max_records: int | None = None) -> None:
        self._max = _audit_max_records(max_records)
        self._l: deque[dict[str, Any]] = deque(maxlen=self._max)

    def append(self, record: dict[str, Any]) -> None:
        self._l.append(summarize_audit_record(record))

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return [dict(r) for r in list(self._l)[-max(0, limit) :]]


# ── redis (gated scaffold; fail-safe) ───────────────────────────────────────
class RedisApprovalStore:
    """Approvals in Redis: create-once (``SET NX EX``), decisions by WATCH/MULTI/EXEC.

    No Lua: the compose ACL user has no ``EVAL``. A decision keeps the record's remaining TTL
    (``SET ... KEEPTTL XX``, Redis >= 6.0) and moves the id out of the pending set in the same
    ``MULTI``; a concurrent write to the record between ``WATCH`` and ``EXEC`` aborts it.
    """

    def __init__(self, client: Any, ttl_s: int = _DEFAULT_TTL_S) -> None:
        self._c = client
        self._ttl = ttl_s

    def create(self, request: dict[str, Any]) -> None:
        aid = str(request.get("id") or "")
        if not aid:
            raise ValueError("approval id required")
        payload = json.dumps(request, ensure_ascii=False)
        if not self._c.set(_APPROVAL_KEY + aid, payload, nx=True, ex=self._ttl):
            raise ApprovalExistsError(aid)
        if _status_is_pending(request):
            self._c.sadd(_APPROVAL_PENDING_SET, aid)

    def transition(
        self,
        approval_id: str,
        tenant_id: str,
        expected_status: str,
        new_record: dict[str, Any],
    ) -> bool:
        """``True`` only if this call moved the record; ``False`` on a lost race or a mismatch.

        Redis errors (connection, NOPERM) propagate: the caller cannot tell whether it decided.
        """
        aid = str(approval_id or "")
        key = _APPROVAL_KEY + aid
        payload = json.dumps(new_record, ensure_ascii=False)
        with self._c.pipeline(transaction=True) as pipe:
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                stored = json.loads(raw) if raw else None
                if not _transition_allowed(stored, aid, tenant_id, expected_status, new_record):
                    pipe.unwatch()
                    return False
                pipe.multi()
                # XX: an expired record is not recreated. KEEPTTL: the original expiry stays.
                pipe.set(key, payload, xx=True, keepttl=True)
                if _status_is_pending(new_record):
                    pipe.sadd(_APPROVAL_PENDING_SET, aid)
                else:
                    pipe.srem(_APPROVAL_PENDING_SET, aid)
                replies = pipe.execute()
            except _watch_error_types():
                return False
        return bool(replies and replies[0])

    def get(self, approval_id: str) -> dict[str, Any] | None:
        raw = self._c.get(_APPROVAL_KEY + str(approval_id or ""))
        return json.loads(raw) if raw else None

    def list_pending(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for aid in self._c.smembers(_APPROVAL_PENDING_SET) or []:
            rec = self.get(aid.decode() if isinstance(aid, bytes) else str(aid))
            if rec and _status_is_pending(rec):
                out.append(rec)
        return out


def _watch_error_types() -> tuple[type[BaseException], ...]:
    """``redis.WatchError`` when redis-py is installed (imported lazily, like the client)."""
    try:
        from redis.exceptions import WatchError
    except ImportError:  # pragma: no cover - a Redis store is only built when redis imports
        return (_NoWatchError,)
    return (WatchError,)


class _NoWatchError(Exception):
    """Placeholder that is never raised (redis-py absent)."""


class RedisAuditStore:
    def __init__(self, client: Any, max_records: int | None = None) -> None:
        self._c = client
        self._max = _audit_max_records(max_records)

    def append(self, record: dict[str, Any]) -> None:
        payload = json.dumps(summarize_audit_record(record), ensure_ascii=False, default=str)
        self._c.rpush(_AUDIT_LIST, payload)
        self._c.ltrim(_AUDIT_LIST, -self._max, -1)

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        raw = self._c.lrange(_AUDIT_LIST, -max(0, limit), -1) or []
        return [json.loads(r) for r in raw]


def _production_mode() -> bool:
    return os.getenv("SAHOOL_ENV", os.getenv("ENV", "")).strip().lower() in {
        "prod",
        "production",
    }


def _redis_client_or_none() -> Any | None:
    if os.getenv("SAHOOL_AGENT_STORE_BACKEND", "memory").strip().lower() != "redis":
        return None
    url = os.getenv("SAHOOL_AGENT_REDIS_URL") or os.getenv("REDIS_URL")
    if not url:
        # H3: in production a requested Redis backend that cannot be satisfied must
        # fail closed (raise), so pending approvals/audit are never silently lost on
        # restart. Only outside production is the in-process store still permitted.
        msg = "redis backend requested but no redis URL"
        if _production_mode():
            raise RuntimeError(msg)
        logger.warning("%s — falling back to memory", msg)
        return None
    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001 — خارج الإنتاج: أيّ خلل ⇒ سقوط آمن للذاكرة
        msg = f"redis agent store unavailable ({type(exc).__name__})"
        if _production_mode():
            raise RuntimeError(msg) from exc
        logger.warning("%s — falling back to memory", msg)
        return None


def _log_selected_backend(kind: str, client: Any | None) -> None:
    """One startup line saying which store was chosen, readable from deploy logs.

    A successful Redis connection was silent: only a failure logged, so "connected to Redis"
    and "configured for memory" looked the same in the logs. Logged at WARNING because the
    service configures no logging and uvicorn only configures its own loggers, so an INFO
    line here would be dropped. The Redis URL is a secret and is never logged.
    """
    requested = os.getenv("SAHOOL_AGENT_STORE_BACKEND", "memory").strip().lower() or "memory"
    selected = "redis" if client is not None else "memory"
    logger.warning(
        "agent %s store selected: backend=%s requested=%s production=%s",
        kind,
        selected,
        requested,
        _production_mode(),
    )


def build_approval_store() -> ApprovalStore:
    client = _redis_client_or_none()
    _log_selected_backend("approval", client)
    return RedisApprovalStore(client) if client is not None else InMemoryApprovalStore()


def build_audit_store() -> AuditStore:
    client = _redis_client_or_none()
    _log_selected_backend("audit", client)
    return RedisAuditStore(client) if client is not None else InMemoryAuditStore()


def store_backend_name() -> str:
    return "redis" if _redis_client_or_none() is not None else "memory"
