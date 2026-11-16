"""Push of published raster assets to the canonical observation store (W1-11).

Owner decision of 2026-11-16: indicators-service owns the append-only ``canonical_observations``
table (migrations/v286) and raster-service pushes each published asset to it over HTTP
(``POST /internal/v1/observations``), not NATS. raster-service never writes that table.

A push that fails is not lost: the publish path first writes the payload to
``raster_observation_outbox`` (owned here, v286), then calls indicators-service and records the
outcome on that row. A row still ``pending`` is re-sent by the cache invalidation worker
(``drain_once``) with a capped exponential backoff, for as long as it takes.

When the outbox itself cannot be written and the one push does not settle the observation either,
the payload is ``unqueued``: it is held in this process (bounded, ``UNQUEUED_LIMIT``) and every
later ``publish`` first writes the held payloads to the outbox, from where the worker drains them.
Each such payload is counted (``raster_batch_observability``, exported on ``/metrics`` as
``sahool_raster_batch_observation_outbox_unqueued_total``; ``..._requeued_total`` when it reached
the outbox, ``..._unqueued_dropped_total`` when the bound drops it) and logged. A held payload
is durable only once it is in the outbox: a process restart before that loses it, which shows as
``unqueued_total`` above ``requeued_total + unqueued_dropped_total``.

Outcomes: 200/201 ``delivered`` · 409 ``conflict`` (the store holds the same observation id with
other content; terminal, surfaced in the log and on the row) · 400/403/422 ``rejected``
(terminal: the payload or the tenant assertion is wrong, a retry cannot fix it) · anything else,
including a network error or an unconfigured URL/token, stays ``pending``.

The push never changes whether the asset counts as published; it runs after publication.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("raster-service.observation_outbox")

SCHEMA_VERSION = "sahool.published_observation/1"
INGEST_PATH = "/internal/v1/observations"
PUSH_TIMEOUT_S = float(os.getenv("OBSERVATION_PUSH_TIMEOUT_SECONDS", "5"))
BACKOFF_BASE_S = float(os.getenv("OBSERVATION_PUSH_BACKOFF_SECONDS", "30"))
BACKOFF_MAX_S = float(os.getenv("OBSERVATION_PUSH_BACKOFF_MAX_SECONDS", "3600"))
#: A claimed row is invisible to another drain for this long (a dead worker's claim expires).
CLAIM_LEASE_S = float(os.getenv("OBSERVATION_PUSH_LEASE_SECONDS", "120"))
#: One drain stops sending after this long (the worker's heartbeat max-age is 120 s); the rows it
#: claimed and did not send are released for the next cycle at once.
DRAIN_BUDGET_S = float(os.getenv("OBSERVATION_PUSH_DRAIN_BUDGET_SECONDS", "30"))

DELIVERED = "delivered"
CONFLICT = "conflict"
REJECTED = "rejected"
PENDING = "pending"
#: The push did not settle and the outbox could not be written: held here for the next publish.
UNQUEUED = "unqueued"
UNQUEUED_LIMIT = int(os.getenv("OBSERVATION_UNQUEUED_LIMIT", "1000"))
#: Payloads with no outbox row yet, by content digest (insertion order: oldest first).
_UNQUEUED: dict[str, dict[str, Any]] = {}
_TERMINAL_CLIENT_ERRORS = {400, 403, 422}


def _indicators_url() -> str:
    return os.getenv("INDICATORS_SERVICE_URL", "http://sahool-indicators-service:8000").rstrip("/")


def _service_token() -> str:
    return os.getenv("SAHOOL_AGENT_TOKEN", "")


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _ratio(value: Any) -> float | None:
    number = _finite(value)
    return number if number is not None and 0 <= number <= 1 else None


def _acquired_iso(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) == 10:
        raw += "T00:00:00+00:00"
    elif raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def build_payload(
    *,
    tenant_id: str | None,
    field_id: str | None,
    indicator: str,
    scene_id: str | None,
    capture_datetime: Any,
    stats: dict[str, Any],
    quality: dict[str, Any],
    algorithm_version: str | None,
    qa_mask_version: str | None,
    product_identity_key: str | None,
    geometry_revision: int | None,
    data_available_at: Any,
    processing_job_id: str | None,
    cog_uri: str | None,
) -> dict[str, Any] | None:
    """The ``PublishedObservationV1`` body for one published asset, or ``None`` when the asset
    cannot be a canonical observation (no tenant, scene, acquisition time or finite mean)."""
    acquired = _acquired_iso(capture_datetime)
    mean = _finite(stats.get("mean"))
    if not (tenant_id and field_id and scene_id and str(scene_id).strip() and acquired):
        return None
    if mean is None:
        return None
    valid_ratio = _ratio(quality.get("valid_pixel_ratio"))
    cloud = _finite(stats.get("cloud_pct"))
    revision = geometry_revision if isinstance(geometry_revision, int) else None
    return {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": str(tenant_id),
        "field_id": str(field_id),
        "indicator": str(indicator).strip().lower(),
        "scene_id": str(scene_id),
        "acquired_at": acquired,
        "stats": {
            key: value
            for key in ("mean", "median", "p10", "p90", "std", "min", "max")
            if (value := _finite(stats.get(key))) is not None
        },
        "valid_pixel_ratio": valid_ratio,
        "coverage_ratio": _ratio(quality.get("coverage_ratio")),
        "cloud_pct": cloud if cloud is not None and 0 <= cloud <= 100 else None,
        "quality_score": _finite(stats.get("quality_score", stats.get("confidence"))),
        # The raster indicator envelope's own rule (raster_indicator_product): a measured,
        # positive valid-pixel ratio.
        "quality_gate_passed": valid_ratio is not None and valid_ratio > 0,
        "index_quality_flags": [str(f) for f in (quality.get("index_quality_flags") or [])],
        "algorithm_version": algorithm_version,
        "qa_mask_version": qa_mask_version,
        "product_identity_key": product_identity_key,
        "geometry_revision": revision,
        "data_available_at": _acquired_iso(data_available_at),
        "processing_job_id": processing_job_id,
        "cog_uri": cog_uri,
    }


def payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class PushOutcome:
    status: str
    status_code: int | None = None
    error: str | None = None


async def push(payload: dict[str, Any], *, transport: Any = None) -> PushOutcome:
    """POST one payload to indicators-service; classify the answer. Never raises."""
    token = _service_token()
    if not token:
        return PushOutcome(PENDING, None, "SAHOOL_AGENT_TOKEN not configured")
    try:
        import httpx

        kwargs: dict[str, Any] = {"timeout": PUSH_TIMEOUT_S, "trust_env": False}
        if transport is not None:
            kwargs["transport"] = transport
        async with httpx.AsyncClient(**kwargs) as client:
            response = await client.post(
                f"{_indicators_url()}{INGEST_PATH}",
                json=payload,
                headers={"X-Agent-Token": token, "X-Tenant-Id": str(payload["tenant_id"])},
            )
    except Exception as exc:  # noqa: BLE001 — a transport failure is retried, not raised
        return PushOutcome(PENDING, None, f"transport: {type(exc).__name__}")
    code = response.status_code
    if code in (200, 201):
        return PushOutcome(DELIVERED, code)
    if code == 409:
        return PushOutcome(CONFLICT, code, "observation id stored with other content")
    if code in _TERMINAL_CLIENT_ERRORS:
        return PushOutcome(REJECTED, code, response.text[:500])
    return PushOutcome(PENDING, code, response.text[:500])


def backoff_seconds(attempts: int) -> float:
    return min(BACKOFF_BASE_S * (2 ** max(attempts - 1, 0)), BACKOFF_MAX_S)


_ENQUEUE = """
    INSERT INTO raster_observation_outbox (
        tenant_id, field_id, indicator_code, product_identity_key, payload, payload_sha256
    ) VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6)
    ON CONFLICT ON CONSTRAINT raster_observation_outbox_once DO NOTHING
    RETURNING id, status
