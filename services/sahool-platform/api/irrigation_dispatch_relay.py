"""IRR-F01 Gate B-delivery — pure relay mapping (event outbox -> decision-service ingest).

The reservation dispatch INTENT is emitted to the existing v11 outbox
(``irrigation.reservation.dispatch_requested`` / ``_failed``) and relayed to NATS by the
existing ``OutboxWorker``. Gate B-delivery's remaining live hop is a consumer that reads that
delivered event and POSTs it to decision-service's durable inbox
(``POST /v1/reservation-dispatch-intents``, built in migration 027 + persistence).

This module is the PURE, side-effect-free heart of that consumer: it maps a delivered event
envelope to the decision-service ingest body. The NATS subscription + HTTP POST + service-token
auth are the thin live glue certified against a running NATS + decision-service stack (deferred);
keeping the mapping pure lets the contract be unit-tested without any infrastructure.

It performs NO fulfillment: it never derives an execution_request. Delivery is idempotent at the
sink (dedup on ``source_event_id``), so the relay may safely redeliver.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# The only reservation dispatch events the inbox accepts (mirrors migration 027's CHECK).
SUPPORTED_DISPATCH_EVENTS = frozenset(
    {
        "irrigation.reservation.dispatch_requested",
        "irrigation.reservation.dispatch_failed",
    }
)


def build_reservation_dispatch_ingest(
    *,
    event_type: str,
    source_event_id: str,
    payload: Mapping[str, Any] | None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> dict[str, Any]:
    """Map one delivered outbox event to the decision-service ingest body.

    ``source_event_id`` is the platform ``events.event_id`` — the sink's dedup anchor, so a
    redelivered event maps to the same request and is a no-op at the inbox. Raises ValueError on
    an unsupported event type or a missing event id (fail-closed: never silently drop a delivery).
    """
    if event_type not in SUPPORTED_DISPATCH_EVENTS:
        raise ValueError(f"UNSUPPORTED_DISPATCH_EVENT:{event_type}")
    if not str(source_event_id or "").strip():
        raise ValueError("MISSING_SOURCE_EVENT_ID")
    p: Mapping[str, Any] = payload or {}
    return {
        "source_event_id": str(source_event_id),
        "event_type": event_type,
        "evaluation_id": p.get("evaluation_id"),
        "reservation_ids": list(p.get("reservation_ids") or []),
        "execution_ref_type": p.get("execution_ref_type"),
        "execution_ref_id": p.get("execution_ref_id"),
        "correlation_id": str(correlation_id) if correlation_id else None,
        "causation_id": str(causation_id) if causation_id else None,
        # The full delivered payload is preserved verbatim for provenance/audit at the sink.
        "raw_payload": dict(p),
    }
