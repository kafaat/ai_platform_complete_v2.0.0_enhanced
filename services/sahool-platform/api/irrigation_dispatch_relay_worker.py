"""IRR-F01 Gate B-delivery Slice B-d2-live — the reservation-dispatch relay worker.

The last live hop of Gate B-delivery: subscribe to the reservation dispatch events the existing
``OutboxWorker`` publishes to NATS (``irrigation.reservation.dispatch_requested`` / ``_failed``),
map each delivered envelope with the PURE mapper (``irrigation_dispatch_relay``), and POST it to
decision-service's durable inbox (``POST /v1/reservation-dispatch-intents``, migration 027).

Boundaries this worker MUST preserve (the delivery≠fulfillment contract locked by
``tests/irrigation/test_gate_b_dispatch_relay_and_contract.py``):
  * it performs NO fulfillment — it never derives or creates an execution_request; it only relays
    a delivery to the inbox, which records it (dedup on ``source_event_id``) and stops there;
  * it is idempotent-safe — the sink dedups, so a redelivered event is a no-op; the relay may
    safely re-POST;
  * it is DEFAULT-OFF behind ``FEATURE_RESERVATION_DISPATCH_RELAY`` — with the flag unset the
    worker never runs, so events simply rest in the outbox (honest, no silent side effects).

Durability of the NATS hop itself (core NATS fire-and-forward vs JetStream ack) is a live-cert
decision made against a running NATS + decision-service stack; the outbox remains the durable
producer and the inbox the idempotent sink, so a lost core-NATS message is re-published by the
outbox and de-duplicated at the sink. The message→ingest→POST core here is pure and unit-tested so
the contract holds without any infrastructure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from decision_service_client import decision_service_headers, decision_service_url
from irrigation_dispatch_relay import (
    SUPPORTED_DISPATCH_EVENTS,
    build_reservation_dispatch_ingest,
)
from worker_heartbeat import HeartbeatState

logger = logging.getLogger("sahool.irrigation.dispatch_relay")

RELAY_FLAG = "FEATURE_RESERVATION_DISPATCH_RELAY"
# WORKERS-INHERIT-AN-HTTP-HEALTHCHECK-THEY-CANNOT-ANSWER-01: the platform image's Dockerfile
# HEALTHCHECK curls :8000/healthz, which this worker never serves — so it read as unhealthy
# forever. The heartbeat below is what `python -m api.worker_heartbeat check --worker
# reservation-dispatch-relay` reads from compose. The relay is event-driven, so the beat is
# time-based (every IDLE_BEAT_SECONDS while waiting) plus one per handled message; `--max-age`
# in compose must exceed IDLE_BEAT_SECONDS.
WORKER_NAME = "reservation-dispatch-relay"
IDLE_BEAT_SECONDS = 60.0
INGEST_PATH = "/v1/reservation-dispatch-intents"
# Subjects the outbox publishes reservation dispatch events on (sahool.events.<event_type>).
DEFAULT_SUBJECTS = tuple(f"sahool.events.{e}" for e in sorted(SUPPORTED_DISPATCH_EVENTS))

# A POST result the sink treats as a settled delivery: 200 (recorded or duplicate) — the inbox is
# idempotent, so a duplicate is success, not an error.
_SETTLED_STATUSES = frozenset({200, 201})

PostFn = Callable[[str | None, dict[str, Any]], Awaitable[tuple[int, Any]]]


def relay_enabled() -> bool:
    """Default-off: with the flag unset the relay never runs (events rest in the outbox)."""
    return os.getenv(RELAY_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def subscribed_subjects() -> tuple[str, ...]:
    override = os.getenv("RESERVATION_DISPATCH_RELAY_SUBJECTS", "").strip()
    if override:
        return tuple(s.strip() for s in override.split(",") if s.strip())
    return DEFAULT_SUBJECTS


async def handle_delivered_message(raw: bytes, *, post_fn: PostFn) -> dict[str, Any]:
    """The pure, infrastructure-free heart: decode a delivered NATS envelope, map it to the ingest
    body (fail-closed on an unsupported/id-less event — never silently drop), and POST it to the
    inbox. Returns a structured outcome; performs NO fulfillment."""
    try:
        envelope = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("dispatch relay: dropping malformed envelope")
        return {"outcome": "skipped", "reason": "malformed_json"}
    if not isinstance(envelope, dict):
        return {"outcome": "skipped", "reason": "malformed_json"}

    event_type = envelope.get("event_type")
    if event_type not in SUPPORTED_DISPATCH_EVENTS:
        # Not a reservation dispatch event — a wildcard subscription would see other traffic.
        return {"outcome": "skipped", "reason": "unsupported_event"}
    try:
        body = build_reservation_dispatch_ingest(
            event_type=event_type,
            source_event_id=envelope.get("event_id"),
            payload=envelope.get("payload"),
            correlation_id=envelope.get("correlation_id"),
            causation_id=envelope.get("causation_id"),
        )
    except ValueError as exc:
        logger.warning("dispatch relay: unmappable event: %s", exc)
        return {"outcome": "skipped", "reason": str(exc)}

    tenant_id = envelope.get("tenant_id")
    status, resp = await post_fn(tenant_id, body)
    if status in _SETTLED_STATUSES:
        return {
            "outcome": "delivered",
            "status": status,
            "source_event_id": body["source_event_id"],
        }
    # Non-2xx (incl. 503 mirror / SoR-off): not settled — surfaced for the caller to retry/log. The
    # sink's dedup makes a later redelivery safe. Never fulfilled here.
    logger.warning(
        "dispatch relay: inbox POST not settled (status=%s) for %s",
        status,
        body["source_event_id"],
    )
    return {
        "outcome": "failed",
        "status": status,
        "source_event_id": body["source_event_id"],
        "detail": resp,
    }


async def _default_post(tenant_id: str | None, body: dict[str, Any]) -> tuple[int, Any]:
    """Return the transport status and decoded body; do not collapse it to a dict."""
    import httpx

    url = f"{decision_service_url()}/{INGEST_PATH.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                json=body,
                headers=decision_service_headers(tenant_id=tenant_id),
            )
    except httpx.HTTPError as exc:
        return 502, {"detail": f"decision-service unavailable: {exc}"}
    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text
    return response.status_code, payload


def make_message_handler(
    post: PostFn, heartbeat: HeartbeatState
) -> Callable[[Any], Awaitable[None]]:
    """The NATS callback: relay one delivery and leave a heartbeat behind it.

    A handler error marks the beat ``failed`` (the probe reports it with the error text) but
    never kills the subscription — the next delivery may succeed and mark it running again.
    """

    async def _on_message(msg: Any) -> None:
        try:
            result = await handle_delivered_message(msg.data, post_fn=post)
        except Exception as exc:  # noqa: BLE001 — a single bad message must not kill the worker
            logger.warning("dispatch relay handler error: %s", exc)
            heartbeat.mark_error(f"{type(exc).__name__}: {exc}")
        else:
            # The structured outcome IS the health signal — a handler that returns is not a
            # handler that delivered. Only `delivered` counts; a `failed` POST (503 mirror,
            # SoR-off, 502) is an error the probe must show; `skipped` proves liveness only.
            outcome = result.get("outcome")
            if outcome == "delivered":
                heartbeat.mark_poll(1)
            elif outcome == "failed":
                heartbeat.mark_error(
                    f"inbox_post_not_settled:status={result.get('status')} "
                    f"event={result.get('source_event_id')}"
                )
            else:
                _touch_alive(heartbeat)
        heartbeat.write()

    return _on_message


def _touch_alive(heartbeat: HeartbeatState) -> None:
    """Refresh `last_poll_at` without changing state or counters.

    Used for beats that prove the process is alive but say nothing about delivery: a skipped
    (foreign) message, or the idle tick. A `failed` state is deliberately preserved — only a
    `delivered` outcome clears it — so a relay whose last POST failed stays unhealthy until a
    delivery actually succeeds, instead of turning green sixty seconds later by the clock.
    """
    heartbeat.last_poll_at = time.time()
    if heartbeat.current_state == "starting":
        heartbeat.current_state = "running"


async def idle_with_heartbeat(heartbeat: HeartbeatState, *, state: str) -> None:
    """Wait forever, beating every IDLE_BEAT_SECONDS so the probe can tell 'waiting' from 'dead'.

    ``state`` is what the beat reports (``idle`` when the feature flag is off, ``running`` while
    subscribed) — a disabled relay is healthy *and* visibly idle, never disguised as working.
    A ``failed`` state set by a message handler is never overwritten here: the clock proves the
    process is alive, not that delivery recovered.
    """
    while True:
        if heartbeat.current_state == "failed":
            _touch_alive(heartbeat)
        else:
            heartbeat.mark_poll(0)
            heartbeat.current_state = state
        heartbeat.write()
        await asyncio.sleep(IDLE_BEAT_SECONDS)


async def run_relay(
    *, post_fn: PostFn | None = None, heartbeat: HeartbeatState | None = None
) -> None:
    """Connect NATS, subscribe to the reservation dispatch subjects, and relay each delivery to the
    inbox until cancelled. No-op (with a clear log) when the relay flag is off."""
    if not relay_enabled():
        logger.info("reservation dispatch relay disabled (%s unset) — not starting", RELAY_FLAG)
        return
    nats_url = os.getenv("NATS_URL") or os.getenv("SAHOOL_NATS_URL") or "nats://sahool-nats:4222"
    post = post_fn or _default_post
    beat = heartbeat or HeartbeatState(WORKER_NAME)

    import nats  # type: ignore
    from shared.broker_url import redact_broker_url

    nc = await nats.connect(nats_url, max_reconnect_attempts=-1)
    # `NATS_URL` صار يحمل الاعتماد — يُطبَع مُنقّى (NATS-BROKER-HAS-NO-AUTHENTICATION-…-01).
    logger.info("reservation dispatch relay connected to NATS at %s", redact_broker_url(nats_url))

    on_message = make_message_handler(post, beat)
    try:
        for subject in subscribed_subjects():
            await nc.subscribe(subject, cb=on_message)
            logger.info("reservation dispatch relay subscribed to %s", subject)
        await idle_with_heartbeat(beat, state="running")
    finally:
        await nc.drain()


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    async def _serve() -> None:
        heartbeat = HeartbeatState(WORKER_NAME)
        heartbeat.write()  # `starting` — a fresh file before NATS is even reachable
        if not relay_enabled():
            # Started (e.g. under the `relay` profile) but the feature is off: idle instead of
            # exiting, so the container stays a harmless no-op without restart-thrashing.
            logger.info("reservation dispatch relay disabled (%s unset) — idling", RELAY_FLAG)
            await idle_with_heartbeat(heartbeat, state="idle")
        await run_relay(heartbeat=heartbeat)

    asyncio.run(_serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
