"""W3-01 — staging enablement of ``FEATURE_NATS_PUBLISHERS`` on real PostgreSQL + real JetStream.

What turning the flag on actually does, measured end to end with the production code
(``EventBus``/``emit_event`` ⇒ ``event_outbox`` ⇒ ``OutboxWorker`` ⇒
``make_jetstream_publisher`` ⇒ the declared ``sahool`` stream ⇒ durable consumers):

1. flag off: the event is held, and the backlog signal says enabling the flag replays it;
2. stream missing: the preflight fails and the relay gate does **not** start the worker, so
   the held row keeps all of its attempts (a missing stream would otherwise dead-letter the
   backlog within a minute); a direct publish attempt fails and is retried, not lost;
3. topology provisioned from the declaration: the preflight passes, the gate starts the relay,
   the row is delivered and the consumer receives it exactly once;
4. a crash after PubAck and before the row is marked ``sent`` (claim and mark roll back
   together): the replay is dropped by the JetStream duplicate window (``Nats-Msg-Id`` =
   ``event_id``) — no second stored message, no second delivery to the consumer. This holds
   only while the replay falls inside ``duplicate_window`` (120 s); a later replay is stored
   again and only consumer-side idempotency (``processed_events``) stops the duplicate.

Needs ``TEST_DATABASE_ADMIN_URL`` (or ``TEST_DATABASE_URL``) on a migrated database and a
``nats-server`` binary (``NATS_SERVER_BIN``). Skips with the reason otherwise, unless
``NATS_OUTBOX_LIVE_REQUIRED=1`` or ``NATS_OUTBOX_CERTIFICATION_REQUIRED=1`` (the name the CI
certification step and the lab runner key on), which turns a missing dependency, the
``asyncpg``/``nats`` client modules included, into a failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

REQUIRED = "1" in (
    os.getenv("NATS_OUTBOX_LIVE_REQUIRED"),
    os.getenv("NATS_OUTBOX_CERTIFICATION_REQUIRED"),
)
if REQUIRED:  # a missing client module is a failure, not a skip, when the proof is required
    import asyncpg

    import nats  # noqa: F401
else:
    asyncpg = pytest.importorskip("asyncpg")
    pytest.importorskip("nats")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or os.getenv("TEST_DATABASE_URL", "")
APP_DSN = os.getenv("TEST_DATABASE_URL", "")
NATS_BIN = os.getenv("NATS_SERVER_BIN") or shutil.which("nats-server")


async def _db_why() -> str:
    if not ADMIN_DSN:
        return "TEST_DATABASE_ADMIN_URL/TEST_DATABASE_URL not set"
    try:
        conn = await asyncpg.connect(ADMIN_DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 — any failure means "no database here"
        return f"{type(exc).__name__}"
    try:
        for table in ("events", "event_outbox", "processed_events", "outbox_delivery_attempts"):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_db_why()) or ("" if NATS_BIN else "no nats-server (NATS_SERVER_BIN)")
if _WHY and REQUIRED:
    raise RuntimeError(f"the live outbox proof is required and cannot run: {_WHY}")
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform_path() -> None:
    for path in (str(PLATFORM), str(ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Broker:
    """A throw-away JetStream server (no auth: identities are proven in the least-privilege suite)."""

    def __init__(self, tmp: Path):
        self.port = _free_port()
        self.log = tmp / "nats.log"
        self.proc = subprocess.Popen(
            [NATS_BIN, "-js", "-sd", str(tmp / "js"), "-a", "127.0.0.1", "-p", str(self.port)],
            stdout=self.log.open("w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )

    @property
    def url(self) -> str:
        return f"nats://127.0.0.1:{self.port}"

    async def ready(self) -> None:
        for _ in range(250):
            if self.proc.poll() is not None:
                break
            if "Server is ready" in self.log.read_text(encoding="utf-8", errors="replace"):
                return
            await asyncio.sleep(0.02)
        raise AssertionError(self.log.read_text(encoding="utf-8", errors="replace"))

    def stop(self) -> None:
        self.proc.terminate()
        self.proc.wait(5)


async def _emit(conn, tenant: str) -> uuid.UUID:
    """The real emission path: ``emit_event`` writes the event and its outbox row atomically."""
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
    return await conn.fetchval(
        "SELECT emit_event('season.closed', 'season', $1, $2::uuid, $3::jsonb, 'system')",
        f"season-{uuid.uuid4().hex[:10]}",
        tenant,
        json.dumps({"season_id": str(uuid.uuid4())}),
    )


async def _row(conn, event_id) -> dict:
    return dict(
        await conn.fetchrow(
            """SELECT o.outbox_id, o.event_id, o.nats_subject, o.retry_count, o.status,
                      o.last_error, e.event_type, e.entity_type, e.entity_id, e.tenant_id,
                      e.payload, e.occurred_at
               FROM event_outbox o JOIN events e ON e.event_id = o.event_id
               WHERE o.event_id = $1""",
            event_id,
        )
    )


async def _drain(queue: asyncio.Queue, wait: float) -> list:
    items = []
    try:
        while True:
            items.append(await asyncio.wait_for(queue.get(), wait))
    except TimeoutError:
        return items


def test_staging_enablement_holds_then_delivers_once_and_dedups_a_replay_in_the_window(tmp_path):
    _platform_path()
    from api.event_bus import OutboxWorker, outbox_backlog
    from workers.canonical_execution_learning_worker import subscribe_subjects

    import nats
    from shared import nats_stream_contract as contract
    from shared.broker_url import make_jetstream_publisher

    async def case():
        tenant = str(uuid.uuid4())
        admin = await asyncpg.connect(ADMIN_DSN)
        broker = _Broker(tmp_path)
        nc = None
        try:
            before = await outbox_backlog(admin, flag_enabled=False)
            event_id = await _emit(admin, tenant)
            assert event_id is not None, "emit_event returned no event id"

            # ① flag off: held, and the signal says the flag replays it.
            held = await outbox_backlog(admin, flag_enabled=False)
            assert held["held"] == before["held"] + 1, f"the new event is not counted: {held}"
            assert held["replay_on_enable"] == held["held"], f"replay count missing: {held}"
            assert any("will replay" in w for w in held["warnings"]), held["warnings"]
            if await admin.fetchval(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            ):
                assert held["scope"] == "all_tenants", f"admin probe mis-scoped: {held}"
            if APP_DSN and APP_DSN != ADMIN_DSN:
                app = await asyncpg.connect(APP_DSN)
                try:
                    scoped = await outbox_backlog(app, flag_enabled=False)
                finally:
                    await app.close()
                assert scoped["scope"] == "tenant_scoped_undercount", (
                    f"an RLS-bound probe must say it undercounts: {scoped}"
                )

            await broker.ready()
            nc = await nats.connect(broker.url, max_reconnect_attempts=0, connect_timeout=3)
            js = nc.jetstream()
            pool = await asyncpg.create_pool(ADMIN_DSN, min_size=1, max_size=2)
            worker = OutboxWorker(pool, make_jetstream_publisher(nc))

            # ② no stream: the preflight fails and the gate does not start the relay.
            state = contract.PreflightState()
            started: list[bool] = []

            async def start():
                started.append(True)

            assert not await state.gate(nc, start, url=broker.url, retry_s=3600), (
                "the relay started without a stream"
            )
            assert not started and state.result["status"] == "failed", state.result
            assert any(e.startswith("stream_info:") for e in state.result["errors"]), state.result
            await state.reset()
            row = await _row(admin, event_id)
            assert (row["status"], row["retry_count"]) == ("pending", 0), (
                f"a held row lost an attempt while the relay was gated: {row}"
            )
            # The retry path, directly: a publish with no stream fails and the row stays
            # replayable with the error recorded — not marked sent, not lost.
            await worker._send_one(None, row)
            row = await _row(admin, event_id)
            assert row["status"] == "pending" and row["retry_count"] == 1, row
            assert row["last_error"], f"the failure left no trace: {row}"

            # ③ provision from the declaration, bind the real consumers, preflight passes.
            assert (await contract.ensure_stream(js, apply=True))["action"] == "created"
            received: asyncio.Queue = asyncio.Queue()

            async def on_learning(msg):
                await received.put(json.loads(msg.data)["event_id"])
                await msg.ack()

            await subscribe_subjects(
                js, durable_base="canonical-execution-learning-v1", callback=on_learning
            )
            domain = await js.subscribe(
                "sahool.events.>", durable="notif_domain_events", manual_ack=True
            )
            assert await state.gate(nc, start, url=broker.url, retry_s=3600), state.result
            assert started == [True], "a passing preflight did not start the relay"
            assert state.result["stream"]["drift"] == [], state.result

            row = await _row(admin, event_id)
            await worker._send_one(None, row)
            row = await _row(admin, event_id)
            assert row["status"] == "sent", f"delivery did not mark the row sent: {row}"
            got = await _drain(received, 2.0)
            assert got == [str(event_id)], f"expected exactly one delivery, got {got}"
            msg = await domain.next_msg(timeout=2)
            assert json.loads(msg.data)["event_id"] == str(event_id), "domain consumer missed it"
            await msg.ack()
            stored = (await js.stream_info(contract.STREAM_NAME)).state.messages
            attempts = await admin.fetch(
                "SELECT outcome FROM outbox_delivery_attempts WHERE outbox_id = $1"
                " ORDER BY attempt_no",
                row["outbox_id"],
            )
            assert [a["outcome"] for a in attempts] == ["failed", "published"], attempts

            # ④ crash after PubAck, before TX-2 committed: claim and 'sent' roll back together.
            await admin.execute("DELETE FROM processed_events WHERE event_id = $1", event_id)
            await admin.execute(
                "UPDATE event_outbox SET status = 'pending', sent_at = NULL WHERE event_id = $1",
                event_id,
            )
            await worker._send_one(None, await _row(admin, event_id))
            assert (await _row(admin, event_id))["status"] == "sent", "replay not finalised"
            assert (await js.stream_info(contract.STREAM_NAME)).state.messages == stored, (
                "the replay was stored a second time — Nats-Msg-Id dedup did not apply"
            )
            assert await _drain(received, 1.5) == [], "the consumer saw a duplicate side effect"

            after = await outbox_backlog(admin, flag_enabled=True)
            assert after["held"] == before["held"], f"the delivered event is still held: {after}"
            await pool.close()
        finally:
            if nc is not None:
                await nc.close()
            broker.stop()
            await admin.close()

    asyncio.run(case())