"""
_EXISTING = """
    SELECT id, status FROM raster_observation_outbox
    WHERE tenant_id = $1::uuid AND product_identity_key = $2 AND payload_sha256 = $3
"""
_RECORD = """
    UPDATE raster_observation_outbox SET
        status = $3,
        attempts = attempts + 1,
        last_status_code = $4,
        last_error = $5,
        delivered_at = CASE WHEN $3 = 'delivered' THEN now() ELSE delivered_at END,
        next_attempt_at = CASE WHEN $3 = 'pending'
                               THEN now() + make_interval(secs => $6) ELSE next_attempt_at END
    WHERE id = $1 AND tenant_id = $2::uuid AND status = 'pending'
"""


async def _record(conn: Any, tenant_id: str, row_id: int, attempts: int, out: PushOutcome) -> None:
    async with conn.transaction():
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_id)
        await conn.execute(
            _RECORD,
            row_id,
            tenant_id,
            out.status,
            out.status_code,
            out.error,
            backoff_seconds(attempts + 1),
        )


def _log_outcome(payload: dict[str, Any], out: PushOutcome, row_id: int | None) -> None:
    where = (
        f"field_id={payload.get('field_id')} index={payload.get('indicator')} outbox_id={row_id}"
    )
    if out.status == DELIVERED:
        logger.info("canonical observation delivered %s", where)
    elif out.status == PENDING:
        logger.warning("canonical observation push pending retry %s: %s", where, out.error)
    else:
        logger.error("canonical observation push %s %s: %s", out.status, where, out.error)


async def enqueue(payload: dict[str, Any]) -> tuple[int, str] | None:
    """Write the outbox row for this exact content (once); return ``(id, status)``.

    ``None`` when the outbox cannot be written (no database, or the write failed)."""
    import db_persist

    tenant = str(payload["tenant_id"])
    digest = payload_sha256(payload)
    identity = payload.get("product_identity_key") or digest
    conn = await db_persist._connect()
    if conn is None:
        return None
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            row = await conn.fetchrow(
                _ENQUEUE,
                tenant,
                payload["field_id"],
                payload["indicator"],
                identity,
                json.dumps(payload, sort_keys=True, allow_nan=False),
                digest,
            )
            if row is None:
                row = await conn.fetchrow(_EXISTING, tenant, identity, digest)
        return (int(row["id"]), str(row["status"])) if row is not None else None
    except Exception as exc:  # noqa: BLE001 — the caller holds the payload as unqueued
        logger.error("raster_observation_outbox write failed: %s", type(exc).__name__)
        return None
    finally:
        await conn.close()


async def record_outcome(tenant_id: str, row_id: int, attempts: int, out: PushOutcome) -> bool:
    """Record one push outcome on its outbox row; ``False`` when it could not be recorded."""
    import db_persist

    conn = await db_persist._connect()
    if conn is None:
        return False
    try:
        await _record(conn, tenant_id, row_id, attempts, out)
        return True
    except Exception as exc:  # noqa: BLE001 — the row stays pending and the worker re-sends
        logger.warning("raster_observation_outbox outcome not recorded: %s", type(exc).__name__)
        return False
    finally:
        await conn.close()


def _count(name: str, amount: int = 1) -> None:
    try:
        import raster_batch_observability

        raster_batch_observability.inc(name, amount)
    except Exception:  # noqa: BLE001 — a counter never fails the publish path
        pass


def unqueued_count() -> int:
    """How many payloads are held with no outbox row (the retryable ``unqueued`` state)."""
    return len(_UNQUEUED)


def _hold(payload: dict[str, Any]) -> None:
    digest = payload_sha256(payload)
    if digest not in _UNQUEUED:
        _count("observation_outbox_unqueued_total")
    _UNQUEUED[digest] = payload
    while len(_UNQUEUED) > max(UNQUEUED_LIMIT, 1):
        dropped = _UNQUEUED.pop(next(iter(_UNQUEUED)))
        _count("observation_outbox_unqueued_dropped_total")
        logger.error(
            "canonical observation dropped from the unqueued hold (limit %s) field_id=%s index=%s",
            UNQUEUED_LIMIT,
            dropped.get("field_id"),
            dropped.get("indicator"),
        )
    logger.error(
        "canonical observation unqueued (outbox unavailable, push not settled) field_id=%s "
        "index=%s held=%s",
        payload.get("field_id"),
        payload.get("indicator"),
        len(_UNQUEUED),
    )


async def requeue_unqueued() -> int:
    """Write the held payloads to the outbox (oldest first); stop at the first failure.

    Returns how many reached the outbox; the worker's drain sends them from there."""
    moved = 0
    for digest in list(_UNQUEUED):
        if await enqueue(_UNQUEUED[digest]) is None:
            break
        _UNQUEUED.pop(digest, None)
        moved += 1
    if moved:
        _count("observation_outbox_requeued_total", moved)
        logger.info("canonical observation outbox: %s held payloads queued", moved)
    return moved


