"""Reconciliation sweep of published observations with no outbox row (W1-11 hardening).

The publish path marks an asset ``ready`` and then, in a separate transaction, writes its
observation to ``raster_observation_outbox`` (``observation_outbox.publish``). A crash, or an
outbox that stays down past the in-process hold, between the two leaves a published asset that
indicators-service never drains (gap RASTER-OBSERVATION-PUBLISH-OUTBOX-NOT-ATOMIC-01, open).

This sweep finds those assets and queues them. Its source is the payload the publish path
stored, with its digest, in the asset row's ``provenance`` (``observation_outbox``'s
``PROVENANCE_PAYLOAD_KEY`` / ``PROVENANCE_DIGEST_KEY``), written in the same statement as the
asset itself. The payload cannot be rebuilt from the row (``acquisition_date`` is a DATE, so
the acquisition instant and with it the observation id would change; median/p10/p90 are not
kept), so the stored bytes are what is queued: the same digest and the same product identity as
the publish path, through the same ``enqueue`` (``ON CONFLICT … DO NOTHING`` on
``raster_observation_outbox_once``), so a re-run or a race with the publish path adds nothing.

What it does not cover: an asset published before its payload was stored in provenance (no
stored payload, nothing to queue), and a payload whose stored digest no longer matches its bytes
(counted ``digest_mismatch``, never queued).

Progress: such a mismatched row never gets an outbox row, so it matches the query on every run.
Each tenant's pass therefore resumes after the last asset id the previous pass read (a keyset
cursor on ``raster_assets.id``, kept in process state) and wraps to the start once a pass
returns fewer rows than the bound, so rows that are never queued cannot hide a genuinely missing
asset behind them. A run that meets a mismatched row is not ok (``last_run_ok`` false) and
``last_run_mismatches`` says how many it met.

Tenants: ``RASTER_OBSERVATION_SWEEP_TENANTS``, a UUID CSV, the same rule as this service's
durable follow-up worker (``RASTER_FOLLOWUP_TENANTS``, ``follow_up_runtime.configured_tenants``):
an operator-assigned partition, one transaction per tenant under ``app.current_tenant`` (RLS
FORCE on both tables), no cross-tenant enumeration and no role that bypasses row security. Empty: the sweep idles.

Switch: ``RASTER_OBSERVATION_SWEEP_ENABLED`` (default on); interval
``RASTER_OBSERVATION_SWEEP_INTERVAL_SECONDS`` (default 300); per-tenant bound per run
``RASTER_OBSERVATION_SWEEP_BATCH`` (default 100, at most 1000). Observable without secrets:
``state()`` on ``/readyz`` and ``sahool_raster_batch_observation_sweep_*`` on ``/metrics``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import observation_outbox

logger = logging.getLogger("raster-service.observation_sweep")

RESULTS = (
    "found",
    "enqueued",
    "already_queued",
    "digest_mismatch",
    "tenant_mismatch",
    "enqueue_failed",
    "read_failed",
)

_STATE: dict[str, Any] = {
    "running": False,
    "runs": 0,
    "last_run_at": None,
    "last_run_ok": None,
    "last_skip_reason": None,
    "last_run_mismatches": 0,
    "counters": dict.fromkeys(RESULTS, 0),
    # tenant -> the last ``raster_assets.id`` the previous pass read; 0 = from the start.
    # Process state only, never shown (it names tenants).
    "cursors": {},
}

# A published asset (``ready``) whose stored observation payload has no outbox row at that exact
# content. The outbox identity is what ``enqueue`` writes: the payload's product identity, or
# its digest when it has none.
_MISSING = """
    SELECT a.id AS asset_id,
           a.product_identity_key,
           a.provenance -> 'observation_payload' AS payload,
           a.provenance ->> 'observation_payload_sha256' AS digest
    FROM raster_assets a
    WHERE a.tenant_id = $1::uuid
      AND a.id > $3
      AND a.asset_status = 'ready'
      AND a.provenance ? 'observation_payload'
      AND a.provenance ? 'observation_payload_sha256'
      AND NOT EXISTS (
          SELECT 1 FROM raster_observation_outbox o
          WHERE o.tenant_id = $1::uuid
            AND o.product_identity_key = COALESCE(
                a.provenance -> 'observation_payload' ->> 'product_identity_key',
                a.provenance ->> 'observation_payload_sha256')
            AND o.payload_sha256 = a.provenance ->> 'observation_payload_sha256'
      )
    ORDER BY a.id
    LIMIT $2
