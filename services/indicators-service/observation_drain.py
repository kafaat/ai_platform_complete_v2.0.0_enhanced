"""The canonical observation drain (W1-11, pull form — owner decision 2026-11-16).

indicators-service PULLS the observations raster-service published; raster-service never calls
this service. The push it replaced (raster → ``POST /internal/v1/observations``) closed the cycle
[indicators-service, raster-service] in the architecture graph (``architecture:no_cycles``, no
exception list): this service already reads raster-service for its observation and timeline
adapters, so the only direction left is this one.

One cycle, per tenant of the explicit partition:

1. ``GET {RASTER_SERVICE_URL}/internal/v1/observation-outbox`` — the tenant's pending entries
   (raster's ``raster_observation_outbox``, v286), with the mesh service token and the tenant
   asserted in ``X-Tenant-Id``, as every internal hop of this service to raster does;
2. each entry goes through the one store path, ``observation_store.insert_observation`` (the same
   validation and the same rules: same id and revision with the same content is a replay, with
   other content a conflict and nothing is stored);
3. ``POST …/acknowledgements`` names exactly the entries this cycle settled, each at the
   ``payload_sha256`` it read: ``delivered`` (created or replayed), ``conflict`` (recorded on
   raster's row as terminal, never acknowledged as a success) or ``rejected`` (the payload is not
   a valid observation, or names another tenant). An entry the store could not answer for is not
   acknowledged: it stays pending and the next cycle reads it again. A failed acknowledgement
   leaves the entries pending too; the next cycle stores them again as replays.

Tenants: ``INDICATORS_OBSERVATION_DRAIN_TENANTS``, a UUID CSV, as raster's own durable workers
(``RASTER_FOLLOWUP_TENANTS``): an operator-assigned partition, no cross-tenant enumeration and no
read of another service's database. Empty means the drain idles, and ``/readyz`` says so.

A drain that is off or has no tenants is reported on ``/readyz`` as not ready for delivery
(``ready_for_delivery: false``, ``delivery: not_enabled``); it never deletes or settles
anything, so raster's pending entries wait for it.

Switch: ``INDICATORS_OBSERVATION_DRAIN_ENABLED`` (default on); interval
``INDICATORS_OBSERVATION_DRAIN_INTERVAL_SECONDS`` (default 30); page size
``INDICATORS_OBSERVATION_DRAIN_BATCH`` (default 50, at most 200). Observable without secrets:
``state()`` on ``/readyz`` and ``sahool_indicators_observation_drain_total{result=…}`` on
``/metrics``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import observation_store
from prometheus_client import Counter
from pydantic import ValidationError

logger = logging.getLogger("indicators-service.observation_drain")

FEED_PATH = "/internal/v1/observation-outbox"
ACK_PATH = f"{FEED_PATH}/acknowledgements"
HTTP_TIMEOUT_S = 15.0
#: Pages one tenant may drain in one cycle (a backlog is finished over the next cycles).
MAX_PAGES = 10

RESULTS = (
    "created",
    "replayed",
    "conflict",
    "rejected",
    "store_unavailable",
    "malformed_entry",
    "fetch_failed",
    "ack_failed",
    "ack_mismatch",
    "acknowledged",
)
_METRIC = Counter(
    "sahool_indicators_observation_drain_total",
    "Canonical observation drain outcomes (W1-11 pull from raster-service), by result.",
    ["result"],
)

_STATE: dict[str, Any] = {
    "running": False,
    "cycles": 0,
    "last_cycle_at": None,
    "last_cycle_ok": None,
    "last_skip_reason": None,
    "counters": dict.fromkeys(RESULTS, 0),
}


def _count(result: str, amount: int = 1) -> None:
    if amount <= 0:
        return
    _STATE["counters"][result] = _STATE["counters"].get(result, 0) + amount
    _METRIC.labels(result=result).inc(amount)


def enabled() -> bool:
    flag = os.getenv("INDICATORS_OBSERVATION_DRAIN_ENABLED", "true").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def tenants() -> tuple[str, ...]:
    """The explicit tenant partition; an entry that is not a UUID is ignored and logged."""
    found: set[str] = set()
    for raw in os.getenv("INDICATORS_OBSERVATION_DRAIN_TENANTS", "").split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            found.add(str(UUID(item)))
        except ValueError:
            logger.error("INDICATORS_OBSERVATION_DRAIN_TENANTS: ignoring a value that is no UUID")
    return tuple(sorted(found))


def interval_seconds() -> float:
    try:
        value = float(os.getenv("INDICATORS_OBSERVATION_DRAIN_INTERVAL_SECONDS", "30"))
    except ValueError:
        value = 30.0
    return max(value, 1.0)


def batch_size() -> int:
    try:
        value = int(os.getenv("INDICATORS_OBSERVATION_DRAIN_BATCH", "50"))
    except ValueError:
        value = 50
    return max(1, min(value, 200))


def _raster_url() -> str:
    return os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip("/")


def _token() -> str:
    return os.getenv("SAHOOL_AGENT_TOKEN") or os.getenv("RASTER_SERVICE_TOKEN", "")


def state() -> dict[str, Any]:
    """What ``/readyz`` shows: switches, counts and booleans, never a token or a payload.

    ``ready_for_delivery`` is true only when a cycle would drain now (switch on, a non-empty
    tenant partition, token and store configured); otherwise ``delivery`` is ``not_enabled``
    with the reason. A drain that is not enabled deletes nothing: raster's entries stay
    pending in its outbox."""
    reason = skip_reason()
    return {
        "ready_for_delivery": reason is None,
        "delivery": "enabled" if reason is None else "not_enabled",
        "not_enabled_reason": reason,
        "enabled": enabled(),
        "tenants": len(tenants()),
        "token_configured": bool(_token()),
        "store_configured": observation_store.configured(),
        "interval_seconds": interval_seconds(),
        "running": _STATE["running"],
        "cycles": _STATE["cycles"],
        "last_cycle_at": _STATE["last_cycle_at"],
        "last_cycle_ok": _STATE["last_cycle_ok"],
        "last_skip_reason": _STATE["last_skip_reason"],
        "counters": dict(_STATE["counters"]),
    }


def skip_reason() -> str | None:
    """Why a cycle would do nothing now, or ``None`` when it would drain."""
    if not enabled():
        return "disabled"
    if not tenants():
        return "no_tenants"
    if not _token():
        return "token_not_configured"
    if not observation_store.configured():
        return "store_not_configured"
    return None


def record_skip(reason: str | None) -> None:
    _STATE["last_skip_reason"] = reason


def _validation_detail(exc: ValidationError) -> str:
    # Field paths and error types only: the offered values stay out of logs and of raster's row.
    parts = [
        ".".join(str(p) for p in err.get("loc", ())) + ":" + err["type"] for err in exc.errors()
    ]
    return "invalid payload: " + "; ".join(parts[:5])


class _StoreDown(Exception):
    """The store could not answer: stop this tenant's cycle, acknowledge nothing more."""