async def publish(payload: dict[str, Any], *, transport: Any = None) -> str:
    """Write the outbox row, push once, record the outcome. Returns the row status. Never raises.

    If the outbox cannot be written the push is still attempted. A push that settles the
    observation (delivered, conflict, rejected) needs no retry. Otherwise the payload is held as
    ``unqueued`` (counted, see the module doc) and the next publish writes it to the outbox.
    """
    if _UNQUEUED:
        await requeue_unqueued()
    queued = await enqueue(payload)
    if queued is not None and queued[1] != PENDING:
        return queued[1]  # this exact content was already delivered or settled
    out = await push(payload, transport=transport)
    _log_outcome(payload, out, queued[0] if queued else None)
    if queued is None:
        if out.status != PENDING:
            return out.status
        _hold(payload)
        return UNQUEUED
    if not await record_outcome(str(payload["tenant_id"]), queued[0], 0, out):
        return PENDING
    return out.status


_CLAIM = """
    SELECT id, tenant_id::text AS tenant_id, payload, attempts
    FROM raster_observation_outbox
    WHERE status = 'pending' AND next_attempt_at <= now()
    ORDER BY next_attempt_at
    LIMIT $1
    FOR UPDATE SKIP LOCKED
"""


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value)


def within_budget(started: float, budget_s: float, *, clock: Any = time.monotonic) -> bool:
    return clock() - started < budget_s


