"""Real JetStream overlap, checkpoint preservation and receipt serialization.

CI requires both dependencies; local service-free unit runs exclude this suite.
The only provider is an in-process stub; no real notification is sent.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import pytest
from nats.js.api import ConsumerConfig, StreamConfig
from nats.js.errors import Error, NotFoundError

import nats
from shared import notification_consumers as consumers

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]
SUBJECT, LEGACY = consumers.SUBSCRIPTIONS[6]
TENANT = "11111111-1111-1111-1111-111111111111"


def dependency(value, name):
    if not value:
        if os.getenv("NOTIFICATION_ROLLOUT_CERTIFICATION_REQUIRED") == "1":
            pytest.fail(f"Required notification rollout dependency missing: {name}")
        pytest.skip(f"Set {name} to run real-service notification certification")
    return value


@pytest.fixture
async def broker(tmp_path):
    binary = dependency(
        os.getenv("NOTIFICATION_TEST_NATS_SERVER") or shutil.which("nats-server"),
        "NOTIFICATION_TEST_NATS_SERVER",
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (tmp_path / "nats.log").open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [binary, "-js", "-a", "127.0.0.1", "-p", str(port), "-sd", str(tmp_path / "data")],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        clients = []

        async def connect():
            nc = await nats.connect(
                f"nats://127.0.0.1:{port}", connect_timeout=1, max_reconnect_attempts=0
            )
            clients.append(nc)
            return nc

        try:
            for _ in range(100):
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    if proc.poll() is not None:
                        pytest.fail((tmp_path / "nats.log").read_text(encoding="utf-8"))
                    await asyncio.sleep(0.02)
            nc = await connect()
            js = nc.jetstream()
            await js.add_stream(StreamConfig(name="sahool", subjects=["sahool.>"]))
            legacy = {}
            for subject, name in consumers.SUBSCRIPTIONS:
                legacy[name] = await js.subscribe(
                    subject,
                    durable=name,
                    manual_ack=True,
                    config=ConsumerConfig(ack_wait=120, max_deliver=-1),
                )
            yield SimpleNamespace(nc=nc, js=js, legacy=legacy, connect=connect)
        finally:
            for client in clients:
                await client.close()
            proc.terminate()
            await asyncio.to_thread(proc.wait, 5)


async def bind(nc, name=LEGACY, subject=SUBJECT):
    js = nc.jetstream()
    info = await js.consumer_info("sahool", consumers.queue_name(name))
    consumers.validate_queue(info.config, subject, name)
    sub = await js.subscribe_bind(
        stream="sahool", consumer=consumers.queue_name(name), config=info.config, manual_ack=True
    )
    await nc.flush()
    return sub


@pytest.mark.asyncio
async def test_overlap_replays_unacked_floor_without_changing_legacy(broker):
    old = broker.legacy[LEGACY]
    second = await broker.connect()
    with pytest.raises(Error, match="already bound"):
        await second.jetstream().subscribe(SUBJECT, durable=LEGACY, manual_ack=True)
    for index in (1, 2, 3):
        await broker.js.publish(SUBJECT, str(index).encode())
    messages = [await old.next_msg(timeout=2) for _ in range(3)]
    await messages[0].ack_sync()
    await messages[2].ack_sync()
    before = await broker.js.consumer_info("sahool", LEGACY)
    assert before.ack_floor.stream_seq == 1
    assert before.delivered.stream_seq == 3
    plan = await consumers.build_plan(broker.js)
    assert plan["consumers"][6]["start_sequence"] == 2
    await broker.js.publish(SUBJECT, b"4")  # Traffic can arrive after the plan.
    await consumers.apply_plan(broker.nc, plan)
    new = await bind(second)
    replay = [await new.next_msg(timeout=2) for _ in range(3)]
    assert [m.data for m in replay] == [b"2", b"3", b"4"]
    for msg in replay:
        await msg.ack_sync()
    # Re-applying the SAME saved plan cannot reset an advanced queue cursor.
    await consumers.apply_plan(broker.nc, plan)
    info = await broker.js.consumer_info("sahool", consumers.queue_name(LEGACY))
    assert info.ack_floor.stream_seq == 4
    after = await broker.js.consumer_info("sahool", LEGACY)
    assert after.created == before.created
    assert after.config == before.config
    assert after.ack_floor == before.ack_floor
    assert after.num_ack_pending >= 1


@pytest.mark.asyncio
async def test_queue_worker_loss_redelivers_to_survivor(broker, monkeypatch):
    # Speed up the real broker timer; production config remains 120 seconds.
    monkeypatch.setattr(consumers, "ACK_WAIT", 0.5)
    await consumers.apply_plan(broker.nc, await consumers.build_plan(broker.js))
    first = await broker.connect()
    first_sub = await bind(first)
    await broker.js.publish(SUBJECT, b"owed-after-process-loss")
    owed = await first_sub.next_msg(timeout=2)
    assert owed.metadata.num_delivered == 1
    survivor = await bind(await broker.connect())
    await first.close()  # No ACK or NAK: actual lost worker with work in flight.
    redelivered = await survivor.next_msg(timeout=3)
    assert redelivered.metadata.sequence.stream == owed.metadata.sequence.stream
    assert redelivered.metadata.num_delivered >= 2
    await redelivered.ack_sync()


@pytest.mark.asyncio
async def test_two_queue_workers_share_one_delivery(broker):
    await consumers.apply_plan(broker.nc, await consumers.build_plan(broker.js))
    workers = [await bind(await broker.connect()) for _ in range(2)]
    for i in range(12):
        await broker.js.publish(SUBJECT, str(i).encode())

    async def drain(sub):
        received = []
        while True:
            try:
                msg = await sub.next_msg(timeout=0.2)
            except nats.errors.TimeoutError:
                return received
            received.append(msg.metadata.sequence.stream)
            await msg.ack_sync()

    results = await asyncio.gather(*(drain(sub) for sub in workers))
    all_sequences = sum(results, [])
    assert len(all_sequences) == len(set(all_sequences)) == 12
    assert all(results), "Both simultaneously bound workers must receive real work"


@pytest.mark.asyncio
async def test_recreated_legacy_and_missing_history_rejected_before_writes(broker):
    plan = await consumers.build_plan(broker.js)
    await broker.js.delete_consumer("sahool", LEGACY)
    await broker.js.subscribe(SUBJECT, durable=LEGACY, manual_ack=True)
    with pytest.raises(ValueError, match="checkpoint_invalid"):
        await consumers.apply_plan(broker.nc, plan)
    with pytest.raises(NotFoundError):
        await broker.js.consumer_info("sahool", consumers.queue_name(LEGACY))
    await broker.js.publish(SUBJECT, b"history")
    await broker.js.purge_stream("sahool")
    with pytest.raises(ValueError, match="complete_stream_history"):
        await consumers.build_plan(broker.js)


@pytest.mark.asyncio
async def test_create_race_never_updates_existing_consumer(broker):
    plan = await consumers.build_plan(broker.js)

    class RacingClient:
        connected_server_version = broker.nc.connected_server_version

        def jetstream(self):
            return broker.js

        async def request(self, subject, payload, **kwargs):
            request = json.loads(payload)
            config = ConsumerConfig.from_response(request["config"])
            config.ack_wait = 999
            await broker.js.add_consumer("sahool", config)
            return await broker.nc.request(subject, payload, **kwargs)

    with pytest.raises(RuntimeError, match="consumer_create_rejected"):
        await consumers.apply_plan(RacingClient(), plan)
    info = await broker.js.consumer_info("sahool", consumers.queue_name("notif_satellite"))
    assert info.config.ack_wait == 999


@pytest.mark.asyncio
async def test_older_server_cannot_silently_ignore_create_only_action():
    client = SimpleNamespace(
        connected_server_version=SimpleNamespace(major=2, minor=9, patch=0, prerelease=""),
        request=AsyncMock(),
    )
    with pytest.raises(ValueError, match="tested_nats_2_15"):
        await consumers.apply_plan(client, {})
    client.request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"max_age": 300}, {"allow_msg_ttl": True}, {"max_msgs": 100}])
async def test_expiring_retention_is_not_a_migration_proof(broker, change):
    stream = await broker.js.stream_info("sahool")
    for key, value in change.items():
        setattr(stream.config, key, value)
    await broker.js.update_stream(stream.config)
    with pytest.raises(ValueError, match="unlimited_retention"):
        await consumers.build_plan(broker.js)


def load_agent(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "agents/notification/agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProbeConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def fetchval(self, query):
        return 1


@pytest.mark.asyncio
async def test_ready_requires_all_provisioned_bindings_and_rejects_drift(broker):
    agent = load_agent("notification_readiness_rollout")
    agent.CONSUMER_MODE = "queue_v1"
    agent._nc = await broker.connect()
    agent._js = agent._nc.jetstream()
    agent.DB_URL = "configured-for-probe"
    agent.get_pool = AsyncMock(return_value=SimpleNamespace(acquire=ProbeConnection))
    await agent._ensure_subscriptions()
    with pytest.raises(agent.HTTPException) as exc:
        await agent.readyz()
    assert exc.value.status_code == 503
    assert len(exc.value.detail["missing"]) == 9
    with pytest.raises(NotFoundError):
        await broker.js.consumer_info("sahool", consumers.queue_name(LEGACY))
    await consumers.apply_plan(broker.nc, await consumers.build_plan(broker.js))
    await agent._ensure_subscriptions()
    assert (await agent.readyz())["status"] == "ready"
    info = await broker.js.consumer_info("sahool", consumers.queue_name(LEGACY))
    info.config.max_deliver = 1
    await broker.js.add_consumer("sahool", info.config)
    with pytest.raises(agent.HTTPException) as exc:
        await agent.readyz()
    assert exc.value.detail["missing"] == [LEGACY]
    await agent._ensure_subscriptions()
    assert LEGACY not in agent._subscriptions


@pytest.mark.asyncio
async def test_real_postgres_serializes_old_and_new_stream_receipts(broker):
    url = dependency(os.getenv("NOTIFICATION_TEST_DATABASE_URL"), "NOTIFICATION_TEST_DATABASE_URL")
    admin = await asyncpg.connect(url)
    await admin.execute(
        (ROOT / "migrations/v83_notification_delivery.sql").read_text(encoding="utf-8")
    )
    # The receipt is written as a real restricted role, with FORCE RLS active.
    await admin.execute("CREATE ROLE notification_rollout_test NOLOGIN")
    await admin.execute("GRANT USAGE ON SCHEMA public TO notification_rollout_test")
    await admin.execute(
        "GRANT SELECT, INSERT, UPDATE ON notification_delivery TO notification_rollout_test"
    )

    async def restricted(conn):
        await conn.execute("SET ROLE notification_rollout_test")

    pool = await asyncpg.create_pool(url, min_size=2, max_size=2, setup=restricted)
    calls = []
    started, release = asyncio.Event(), asyncio.Event()
    completions = asyncio.Queue()

    async def provider():
        calls.append("stub-provider")
        started.set()
        await release.wait()
        return True

    async def handler(msg):
        agent = load_agent(f"notification_receipt_{msg.metadata.consumer}")
        agent.get_pool = AsyncMock(return_value=pool)

        async def dispatch(data):
            await agent._deliver_channel(data, "email", provider)

        agent.dispatch = dispatch
        await agent.handle_msg(msg)
        await completions.put(msg.metadata.consumer)

    try:
        await consumers.apply_plan(broker.nc, await consumers.build_plan(broker.js))
        await broker.legacy[LEGACY].unsubscribe()
        await broker.nc.flush()
        await broker.js.subscribe(SUBJECT, durable=LEGACY, cb=handler, manual_ack=True)
        second = await broker.connect()
        info = await second.jetstream().consumer_info("sahool", consumers.queue_name(LEGACY))
        await second.jetstream().subscribe_bind(
            stream="sahool",
            consumer=consumers.queue_name(LEGACY),
            config=info.config,
            cb=handler,
            manual_ack=True,
        )
        await second.flush()
        await broker.js.publish(SUBJECT, json.dumps({"tenant_id": TENANT, "user_id": "7"}).encode())
        await asyncio.wait_for(started.wait(), 5)
        for _ in range(100):
            blocked = await admin.fetchval(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname=current_database() AND wait_event_type='Lock'"
            )
            if blocked:
                break
            await asyncio.sleep(0.02)
        assert blocked, "The other generation must actually wait for the receipt transaction"
        assert calls == ["stub-provider"]
        release.set()
        completed = [await asyncio.wait_for(completions.get(), 5) for _ in range(2)]
        assert set(completed) == {LEGACY, consumers.queue_name(LEGACY)}
        assert calls == ["stub-provider"]
        rows = await admin.fetch("SELECT alert_key, status FROM notification_delivery")
        assert [dict(row) for row in rows] == [
            {
                "alert_key": "notification:sahool:1:user:7",
                "status": "sent",
            }
        ]
    finally:
        release.set()
        await pool.close()
        await admin.execute("DROP OWNED BY notification_rollout_test")
        await admin.execute("DROP ROLE notification_rollout_test")
        await admin.close()
