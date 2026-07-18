"""IRR-F01 Gate B-delivery (thin inbox) — decision-service reservation dispatch-intent inbox,
against real Postgres.

Certifies that a delivered reservation dispatch INTENT is recorded idempotently (dedup on
tenant+source_event_id), that a corrupted redelivery is rejected, that the delivery receipt is
append-preserving, that a consumer heartbeat advances — and CRUCIALLY that recording a delivery
does NOT create an execution_request (delivery ≠ fulfillment).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")

from persistence import (  # noqa: E402
    RESERVATION_INBOX_CONSUMER,
    record_reservation_dispatch_intent,
)

TENANT = "00000000-0000-0000-0000-0000000000b1"
OTHER_TENANT = "00000000-0000-0000-0000-0000000000b2"


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def _intent(**over):
    base = dict(
        evaluation_id="eval_" + uuid4().hex,
        reservation_ids=["res_" + uuid4().hex],
        execution_ref_type="manual_execution",
        execution_ref_id="mx-b",
        correlation_id=str(uuid4()),
        causation_id=None,
        raw_payload={"state": "dispatch_requested"},
    )
    base.update(over)
    return SimpleNamespace(**base)


async def _count_inbox(conn, tenant, event_id):
    return await conn.fetchval(
        "SELECT count(*) FROM decision_reservation_dispatch_inbox "
        "WHERE tenant_id=$1::uuid AND source_event_id=$2",
        tenant,
        event_id,
    )


def test_first_delivery_records_receipt_without_execution_request():
    async def go():
        event_id = "evt_" + uuid4().hex
        payload = _intent()
        res = await record_reservation_dispatch_intent(
            tenant_id=TENANT,
            source_event_id=event_id,
            event_type="irrigation.reservation.dispatch_requested",
            payload=payload,
        )
        assert res["status"] == "received"
        assert res["persisted"] is True and res["replay"] is False
        assert res["dispatch_state"] == "received" and res["receipt_id"].startswith("rcpt_")

        conn = await _connect()
        try:
            assert await _count_inbox(conn, TENANT, event_id) == 1
            # Delivery must NOT have created an execution_request.
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM decision_execution_requests "
                    "WHERE tenant_id=$1::uuid AND execution_request_id=$2",
                    TENANT,
                    res["inbox_id"],
                )
                == 0
            )
            # Heartbeat advanced for this consumer.
            hb = await conn.fetchrow(
                "SELECT last_event_id, processed_count FROM decision_consumer_heartbeats "
                "WHERE consumer_name=$1",
                RESERVATION_INBOX_CONSUMER,
            )
            assert hb is not None and hb["processed_count"] >= 1
        finally:
            await conn.close()

    _run(go())


def test_redelivery_is_idempotent_same_receipt_no_duplicate():
    async def go():
        event_id = "evt_" + uuid4().hex
        payload = _intent()
        first = await record_reservation_dispatch_intent(
            tenant_id=TENANT,
            source_event_id=event_id,
            event_type="irrigation.reservation.dispatch_requested",
            payload=payload,
        )
        second = await record_reservation_dispatch_intent(
            tenant_id=TENANT,
            source_event_id=event_id,
            event_type="irrigation.reservation.dispatch_requested",
            payload=payload,
        )
        assert second["status"] == "duplicate" and second["replay"] is True
        assert second["inbox_id"] == first["inbox_id"]
        assert second["receipt_id"] == first["receipt_id"]
        conn = await _connect()
        try:
            assert await _count_inbox(conn, TENANT, event_id) == 1
        finally:
            await conn.close()

    _run(go())


def test_same_event_different_payload_is_rejected_conflict():
    async def go():
        event_id = "evt_" + uuid4().hex
        await record_reservation_dispatch_intent(
            tenant_id=TENANT,
            source_event_id=event_id,
            event_type="irrigation.reservation.dispatch_requested",
            payload=_intent(evaluation_id="eval_A"),
        )
        clash = await record_reservation_dispatch_intent(
            tenant_id=TENANT,
            source_event_id=event_id,
            event_type="irrigation.reservation.dispatch_requested",
            payload=_intent(evaluation_id="eval_B"),
        )
        assert clash["status"] == "conflict"
        assert clash["reason"] == "source_event_payload_mismatch"
        conn = await _connect()
        try:
            assert await _count_inbox(conn, TENANT, event_id) == 1  # no second row
        finally:
            await conn.close()

    _run(go())


def test_dispatch_failed_records_failure_notice():
    async def go():
        event_id = "evt_" + uuid4().hex
        res = await record_reservation_dispatch_intent(
            tenant_id=TENANT,
            source_event_id=event_id,
            event_type="irrigation.reservation.dispatch_failed",
            payload=_intent(raw_payload={"reason": "actuator_nak"}),
        )
        assert res["status"] == "failure_notice" and res["dispatch_state"] == "failure_notice"

    _run(go())


def test_inbox_is_append_preserving():
    async def go():
        event_id = "evt_" + uuid4().hex
        await record_reservation_dispatch_intent(
            tenant_id=TENANT,
            source_event_id=event_id,
            event_type="irrigation.reservation.dispatch_requested",
            payload=_intent(),
        )
        conn = await _connect()
        try:
            import asyncpg

            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "DELETE FROM decision_reservation_dispatch_inbox "
                    "WHERE tenant_id=$1::uuid AND source_event_id=$2",
                    TENANT,
                    event_id,
                )
        finally:
            await conn.close()

    _run(go())


def test_dedup_is_per_tenant():
    async def go():
        event_id = "evt_" + uuid4().hex  # same event id, two tenants
        a = await record_reservation_dispatch_intent(
            tenant_id=TENANT,
            source_event_id=event_id,
            event_type="irrigation.reservation.dispatch_requested",
            payload=_intent(),
        )
        b = await record_reservation_dispatch_intent(
            tenant_id=OTHER_TENANT,
            source_event_id=event_id,
            event_type="irrigation.reservation.dispatch_requested",
            payload=_intent(),
        )
        assert a["status"] == "received" and b["status"] == "received"
        assert a["inbox_id"] != b["inbox_id"]

    _run(go())
