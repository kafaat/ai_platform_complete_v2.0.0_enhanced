"""The durable outbox of published raster observations (W1-11).

Owner decision of 2026-11-16 (first form): indicators-service owns the append-only
``canonical_observations`` table (migrations/v286); raster-service never writes it.

Owner decision of 2026-11-16 (second form, this module): the direction is PULL. raster-service
does not call indicators-service. indicators-service already reads raster-service (its
observation and timeline adapters), and a push back from raster made the two services a cycle in
the architecture graph (``scripts/ci/architecture_graph.py``, ``architecture:no_cycles``), which
has no exception list. So:

* the publish path writes each published asset's ``PublishedObservationV1`` payload to
  ``raster_observation_outbox`` (owned here, v286) as soon as the asset is published, once per
  exact content (``raster_observation_outbox_once``);
* indicators-service's drain worker reads the tenant's pending entries over this service's
  internal S2S route (``GET /internal/v1/observation-outbox``, ``pending_entries``), stores each
  one in its own idempotent store, and then acknowledges what it settled
  (``POST /internal/v1/observation-outbox/acknowledgements``, ``acknowledge``);
* an entry stays ``pending`` until it is acknowledged; acknowledgement marks only the entries the
  caller names, at the content it names (``payload_sha256``), and only from ``pending``; nothing
  here deletes an entry. ``delivered`` means stored (created or replayed) in the canonical store;
  ``conflict`` means the store holds the same observation id and revision with other content;
  ``rejected`` means the payload cannot be a canonical observation. The last two are terminal and
  stay visible on the row (``last_error``).

When the outbox itself cannot be written, the payload is ``unqueued``: it is held in this process
(bounded, ``UNQUEUED_LIMIT``) and every later ``publish`` first writes the held payloads to the
outbox. Each such payload is counted (``raster_batch_observability``, exported on ``/metrics`` as
``sahool_raster_batch_observation_outbox_unqueued_total``; ``..._requeued_total`` when it reached
the outbox, ``..._unqueued_dropped_total`` when the bound drops it) and logged. A held payload
is durable only once it is in the outbox: a process restart before that loses it, which shows as
``unqueued_total`` above ``requeued_total + unqueued_dropped_total``.

Queueing never changes whether the asset counts as published; it runs after publication.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("raster-service.observation_outbox")

SCHEMA_VERSION = "sahool.published_observation/1"

DELIVERED = "delivered"
CONFLICT = "conflict"
REJECTED = "rejected"
PENDING = "pending"
#: The outbox could not be written: held here for the next publish.
UNQUEUED = "unqueued"
#: What an acknowledgement may set (from ``pending`` only).
OUTCOMES = frozenset({DELIVERED, CONFLICT, REJECTED})
UNQUEUED_LIMIT = int(os.getenv("OBSERVATION_UNQUEUED_LIMIT", "1000"))
#: Bounds of one read of the pending feed.
FEED_LIMIT_DEFAULT = 50
FEED_LIMIT_MAX = 200
#: Payloads with no outbox row yet, by content digest (insertion order: oldest first).
_UNQUEUED: dict[str, dict[str, Any]] = {}


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
        "canonical observation unqueued (outbox unavailable) field_id=%s index=%s held=%s",
        payload.get("field_id"),
        payload.get("indicator"),
        len(_UNQUEUED),
    )


async def requeue_unqueued() -> int:
    """Write the held payloads to the outbox (oldest first); stop at the first failure.

    Returns how many reached the outbox, where indicators-service's drain finds them."""
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


async def publish(payload: dict[str, Any]) -> str:
    """Write the outbox row for this published observation. Returns the row status, or
    ``unqueued`` when the outbox cannot be written (the payload is then held, see the module
    doc). Never raises and never calls another service."""
    if _UNQUEUED:
        await requeue_unqueued()
    queued = await enqueue(payload)
    if queued is None:
        _hold(payload)
        return UNQUEUED
    if queued[1] == PENDING:
        logger.info(
            "canonical observation queued field_id=%s index=%s outbox_id=%s",
            payload.get("field_id"),
            payload.get("indicator"),
            queued[0],
        )
    return queued[1]


# ── the pending feed indicators-service drains (routers/observation_feed.py) ───────────────
class OutboxUnavailable(RuntimeError):
    """The outbox cannot be read or written now; the caller answers 503 and retries."""


