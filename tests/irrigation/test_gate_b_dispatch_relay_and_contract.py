"""IRR-F01 Gate B-delivery — relay mapping unit tests + delivery≠fulfillment governance guard.

Two concerns:
 1. The PURE relay mapper (``build_reservation_dispatch_ingest``) that a live NATS consumer will
    use to turn a delivered outbox event into the decision-service ingest body — tested with no
    infrastructure.
 2. A STATIC guard locking the whole Gate-B boundary invariant: recording DELIVERY must never
    perform FULFILLMENT. The inbox migration, the persistence recorder, and the ingest endpoint
    must not create a decision_execution_request; the sink must stay idempotent, append-only, and
    fail-closed in mirror mode. This prevents the boundary from silently eroding into an
    auto-executing side path (the Option-2 governance bypass the design forbids).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "services" / "sahool-platform"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from api.irrigation_dispatch_relay import (  # noqa: E402
    SUPPORTED_DISPATCH_EVENTS,
    build_reservation_dispatch_ingest,
)

REQUESTED = "irrigation.reservation.dispatch_requested"
FAILED = "irrigation.reservation.dispatch_failed"


# --- pure relay mapping ---------------------------------------------------------------------


def test_maps_dispatch_requested_payload_to_ingest_body():
    body = build_reservation_dispatch_ingest(
        event_type=REQUESTED,
        source_event_id="evt-1",
        correlation_id="corr-1",
        payload={
            "evaluation_id": "eval-1",
            "reservation_ids": ["r1", "r2"],
            "execution_ref_type": "manual_execution",
            "execution_ref_id": "mx-1",
            "state": "dispatch_requested",
        },
    )
    assert body["source_event_id"] == "evt-1"
    assert body["event_type"] == REQUESTED
    assert body["evaluation_id"] == "eval-1"
    assert body["reservation_ids"] == ["r1", "r2"]
    assert body["execution_ref_type"] == "manual_execution"
    assert body["execution_ref_id"] == "mx-1"
    assert body["correlation_id"] == "corr-1"
    assert body["raw_payload"]["state"] == "dispatch_requested"


def test_maps_dispatch_failed_with_sparse_payload():
    body = build_reservation_dispatch_ingest(
        event_type=FAILED,
        source_event_id="evt-2",
        payload={
            "execution_request_ref": "dispatch-requested:manual_execution:mx-1",
            "reason": "nak",
        },
    )
    assert body["event_type"] == FAILED
    assert body["evaluation_id"] is None
    assert body["reservation_ids"] == []
    assert body["correlation_id"] is None
    assert body["raw_payload"]["reason"] == "nak"


def test_output_keys_match_the_ingest_endpoint_model():
    # The mapper's body must be exactly the fields the decision-service ingest endpoint accepts,
    # so the live relay can POST it verbatim. Keep the two contracts in lockstep.
    body = build_reservation_dispatch_ingest(
        event_type=REQUESTED, source_event_id="evt-3", payload={}
    )
    assert set(body) == {
        "source_event_id",
        "event_type",
        "evaluation_id",
        "reservation_ids",
        "execution_ref_type",
        "execution_ref_id",
        "correlation_id",
        "causation_id",
        "raw_payload",
    }


def test_rejects_unsupported_event_type_fail_closed():
    with pytest.raises(ValueError, match="UNSUPPORTED_DISPATCH_EVENT"):
        build_reservation_dispatch_ingest(
            event_type="irrigation.reservation.something_else",
            source_event_id="evt-4",
            payload={},
        )


def test_rejects_missing_source_event_id_fail_closed():
    with pytest.raises(ValueError, match="MISSING_SOURCE_EVENT_ID"):
        build_reservation_dispatch_ingest(event_type=REQUESTED, source_event_id="", payload={})


def test_supported_events_match_migration_check():
    migration = (
        ROOT / "services" / "decision-service" / "migrations" / "027_reservation_dispatch_inbox.sql"
    ).read_text(encoding="utf-8")
    for event in SUPPORTED_DISPATCH_EVENTS:
        assert event in migration, f"{event} must be in the inbox CHECK constraint"


# --- delivery != fulfillment governance guard ----------------------------------------------

MIGRATION = (
    ROOT / "services" / "decision-service" / "migrations" / "027_reservation_dispatch_inbox.sql"
).read_text(encoding="utf-8")
PERSISTENCE = (ROOT / "services" / "decision-service" / "persistence.py").read_text(
    encoding="utf-8"
)
MAIN = (ROOT / "services" / "decision-service" / "main.py").read_text(encoding="utf-8")


def _recorder_body() -> str:
    start = PERSISTENCE.index("async def record_reservation_dispatch_intent")
    nxt = PERSISTENCE.index("\nasync def create_execution_request", start)
    return PERSISTENCE[start:nxt]


def test_inbox_migration_does_not_touch_execution_requests():
    # Delivery-only: the inbox schema must not create or write the execution-request SoR.
    assert "decision_execution_requests" not in MIGRATION
    assert "CREATE TABLE IF NOT EXISTS decision_reservation_dispatch_inbox" in MIGRATION


def test_recorder_never_creates_an_execution_request():
    body = _recorder_body()
    assert "create_execution_request" not in body
    assert "decision_execution_requests" not in body


def test_inbox_is_deduped_and_append_only():
    assert "uq_reservation_inbox_tenant_event" in MIGRATION
    assert "ON CONFLICT (tenant_id, source_event_id) DO NOTHING" in PERSISTENCE
    assert "is append-preserving" in MIGRATION


def test_ingest_endpoint_is_fail_closed_in_mirror():
    start = MAIN.index('@app.post("/v1/reservation-dispatch-intents")')
    end = MAIN.index("\n\n\n", start)
    endpoint = MAIN[start:end]
    assert "if not sor_enabled():" in endpoint
    assert "status_code=503" in endpoint
    assert "record_reservation_dispatch_intent" in endpoint