async def settle(entry: dict[str, Any], tenant: str) -> dict[str, Any] | None:
    """Store one entry through the store path; the acknowledgement it earns, or ``None`` when
    the entry is malformed (no id or digest, so it cannot be named). Raises ``_StoreDown``."""
    entry_id = entry.get("id")
    digest = entry.get("payload_sha256")
    if not isinstance(entry_id, int) or isinstance(entry_id, bool) or not isinstance(digest, str):
        _count("malformed_entry")
        return None
    ack = {"id": entry_id, "payload_sha256": digest}
    try:
        record = observation_store.PublishedObservationV1.model_validate(entry.get("payload"))
    except ValidationError as exc:
        _count("rejected")
        return {**ack, "outcome": "rejected", "detail": _validation_detail(exc)}
    if str(record.tenant_id) != tenant:
        _count("rejected")
        return {**ack, "outcome": "rejected", "detail": "tenant_mismatch"}
    try:
        result = await observation_store.insert_observation(record)
    except observation_store.StoreUnavailable as exc:
        _count("store_unavailable")
        logger.warning("canonical observation store unavailable, entry left pending: %s", exc)
        raise _StoreDown from exc
    _count(result["status"])
    if result["status"] == "conflict":
        logger.error(
            "canonical observation conflict observation_id=%s outbox_id=%s: stored %s, offered %s",
            result["observation_id"],
            entry_id,
            result["stored_payload_sha256"],
            result["payload_sha256"],
        )
        return {
            **ack,
            "outcome": "conflict",
            "detail": (
                f"observation_conflict observation_id={result['observation_id']} "
                f"stored={result['stored_payload_sha256']} offered={result['payload_sha256']}"
            ),
        }
    return {**ack, "outcome": "delivered"}