_PENDING = """
    SELECT id, payload, payload_sha256, created_at
    FROM raster_observation_outbox
    WHERE tenant_id = $1::uuid AND status = 'pending' AND id > $2
    ORDER BY id
    LIMIT $3
"""
_ACK = """
    UPDATE raster_observation_outbox SET
        status = $4,
        attempts = attempts + 1,
        last_status_code = NULL,
        last_error = $5,
        delivered_at = CASE WHEN $4 = 'delivered' THEN now() ELSE NULL END
    WHERE tenant_id = $1::uuid AND id = $2 AND payload_sha256 = $3 AND status = 'pending'
    RETURNING id
"""
_ENTRY = """
    SELECT status, payload_sha256 FROM raster_observation_outbox
    WHERE tenant_id = $1::uuid AND id = $2
"""


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value)


async def _connection():
    import db_persist

    conn = await db_persist._connect()
    if conn is None:
        raise OutboxUnavailable("database not configured or unreachable")
    return conn


async def pending_entries(
    tenant_id: str, *, limit: int = FEED_LIMIT_DEFAULT, after_id: int = 0
) -> list[dict[str, Any]]:
    """The tenant's ``pending`` entries after ``after_id``, oldest first. A read: it changes
    nothing. Tenant-bound twice: the explicit ``tenant_id`` predicate and RLS FORCE under
    ``app.current_tenant``. Raises ``OutboxUnavailable`` when it cannot answer."""
    bounded = max(1, min(int(limit), FEED_LIMIT_MAX))
    conn = await _connection()
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_id)
            rows = await conn.fetch(_PENDING, tenant_id, max(int(after_id), 0), bounded)
    except Exception as exc:  # noqa: BLE001 — the caller answers 503, the drain retries
        raise OutboxUnavailable(f"outbox read failed: {type(exc).__name__}") from exc
    finally:
        await conn.close()
    return [
        {
            "id": int(r["id"]),
            "payload": _payload(r["payload"]),
            "payload_sha256": str(r["payload_sha256"]),
            "created_at": r["created_at"].isoformat()
            if isinstance(r["created_at"], datetime)
            else r["created_at"],
        }
        for r in rows
    ]


def _ack_result(entry_id: int, outcome: str, row: Any, digest: str) -> dict[str, Any]:
    if row is None:
        return {"id": entry_id, "result": "not_found"}
    if str(row["payload_sha256"]) != digest:
        return {"id": entry_id, "result": "payload_mismatch", "status": str(row["status"])}
    if str(row["status"]) == outcome:
        return {"id": entry_id, "result": "already_acknowledged", "status": outcome}
    return {"id": entry_id, "result": "status_mismatch", "status": str(row["status"])}


async def acknowledge(tenant_id: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Settle the named entries of this tenant, each at the content it names; one result each.

    ``acknowledged``: the entry was ``pending`` and now carries ``outcome``.
    ``already_acknowledged``: it already carries that outcome (a repeated acknowledgement).
    ``status_mismatch``: it is settled with another outcome; left as it is.
    ``payload_mismatch``: the named digest is not the entry's content; left as it is.
    ``not_found``: no such entry for this tenant (another tenant's id answers the same).
    Only the named ids are touched, in one transaction. Raises ``OutboxUnavailable``."""
    conn = await _connection()
    results: list[dict[str, Any]] = []
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_id)
            for entry in entries:
                entry_id = int(entry["id"])
                outcome = str(entry["outcome"])
                digest = str(entry["payload_sha256"])
                if outcome not in OUTCOMES:
                    raise ValueError(f"unknown outcome {outcome!r}")
                detail = entry.get("detail")
                updated = await conn.fetchval(
                    _ACK,
                    tenant_id,
                    entry_id,
                    digest,
                    outcome,
                    None if outcome == DELIVERED or detail is None else str(detail)[:500],
                )
                if updated is not None:
                    results.append({"id": entry_id, "result": "acknowledged", "status": outcome})
                    continue
                row = await conn.fetchrow(_ENTRY, tenant_id, entry_id)
                results.append(_ack_result(entry_id, outcome, row, digest))
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 — nothing was settled; the drain retries
        raise OutboxUnavailable(f"outbox acknowledgement failed: {type(exc).__name__}") from exc
    finally:
        await conn.close()
    for item in results:
        if item["result"] == "acknowledged" and item["status"] != DELIVERED:
            logger.error(
                "canonical observation %s outbox_id=%s (terminal, kept on the row)",
                item["status"],
                item["id"],
            )
    return results
