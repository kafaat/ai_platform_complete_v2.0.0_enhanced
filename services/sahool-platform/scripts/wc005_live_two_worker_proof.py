#!/usr/bin/env python3
"""WC-005 live two-worker Outbox proof.

Uses the exact OutboxWorker shipped in the pinned deployment, real PostgreSQL,
and real NATS. All mutable proof rows live in a dedicated disposable schema.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import asyncpg
import nats

sys.path.insert(0, "/app")
from api.event_bus import OutboxWorker  # noqa: E402


async def role_info(url: str) -> dict:
    conn = await asyncpg.connect(url)
    try:
        row = await conn.fetchrow(
            "SELECT current_user, rolsuper, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        )
        return dict(row)
    finally:
        await conn.close()


async def main() -> None:
    app_url = os.environ["DATABASE_URL"]
    jobs_url = os.environ["JOBS_DATABASE_URL"]
    nats_url = os.environ["NATS_URL"]
    proof_url = os.environ.get("WC005_PROOF_DATABASE_URL", jobs_url)

    app_role = await role_info(app_url)
    jobs_role = await role_info(jobs_url)
    if app_role["rolsuper"] or app_role["rolbypassrls"]:
        raise RuntimeError(f"unsafe app DB role: {app_role}")
    if jobs_role["rolsuper"]:
        raise RuntimeError(f"jobs role must not be superuser: {jobs_role}")
    if not jobs_role["rolbypassrls"]:
        raise RuntimeError(f"jobs role lacks BYPASSRLS required by OutboxWorker: {jobs_role}")

    schema = "wc005_" + uuid.uuid4().hex[:12]
    event_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    subject = "wc005.outbox." + uuid.uuid4().hex
    setup = await asyncpg.connect(proof_url)
    nc = None
    pool = None
    sub = None
    try:
        await setup.execute(f'CREATE SCHEMA "{schema}"')
        await setup.execute(f'''
            SET search_path TO "{schema}";
            CREATE TABLE events (
                event_id uuid PRIMARY KEY,
                event_type text NOT NULL,
                entity_type text NOT NULL,
                entity_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                payload jsonb NOT NULL,
                occurred_at timestamptz NOT NULL DEFAULT now()
            );
            CREATE TABLE event_outbox (
                outbox_id bigserial PRIMARY KEY,
                event_id uuid NOT NULL REFERENCES events(event_id),
                nats_subject text NOT NULL,
                status text NOT NULL DEFAULT 'pending',
                retry_count int NOT NULL DEFAULT 0,
                last_attempt_at timestamptz,
                sent_at timestamptz,
                last_error text,
                created_at timestamptz NOT NULL DEFAULT now(),
                claim_token uuid,
                claimed_by text,
                lease_until timestamptz
            );
            CREATE TABLE processed_events (
                event_id uuid PRIMARY KEY,
                consumer text NOT NULL
            );
            CREATE TABLE outbox_delivery_attempts (
                id bigserial PRIMARY KEY,
                outbox_id bigint NOT NULL,
                tenant_id uuid,
                attempt_no int NOT NULL,
                subject text NOT NULL,
                outcome text NOT NULL,
                error text,
                created_at timestamptz NOT NULL DEFAULT now()
            );
        ''')
        await setup.execute(f'SET search_path TO "{schema}"')
        await setup.execute(
            """INSERT INTO events
               (event_id,event_type,entity_type,entity_id,tenant_id,payload)
               VALUES ($1,'wc005.live.two_worker','field',$2,$3,$4::jsonb)""",
            event_id,
            entity_id,
            tenant_id,
            json.dumps({"probe": "WC-005", "expected": "exactly_once_claim"}),
        )
        await setup.execute(
            "INSERT INTO event_outbox (event_id,nats_subject) VALUES ($1,$2)",
            event_id,
            subject,
        )

        async def init_conn(conn):
            await conn.execute(f'SET search_path TO "{schema}"')

        pool = await asyncpg.create_pool(proof_url, min_size=2, max_size=4, init=init_conn)
        nc = await nats.connect(nats_url, connect_timeout=5, max_reconnect_attempts=2)
        received: list[bytes] = []

        async def on_msg(msg):
            received.append(msg.data)

        sub = await nc.subscribe(subject, cb=on_msg)
        await nc.flush()

        async def publish(s: str, payload: bytes) -> None:
            await nc.publish(s, payload)
            await nc.flush()

        w1 = OutboxWorker(pool, publish, batch_size=1)
        w2 = OutboxWorker(pool, publish, batch_size=1)
        processed = await asyncio.gather(w1._process_batch(), w2._process_batch())
        await asyncio.sleep(0.5)

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status,retry_count,claim_token,claimed_by,lease_until "
                "FROM event_outbox WHERE event_id=$1", event_id
            )
            attempts = await conn.fetchval(
                "SELECT count(*) FROM outbox_delivery_attempts WHERE outbox_id="
                "(SELECT outbox_id FROM event_outbox WHERE event_id=$1)", event_id
            )
            claims = await conn.fetchval(
                "SELECT count(*) FROM processed_events WHERE event_id=$1", event_id
            )

        result = {
            "schema": schema,
            "source_sha": os.getenv("SAHOOL_GIT_SHA"),
            "app_role": app_role,
            "jobs_role": jobs_role,
            "workers_processed": processed,
            "nats_messages": len(received),
            "outbox_status": row["status"],
            "retry_count": row["retry_count"],
            "claim_token_cleared": row["claim_token"] is None,
            "claimed_by_cleared": row["claimed_by"] is None,
            "lease_cleared": row["lease_until"] is None,
            "delivery_attempts": attempts,
            "processed_event_claims": claims,
        }
        print("WC005_LIVE_PROOF " + json.dumps(result, sort_keys=True), flush=True)

        assert sorted(processed) == [0, 1], result
        assert len(received) == 1, result
        assert row["status"] == "sent", result
        assert row["retry_count"] == 0, result
        assert row["claim_token"] is None and row["claimed_by"] is None and row["lease_until"] is None, result
        assert attempts == 1, result
        assert claims == 1, result
        print("WC005_LIVE_TWO_WORKER_PASS", flush=True)
    finally:
        if sub is not None:
            await sub.unsubscribe()
        if nc is not None:
            await nc.close()
        if pool is not None:
            await pool.close()
        try:
            await setup.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await setup.close()


if __name__ == "__main__":
    asyncio.run(main())