def _headers(tenant: str, token: str) -> dict[str, str]:
    return {"X-Agent-Token": token, "X-Tenant-Id": tenant}


async def _acknowledge(
    client: httpx.AsyncClient, tenant: str, token: str, acks: list[dict[str, Any]]
) -> bool:
    try:
        response = await client.post(
            f"{_raster_url()}{ACK_PATH}", json={"entries": acks}, headers=_headers(tenant, token)
        )
    except httpx.HTTPError as exc:
        _count("ack_failed")
        logger.warning("observation outbox acknowledgement failed: %s", type(exc).__name__)
        return False
    if response.status_code != 200:
        _count("ack_failed")
        logger.warning("observation outbox acknowledgement HTTP %s", response.status_code)
        return False
    results = (response.json() or {}).get("results") or []
    settled = {"acknowledged", "already_acknowledged"}
    done = sum(1 for r in results if r.get("result") in settled)
    _count("acknowledged", done)
    mismatched = [r for r in results if r.get("result") not in settled]
    if mismatched or len(results) != len(acks):
        _count("ack_mismatch", max(len(mismatched), 1))
        logger.error("observation outbox acknowledgement not applied: %s", mismatched[:5])
    return True


async def drain_tenant(client: httpx.AsyncClient, tenant: str) -> bool:
    """Drain one tenant's pending entries (up to ``MAX_PAGES`` pages). ``True`` when every
    read, store and acknowledgement of the cycle answered."""
    token = _token()
    batch = batch_size()
    after = 0
    for _ in range(MAX_PAGES):
        try:
            response = await client.get(
                f"{_raster_url()}{FEED_PATH}",
                params={"limit": batch, "after_id": after},
                headers=_headers(tenant, token),
            )
        except httpx.HTTPError as exc:
            _count("fetch_failed")
            logger.warning("observation outbox read failed: %s", type(exc).__name__)
            return False
        if response.status_code != 200:
            _count("fetch_failed")
            logger.warning("observation outbox read HTTP %s", response.status_code)
            return False
        entries = (response.json() or {}).get("entries") or []
        acks: list[dict[str, Any]] = []
        store_down = False
        for entry in entries:
            try:
                ack = await settle(entry, tenant)
            except _StoreDown:
                store_down = True
                break
            if ack is not None:
                acks.append(ack)
        acked = await _acknowledge(client, tenant, token, acks) if acks else True
        if store_down or not acked:
            return False
        if len(entries) < batch:
            return True
        after = entries[-1]["id"]
    return True


async def run_cycle(*, transport: Any = None) -> dict[str, Any]:
    """One drain cycle over every tenant of the partition. Never raises."""
    reason = skip_reason()
    record_skip(reason)
    if reason is not None:
        return {"skipped": reason}
    kwargs: dict[str, Any] = {"timeout": HTTP_TIMEOUT_S, "trust_env": False}
    if transport is not None:
        kwargs["transport"] = transport
    results: dict[str, bool] = {}
    async with httpx.AsyncClient(**kwargs) as client:
        for tenant in tenants():
            try:
                results[tenant] = await drain_tenant(client, tenant)
            except Exception as exc:  # noqa: BLE001 — one tenant never stops the others
                logger.error("observation drain failed for a tenant: %s", type(exc).__name__)
                results[tenant] = False
    _STATE["cycles"] += 1
    _STATE["last_cycle_at"] = datetime.now(UTC).isoformat()
    _STATE["last_cycle_ok"] = all(results.values())
    return {"tenants": results}


async def serve() -> None:
    """The background loop (started by the app lifespan when the drain can run)."""
    _STATE["running"] = True
    try:
        while True:
            await run_cycle()
            await asyncio.sleep(interval_seconds())
    finally:
        _STATE["running"] = False