async def drain_once(
    pool: Any,
    *,
    batch_size: int = 20,
    transport: Any = None,
    budget_s: float | None = None,
    clock: Any = time.monotonic,
) -> int:
    """Re-send pending outbox rows whose time has come. Returns how many were delivered.

    Runs in the cache invalidation worker on its jobs-role pool. The claim moves
    ``next_attempt_at`` forward by a lease inside the claiming transaction, so two workers never
    send the same row at once and a dead worker's claim expires on its own. Sending stops once
    ``budget_s`` (``DRAIN_BUDGET_S``) has passed; the claimed rows not sent are released.
    """
    budget = DRAIN_BUDGET_S if budget_s is None else budget_s
    started = clock()
    if not _service_token():
        return 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(_CLAIM, batch_size)
            if rows:
                await conn.execute(
                    "UPDATE raster_observation_outbox "
                    "SET next_attempt_at = now() + make_interval(secs => $2) "
                    "WHERE id = ANY($1::bigint[])",
                    [r["id"] for r in rows],
                    CLAIM_LEASE_S,
                )
        delivered = 0
        unsent: list[int] = []
        for row in rows:
            if not within_budget(started, budget, clock=clock):
                unsent.append(int(row["id"]))
                continue
            payload = _payload(row["payload"])
            out = await push(payload, transport=transport)
            _log_outcome(payload, out, row["id"])
            await _record(conn, row["tenant_id"], int(row["id"]), int(row["attempts"]), out)
            delivered += out.status == DELIVERED
        if unsent:
            await conn.execute(
                "UPDATE raster_observation_outbox SET next_attempt_at = now() "
                "WHERE id = ANY($1::bigint[]) AND status = 'pending'",
                unsent,
            )
            logger.warning(
                "observation outbox drain budget %.0fs spent: %s claimed rows released unsent",
                budget,
                len(unsent),
            )
        return delivered