"""


def _count(result: str, amount: int = 1) -> None:
    if amount <= 0:
        return
    _STATE["counters"][result] = _STATE["counters"].get(result, 0) + amount
    try:
        import raster_batch_observability

        raster_batch_observability.inc(f"observation_sweep_{result}_total", amount)
    except Exception:  # noqa: BLE001 — a counter never stops the sweep
        pass


def enabled() -> bool:
    flag = os.getenv("RASTER_OBSERVATION_SWEEP_ENABLED", "true").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def tenants() -> tuple[str, ...]:
    """The explicit tenant partition; a value that is no UUID is ignored and logged."""
    found: set[str] = set()
    for raw in os.getenv("RASTER_OBSERVATION_SWEEP_TENANTS", "").split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            found.add(str(UUID(item)))
        except ValueError:
            logger.error("RASTER_OBSERVATION_SWEEP_TENANTS: ignoring a value that is no UUID")
    return tuple(sorted(found))


def interval_seconds() -> float:
    try:
        value = float(os.getenv("RASTER_OBSERVATION_SWEEP_INTERVAL_SECONDS", "300"))
    except ValueError:
        value = 300.0
    return max(value, 5.0)


def batch_size() -> int:
    try:
        value = int(os.getenv("RASTER_OBSERVATION_SWEEP_BATCH", "100"))
    except ValueError:
        value = 100
    return max(1, min(value, 1000))


def skip_reason() -> str | None:
    """Why a run would do nothing now, or ``None`` when it would sweep."""
    if not enabled():
        return "disabled"
    if not tenants():
        return "no_tenants"
    import db_persist

    if not db_persist.DATABASE_URL:
        return "database_not_configured"
    return None


def state() -> dict[str, Any]:
    """What ``/readyz`` shows: switches, counts and booleans, never a payload."""
    return {
        "enabled": enabled(),
        "tenants": len(tenants()),
        "interval_seconds": interval_seconds(),
        "batch": batch_size(),
        "running": _STATE["running"],
        "runs": _STATE["runs"],
        "last_run_at": _STATE["last_run_at"],
        "last_run_ok": _STATE["last_run_ok"],
        "last_skip_reason": _STATE["last_skip_reason"],
        "last_run_mismatches": _STATE.get("last_run_mismatches", 0),
        "unqueued_held": observation_outbox.unqueued_count(),
        "counters": dict(_STATE["counters"]),
    }


def _decode(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        value = json.loads(value)
    return value


async def missing_entries(tenant: str, limit: int, after_id: int = 0) -> list[dict[str, Any]]:
    """The tenant's published assets whose stored payload has no outbox row (at most ``limit``,
    asset id above ``after_id``, in id order). Raises ``observation_outbox.OutboxUnavailable``
    when it cannot read."""
    conn = await observation_outbox._connection()
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            rows = await conn.fetch(_MISSING, tenant, limit, after_id)
    except Exception as exc:  # noqa: BLE001 — the run is counted as failed and retried
        raise observation_outbox.OutboxUnavailable(
            f"sweep read failed: {type(exc).__name__}"
        ) from exc
    finally:
        await conn.close()
    return [
        {
            "asset_id": int(r["asset_id"]),
            "product_identity_key": r["product_identity_key"],
            "payload": _decode(r["payload"]),
            "digest": str(r["digest"]),
        }
        for r in rows
    ]


async def sweep_tenant(tenant: str, *, limit: int | None = None) -> dict[str, int]:
    """One bounded pass over one tenant, resuming after the previous pass's last asset id.
    Returns this pass's counts."""
    counts = dict.fromkeys(RESULTS, 0)
    bound = limit or batch_size()
    cursors: dict[str, int] = _STATE.setdefault("cursors", {})
    after_id = cursors.get(tenant, 0)
    try:
        found = await missing_entries(tenant, bound, after_id)
    except observation_outbox.OutboxUnavailable as exc:
        logger.warning("observation sweep read failed for a tenant: %s", exc)
        counts["read_failed"] += 1
        _count("read_failed")
        return counts
    counts["found"] = len(found)
    _count("found", len(found))
    for item in found:
        payload = item["payload"]
        if (
            not isinstance(payload, dict)
            or observation_outbox.payload_sha256(payload) != item["digest"]
        ):
            counts["digest_mismatch"] += 1
            _count("digest_mismatch")
            logger.error(
                "observation sweep: stored payload does not match its digest product=%s",
                item["product_identity_key"],
            )
            continue
        if str(payload.get("tenant_id")) != tenant:
            counts["tenant_mismatch"] += 1
            _count("tenant_mismatch")
            continue
        queued = await observation_outbox.enqueue(payload)
        if queued is None:
            counts["enqueue_failed"] += 1
            _count("enqueue_failed")
            # The outbox is down: stop this tenant; the cursor stays, the next run retries.
            return counts
        counts["enqueued"] += 1
        _count("enqueued")
        logger.info(
            "observation sweep queued a published asset with no outbox row field_id=%s "
            "index=%s outbox_id=%s status=%s",
            payload.get("field_id"),
            payload.get("indicator"),
            queued[0],
            queued[1],
        )
    # A short pass reached the end: the next one starts again from the first asset.
    cursors[tenant] = int(found[-1]["asset_id"]) if len(found) >= bound else 0
    return counts


async def run_once() -> dict[str, Any]:
    """One run over every tenant of the partition. Never raises."""
    reason = skip_reason()
    _STATE["last_skip_reason"] = reason
    if reason is not None:
        return {"skipped": reason}
    results: dict[str, dict[str, int]] = {}
    ok = True
    mismatches = 0
    for tenant in tenants():
        try:
            counts = await sweep_tenant(tenant)
        except Exception as exc:  # noqa: BLE001 — one tenant never stops the others
            logger.error("observation sweep failed for a tenant: %s", type(exc).__name__)
            counts = {"read_failed": 1}
        results[tenant] = counts
        met = counts.get("digest_mismatch", 0) + counts.get("tenant_mismatch", 0)
        mismatches += met
        ok = ok and not counts.get("read_failed") and not counts.get("enqueue_failed") and not met
    _STATE["runs"] += 1
    _STATE["last_run_at"] = datetime.now(UTC).isoformat()
    _STATE["last_run_ok"] = ok
    _STATE["last_run_mismatches"] = mismatches
    return {"tenants": results}


async def serve() -> None:
    """The background loop (started by the app lifespan when the sweep can run)."""
    _STATE["running"] = True
    try:
        while True:
            await run_once()
            await asyncio.sleep(interval_seconds())
    finally:
        _STATE["running"] = False
