#!/usr/bin/env python3
"""Live JetStream round-trip for the canonical projection worker.

Creates one tenant-scoped salinity projection request, publishes an
identifiers-only event, waits for the registered worker to persist the
canonical row and outbox intent, then republishes the same event to prove
idempotency. The fixture is removed after verification.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

SUBJECT = "sahool.events.agronomy.projection.requested"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _wait_processed(conn: Any, request_id: uuid.UUID, timeout: float) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        row = await conn.fetchrow(
            """SELECT status, result_event_id, error_code
               FROM canonical_projection_requests
               WHERE request_id=$1""",
            request_id,
        )
        if row and row["status"] == "processed":
            return dict(row)
        if row and row["status"] == "failed":
            raise RuntimeError(f"projection request failed: {row['error_code']}")
        await asyncio.sleep(0.25)
    raise TimeoutError("worker did not process projection request before timeout")


async def main() -> None:
    import asyncpg

    import nats

    database_url = os.environ["DATABASE_URL"]
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    timeout = float(os.getenv("ROUNDTRIP_TIMEOUT_SECONDS", "20"))
    tenant_id = uuid.uuid4()
    field_id = uuid.uuid4()
    request_id = uuid.uuid4()
    inbound_event_id = uuid.uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    state_digest = _sha(f"salinity:{tenant_id}:{field_id}:{request_id}")

    payload = {
        "tenant_id": str(tenant_id),
        "field_id": str(field_id),
        "season_id": f"live-{request_id}",
        "crop_id": "wheat",
        "cultivar_id": None,
        "phenology_stage": "vegetative",
        "as_of": now.isoformat(),
        "status": "blocked",
        "soil_class": None,
        "water_risk": None,
        "sodium_hazard_class": None,
        "rsc_hazard_class": None,
        "effective_crop_threshold_ece_dsm": None,
        "estimated_relative_yield": None,
        "leaching_fraction": None,
        "leaching_feasible": None,
        "drainage_class": "unknown",
        "operational_recommendation_allowed": False,
        "limitations": ["LIVE_GATE_FIXTURE"],
        "evidence_digests": [],
        "state_digest": state_digest,
    }
    envelope = {
        "event_id": str(inbound_event_id),
        "event_type": "agronomy.projection.requested",
        "tenant_id": str(tenant_id),
        "payload": {"request_id": str(request_id)},
    }

    conn = await asyncpg.connect(database_url)
    nc = await nats.connect(nats_url, connect_timeout=5)
    try:
        await conn.execute("SELECT set_config('app.current_tenant',$1,false)", str(tenant_id))
        await conn.execute(
            """INSERT INTO canonical_projection_requests (
                 request_id, tenant_id, projection_type, field_id, season_id,
                 canonical_payload, evidence_payload
               ) VALUES ($1,$2,'salinity',$3,$4,$5::jsonb,'[]'::jsonb)""",
            request_id,
            tenant_id,
            str(field_id),
            payload["season_id"],
            json.dumps(payload, sort_keys=True),
        )

        await nc.publish(SUBJECT, json.dumps(envelope, sort_keys=True).encode("utf-8"))
        await nc.flush()
        first = await _wait_processed(conn, request_id, timeout)
        result_event_id = first["result_event_id"]
        if result_event_id is None:
            raise RuntimeError("worker processed request without result_event_id")

        event = await conn.fetchrow(
            """SELECT event_id, command_id, event_type, tenant_id
               FROM events WHERE event_id=$1""",
            result_event_id,
        )
        outbox_count = await conn.fetchval(
            "SELECT count(*) FROM event_outbox WHERE event_id=$1", result_event_id
        )
        if not event or event["command_id"] is not None:
            raise RuntimeError("projection event missing or carries a synthetic command_id")
        if event["event_type"] != "agronomy.salinity.projected":
            raise RuntimeError(f"unexpected projection event type: {event['event_type']}")
        if event["tenant_id"] != tenant_id or int(outbox_count) != 1:
            raise RuntimeError("projection event/outbox tenant or cardinality mismatch")

        await nc.publish(SUBJECT, json.dumps(envelope, sort_keys=True).encode("utf-8"))
        await nc.flush()
        await asyncio.sleep(1)
        replay_outbox_count = await conn.fetchval(
            "SELECT count(*) FROM event_outbox WHERE event_id=$1", result_event_id
        )
        state_count = await conn.fetchval(
            """SELECT count(*) FROM canonical_salinity_states
               WHERE tenant_id=$1 AND state_digest=$2""",
            tenant_id,
            state_digest,
        )
        if int(replay_outbox_count) != 1 or int(state_count) != 1:
            raise RuntimeError("replay created duplicate canonical state or outbox intent")

        print(
            json.dumps(
                {
                    "status": "passed",
                    "subject": SUBJECT,
                    "tenant_id": str(tenant_id),
                    "request_id": str(request_id),
                    "result_event_id": str(result_event_id),
                    "command_id": None,
                    "canonical_state_count": int(state_count),
                    "outbox_count": int(replay_outbox_count),
                },
                sort_keys=True,
            )
        )
    finally:
        try:
            await conn.execute("SELECT set_config('app.current_tenant',$1,false)", str(tenant_id))
            row = await conn.fetchrow(
                "SELECT result_event_id FROM canonical_projection_requests WHERE request_id=$1",
                request_id,
            )
            if row and row["result_event_id"]:
                await conn.execute("DELETE FROM events WHERE event_id=$1", row["result_event_id"])
            await conn.execute(
                "DELETE FROM canonical_salinity_states WHERE tenant_id=$1 AND state_digest=$2",
                tenant_id,
                state_digest,
            )
            await conn.execute(
                "DELETE FROM canonical_projection_requests WHERE request_id=$1", request_id
            )
        finally:
            await nc.drain()
            await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
