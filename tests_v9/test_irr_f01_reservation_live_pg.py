"""IRR-F01 — live PostgreSQL Gate A for the capacity/reservation slice.

Runs only under ``pytest -m integration`` and skips when a live database or a
NOBYPASSRLS app role is unavailable. It drives the REAL adapter
(``reserve_and_request_dispatch_db``) over the REAL v195/v196 tables to certify
what CI cannot: FORCE RLS isolation, WITH CHECK write fail-closed, transactional
advisory-lock serialization, exclusive/shared admission, and rollback safety.

Requires (env):
  TEST_DATABASE_URL        — app-role DSN (NOSUPERUSER, NOBYPASSRLS, NOINHERIT), TCP.
  TEST_DATABASE_ADMIN_URL  — owner/superuser DSN used ONLY to seed dependency rows.
                             MANDATORY under IRR_F01_CERTIFICATION_REQUIRED=1; dev runs may
                             omit it and fall back to TEST_DATABASE_URL.
  IRR_F01_CERTIFICATION_REQUIRED=1 — turn every skip (no DB, no driver, no admin DSN, wrong
                             role, missing migration) into a HARD failure; no false green.
The database must already have migrations through v196 applied.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

# When IRR_F01_CERTIFICATION_REQUIRED=1 the certification job is asserting that Gate A/B1
# actually EXECUTE — so an unavailable DB, missing migrations, a superuser/BYPASSRLS role, OR
# a missing driver become HARD FAILURES instead of a green-but-skipped false certification.
CERTIFICATION_REQUIRED = os.getenv("IRR_F01_CERTIFICATION_REQUIRED") == "1"

# A plain importorskip would let a certification run pass green with asyncpg absent — the very
# false-green the cert flag forbids. Under the flag, a missing driver must raise, not skip.
try:
    import asyncpg
except ImportError:
    if CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

pytestmark = pytest.mark.integration

APP_DSN = os.getenv("TEST_DATABASE_URL")
# The admin DSN seeds dependency rows (projects/nodes) with BYPASSRLS. In certification mode it
# is MANDATORY: silently falling back to the app DSN would run admin seeds through the restricted
# role with no app.current_tenant, failing the RLS WITH CHECK with a raw, undiagnosed error and
# defeating the very role-separation the gate exists to prove. Dev runs may still fall back.
_ADMIN_ENV = os.getenv("TEST_DATABASE_ADMIN_URL")
ADMIN_DSN = _ADMIN_ENV or APP_DSN

CORE_TABLES = (
    "hydraulic_capacity_evaluations",
    "irrigation_resource_reservations",
    "irrigation_resource_reservation_events",
)


def _skip_or_fail(message: str) -> None:
    if CERTIFICATION_REQUIRED:
        pytest.fail(message)
    pytest.skip(message)


def _adapter():
    import sys
    from pathlib import Path

    platform = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
    if str(platform) not in sys.path:
        sys.path.insert(0, str(platform))
    from api import irrigation_capacity_reservation as kernel
    from api import irrigation_reservation_adapter as adapter

    return adapter, kernel


class _Port:
    async def request_dispatch(self, conn, **kw):
        return "req-live"

    async def mark_dispatch_failed(self, conn, **kw):
        return None


@pytest.fixture
async def live():
    if not APP_DSN:
        _skip_or_fail("TEST_DATABASE_URL unset")
    # Fail-closed on a missing admin DSN under certification — never silently seed admin rows
    # through the restricted app role (that would fail RLS WITH CHECK with a raw error).
    if _ADMIN_ENV is None and CERTIFICATION_REQUIRED:
        _skip_or_fail("TEST_DATABASE_ADMIN_URL unset — certification requires a distinct admin DSN")
    try:
        app = await asyncpg.connect(APP_DSN)
    except Exception as exc:  # noqa: BLE001
        _skip_or_fail(f"PostgreSQL unavailable: {type(exc).__name__}")
        return
    # Skip when connected as a superuser/bypassrls role — RLS asserts need a real app role.
    is_super = await app.fetchval("select current_setting('is_superuser')")
    bypass = await app.fetchval("select rolbypassrls from pg_roles where rolname = current_user")
    inherit = await app.fetchval("select rolinherit from pg_roles where rolname = current_user")
    for table in CORE_TABLES:
        if await app.fetchval("select to_regclass($1)", table) is None:
            await app.close()
            _skip_or_fail(f"{table} absent — migrate to v196 first")
    if is_super == "on" or bypass:
        await app.close()
        _skip_or_fail("connect as a NOSUPERUSER/NOBYPASSRLS app role to certify RLS")
    # NOINHERIT is part of the declared restricted-role contract; prove it literally.
    if inherit:
        await app.close()
        _skip_or_fail("app role must be NOINHERIT to certify the restricted-role contract")

    try:
        admin = await asyncpg.connect(ADMIN_DSN)
    except Exception as exc:  # noqa: BLE001
        await app.close()
        _skip_or_fail(
            f"admin DSN ({'TEST_DATABASE_ADMIN_URL' if _ADMIN_ENV else 'fallback'}) "
            f"unavailable: {type(exc).__name__}"
        )
        return
    tenant = uuid4()
    project = uuid4()
    node1 = uuid4()
    node2 = uuid4()
    await admin.execute(
        "insert into irrigation_projects(id, tenant_id, name) values ($1,$2,$3)",
        project,
        tenant,
        "irr-f01-cert",
    )
    for node, kind in ((node1, "pump"), (node2, "valve")):
        await admin.execute(
            "insert into irrigation_hydraulic_nodes(id, tenant_id, project_id, node_type, elevation_m) "
            "values ($1,$2,$3,$4,$5)",
            node,
            tenant,
            project,
            kind,
            0,
        )
    ctx = {"app": app, "tenant": tenant, "project": project, "n1": node1, "n2": node2}
    try:
        yield ctx
    finally:
        # Shared-DB-safe teardown: every statement is tenant-scoped and best-effort, and
        # there is NO destructive TRUNCATE — this certification runs against the SHARED CI
        # integration database, so it must never wipe another test's data. The reservation
        # event log is DB-enforced append-only and every reservation FK is ON DELETE
        # RESTRICT, so the reservation/evaluation/node/project rows for this random
        # (RLS-isolated) tenant are intentionally left behind — harmless. Only the freely
        # deletable rows are removed; the outbox is cascaded by the events delete.
        async def _try(sql: str, *args: object) -> None:
            try:
                await admin.execute(sql, *args)
            except asyncpg.PostgresError:
                pass

        if await admin.fetchval("select to_regclass('events')") is not None:
            await _try("delete from events where tenant_id = $1", tenant)
        await _try("delete from irrigation_hydraulic_nodes where tenant_id = $1", tenant)
        await _try("delete from irrigation_projects where id = $1", project)
        await admin.close()
        await app.close()


def _req(kernel, node, policy, flow, cap):
    return kernel_ResourceRequest(kernel, node, policy, flow, cap)


def kernel_ResourceRequest(kernel, node, policy, flow, cap):
    adapter, _ = _adapter()
    return adapter.ResourceRequest(
        resource_node_id=node,
        policy=kernel.ResourcePolicy(policy),
        reserved_flow_m3h=Decimal(flow),
        derated_capacity_m3h=None if cap is None else Decimal(cap),
    )


# Anchored one hour in the FUTURE (minute-rounded) so the window can never rot into the past
# and trip a not-in-the-past guard on a later run — deterministic within a single test session.
START = (datetime.now(UTC) + timedelta(hours=1)).replace(second=0, microsecond=0)
END = START + timedelta(minutes=45)


async def test_gate_a_reservation_over_live_postgres(live):
    adapter, kernel = _adapter()
    app, tenant, project, n1, n2 = (
        live["app"],
        live["tenant"],
        live["project"],
        live["n1"],
        live["n2"],
    )

    # A1/A-happy: the real adapter persists evaluation + reservation + event atomically.
    async with app.transaction():
        await adapter.reserve_and_request_dispatch_db(
            app,
            tenant_id=tenant,
            project_id=project,
            requested_start=START,
            requested_end=END,
            resources=[_req(kernel, n1, "shared_capacity", "180", "300")],
            execution_ref_type="manual_execution",
            execution_ref_id="mx-1",
            calculation_model_version="v1",
            execution_port=_Port(),
            correlation_id=tenant,
        )
    await app.execute("select set_config('app.current_tenant', $1, false)", str(tenant))
    assert await app.fetchval("select count(*) from irrigation_resource_reservations") == 1
    assert await app.fetchval("select count(*) from irrigation_resource_reservation_events") == 1

    # A3: RLS read isolation — wrong/empty context sees nothing.
    await app.execute("select set_config('app.current_tenant', $1, false)", str(uuid4()))
    assert await app.fetchval("select count(*) from irrigation_resource_reservations") == 0
    await app.execute("select set_config('app.current_tenant', '', false)")
    assert await app.fetchval("select count(*) from irrigation_resource_reservations") == 0

    # A3: WITH CHECK write fail-closed — insert tenant row under a foreign context is refused.
    await app.execute("select set_config('app.current_tenant', $1, false)", str(tenant))
    eid = await app.fetchval("select evaluation_id from hydraulic_capacity_evaluations limit 1")
    await app.execute("select set_config('app.current_tenant', $1, false)", str(uuid4()))
    with pytest.raises(asyncpg.PostgresError) as rls_exc:
        await app.execute(
            "insert into irrigation_resource_reservations(tenant_id,project_id,evaluation_id,"
            "execution_ref_type,execution_ref_id,resource_node_id,resource_policy,reserved_flow_m3h,"
            "active_interval,idempotency_key) values($1,$2,$3,'manual_execution','x',$4,"
            "'shared_capacity',1,tstzrange($5,$6,'[)'),'kx')",
            tenant,
            project,
            eid,
            n1,
            START,
            END,
        )
    # Prove the refusal came from the RLS policy (insufficient_privilege), not an incidental
    # FK/connection error — a WITH CHECK violation raises SQLSTATE 42501.
    assert rls_exc.value.sqlstate == "42501"

    # A6: exclusive overlap on the already-reserved node is refused.
    with pytest.raises(adapter.CapacityNotAdmissible) as ex:
        async with app.transaction():
            await adapter.reserve_and_request_dispatch_db(
                app,
                tenant_id=tenant,
                project_id=project,
                requested_start=START + timedelta(minutes=10),
                requested_end=END,
                resources=[_req(kernel, n1, "exclusive", "10", None)],
                execution_ref_type="manual_execution",
                execution_ref_id="mx-e",
                calculation_model_version="v1",
                execution_port=_Port(),
                correlation_id=tenant,
            )
    assert ex.value.admission.blocking_code == "RESOURCE_CONFLICT"

    # A7: shared overcommit on peak (existing 180 + 180 > cap 300) is refused.
    with pytest.raises(adapter.CapacityNotAdmissible) as ex2:
        async with app.transaction():
            await adapter.reserve_and_request_dispatch_db(
                app,
                tenant_id=tenant,
                project_id=project,
                requested_start=START,
                requested_end=END,
                resources=[_req(kernel, n1, "shared_capacity", "180", "300")],
                execution_ref_type="manual_execution",
                execution_ref_id="mx-o",
                calculation_model_version="v1",
                execution_port=_Port(),
                correlation_id=tenant,
            )
    assert ex2.value.admission.blocking_code == "CONCURRENT_LOAD_EXCEEDED"

    # A8: a rolled-back reservation leaves no phantom.
    with pytest.raises(RuntimeError):
        async with app.transaction():
            await adapter.reserve_and_request_dispatch_db(
                app,
                tenant_id=tenant,
                project_id=project,
                requested_start=START,
                requested_end=END,
                resources=[_req(kernel, n2, "shared_capacity", "50", "300")],
                execution_ref_type="manual_execution",
                execution_ref_id="mx-r",
                calculation_model_version="v1",
                execution_port=_Port(),
                correlation_id=tenant,
                idempotency_key="ROLL",
            )
            raise RuntimeError("force rollback")
    await app.execute("select set_config('app.current_tenant', $1, false)", str(tenant))
    assert (
        await app.fetchval(
            "select count(*) from irrigation_resource_reservations where idempotency_key='ROLL'"
        )
        == 0
    )


async def test_gate_a_two_connection_advisory_lock_serializes(live):
    adapter, kernel = _adapter()
    tenant, n1 = live["tenant"], live["n1"]
    key = kernel.advisory_lock_key(
        kernel.ResourceRef(tenant, "hydraulic_node", n1, kernel.ResourcePolicy.SHARED_CAPACITY)
    )
    c1 = await asyncpg.connect(APP_DSN)
    c2 = await asyncpg.connect(APP_DSN)
    t1 = c1.transaction()
    await t1.start()
    await c1.execute("select pg_advisory_xact_lock($1)", key)
    t2 = c2.transaction()
    await t2.start()
    blocked = False
    try:
        await asyncio.wait_for(c2.execute("select pg_advisory_xact_lock($1)", key), timeout=1.5)
    except TimeoutError:
        blocked = True
    finally:
        await t1.rollback()
        try:
            await t2.rollback()
        except Exception:  # noqa: BLE001
            pass
        await c1.close()
        await c2.close()
    assert blocked, "second session must block on the held advisory lock"


async def test_gate_a_concurrent_overcommit_serialized_rejection(live):
    """Gate A (the real thing) — two SIMULTANEOUS transactions over the same shared node,
    each requesting 180/300. The advisory lock forces them to serialize so the second one
    re-reads AFTER the first commits, sees the committed 180, and is rejected on peak
    (180 + 180 > 300). This exercises the full adapter path (lock → fresh overlap read →
    kernel admission → reject), not just the lock primitive. Deterministic, no sleeps:
    an ``after_locks_acquired`` hook pauses T1 with the lock held until T2 is proven blocked.
    """
    adapter, kernel = _adapter()
    tenant, project, n1 = live["tenant"], live["project"], live["n1"]

    c1 = await asyncpg.connect(APP_DSN)
    c2 = await asyncpg.connect(APP_DSN)
    t1_has_lock = asyncio.Event()
    release_t1 = asyncio.Event()
    t2_has_lock = asyncio.Event()

    async def hook1() -> None:
        t1_has_lock.set()
        await release_t1.wait()

    async def hook2() -> None:
        t2_has_lock.set()

    async def _reserve(conn, ref_id, idem, hook):
        async with conn.transaction():
            return await adapter.reserve_and_request_dispatch_db(
                conn,
                tenant_id=tenant,
                project_id=project,
                requested_start=START,
                requested_end=END,
                resources=[_req(kernel, n1, "shared_capacity", "180", "300")],
                execution_ref_type="manual_execution",
                execution_ref_id=ref_id,
                calculation_model_version="v1",
                execution_port=_Port(),
                correlation_id=tenant,
                idempotency_key=idem,
                after_locks_acquired=hook,
            )

    try:
        t1 = asyncio.create_task(_reserve(c1, "cc-1", "CC1", hook1))
        # T1 has taken the advisory lock and is paused BEFORE its overlap read/insert.
        await asyncio.wait_for(t1_has_lock.wait(), timeout=5)

        # T2 starts and must BLOCK acquiring the same advisory lock — it can never reach
        # its own post-lock hook while T1 holds the lock.
        t2 = asyncio.create_task(_reserve(c2, "cc-2", "CC2", hook2))
        blocked = False
        try:
            await asyncio.wait_for(t2_has_lock.wait(), timeout=1.5)
        except TimeoutError:
            blocked = True
        assert blocked, "T2 must block on the advisory lock while T1 holds it"

        # Release T1: it does its fresh overlap read (empty), inserts 180, commits — the
        # advisory xact lock is dropped, unblocking T2.
        release_t1.set()
        await t1

        # T2 now acquires the lock, re-reads, sees T1's committed 180, and is rejected.
        with pytest.raises(adapter.CapacityNotAdmissible) as ex:
            await t2
        assert ex.value.admission.blocking_code == "CONCURRENT_LOAD_EXCEEDED"
    finally:
        await c1.close()
        await c2.close()

    # End state: exactly ONE reservation + ONE evaluation (T1); T2 left no orphan rows.
    app = live["app"]
    await app.execute("select set_config('app.current_tenant', $1, false)", str(tenant))
    assert (
        await app.fetchval(
            "select count(*) from irrigation_resource_reservations where idempotency_key='CC1'"
        )
        == 1
    )
    assert (
        await app.fetchval(
            "select count(*) from irrigation_resource_reservations where idempotency_key='CC2'"
        )
        == 0
    )
    assert (
        await app.fetchval(
            "select count(*) from hydraulic_capacity_evaluations where execution_ref_id='cc-1'"
        )
        == 1
    )
    assert (
        await app.fetchval(
            "select count(*) from hydraulic_capacity_evaluations where execution_ref_id='cc-2'"
        )
        == 0
    )


async def test_gate_a_idempotent_replay_is_rejected_no_duplicate(live):
    """Replaying a byte-identical reservation (same idempotency_key + node) is rejected by the
    DB uniqueness contract — no silent dedup, no duplicate row, no phantom evaluation. Here
    'idempotent' means exactly one reservation survives, enforced by
    UNIQUE(tenant_id, idempotency_key, resource_node_id) rather than a swallowed retry.
    """
    adapter, kernel = _adapter()
    app, tenant, project, n1 = live["app"], live["tenant"], live["project"], live["n1"]

    async def _reserve():
        async with app.transaction():
            await adapter.reserve_and_request_dispatch_db(
                app,
                tenant_id=tenant,
                project_id=project,
                requested_start=START,
                requested_end=END,
                resources=[_req(kernel, n1, "shared_capacity", "100", "300")],
                execution_ref_type="manual_execution",
                execution_ref_id="idemp",
                calculation_model_version="v1",
                execution_port=_Port(),
                correlation_id=tenant,
                idempotency_key="IDEMP",
            )

    await _reserve()
    # The replay passes admission (100 + 100 <= 300) but violates the reservation idempotency
    # uniqueness (SQLSTATE 23505); the whole transaction rolls back — including its evaluation.
    with pytest.raises(asyncpg.PostgresError) as dup:
        await _reserve()
    assert dup.value.sqlstate == "23505"

    await app.execute("select set_config('app.current_tenant', $1, false)", str(tenant))
    assert (
        await app.fetchval(
            "select count(*) from irrigation_resource_reservations where idempotency_key='IDEMP'"
        )
        == 1
    )
    assert (
        await app.fetchval(
            "select count(*) from hydraulic_capacity_evaluations where execution_ref_id='idemp'"
        )
        == 1
    )


async def test_gate_b1_dispatch_intent_emitted_to_outbox_atomically(live):
    """Gate B1 — the real EmitEventExecutionRequestPort writes the dispatch INTENT to
    the existing outbox atomically with the reservation. Skips without the events subsystem."""
    adapter, kernel = _adapter()
    app, tenant, project, n1 = live["app"], live["tenant"], live["project"], live["n1"]
    if await app.fetchval("select to_regclass('events')") is None:
        _skip_or_fail("events table absent — apply the events-bus migrations for Gate B1")
    from api.irrigation_execution_request_port import EmitEventExecutionRequestPort

    port = EmitEventExecutionRequestPort()
    async with app.transaction():
        out = await adapter.reserve_and_request_dispatch_db(
            app,
            tenant_id=tenant,
            project_id=project,
            requested_start=START,
            requested_end=END,
            resources=[_req(kernel, n1, "shared_capacity", "120", "300")],
            execution_ref_type="manual_execution",
            execution_ref_id="b1",
            calculation_model_version="v1",
            execution_port=port,
            correlation_id=tenant,
        )
    await app.execute("select set_config('app.current_tenant', $1, false)", str(tenant))
    ev = await app.fetchrow(
        "select event_id, entity_type, entity_id from events "
        "where event_type='irrigation.reservation.dispatch_requested' and entity_id=$1",
        out.evaluation_id,
    )
    assert ev is not None and ev["entity_type"] == "operation"
    # Primary name is dispatch_intent_id (an outbox INTENT, not an execution receipt);
    # dispatch_request_ref is a back-compat alias that must agree.
    assert out.dispatch_intent_id == str(ev["event_id"])
    assert out.dispatch_request_ref == out.dispatch_intent_id
    # The outbox carries the intent for the existing worker (dispatch_requested, not dispatched).
    assert (
        await app.fetchval("select count(*) from event_outbox where event_id=$1", ev["event_id"])
        == 1
    )

    # Atomicity: a rolled-back reservation emits NO outbox event. Scope the count to this
    # tenant so it is robust on the shared CI DB even if events RLS is ever relaxed.
    before = await app.fetchval("select count(*) from events where tenant_id = $1", tenant)
    with pytest.raises(RuntimeError):
        async with app.transaction():
            await adapter.reserve_and_request_dispatch_db(
                app,
                tenant_id=tenant,
                project_id=project,
                requested_start=START,
                requested_end=END,
                resources=[_req(kernel, n1, "shared_capacity", "50", "300")],
                execution_ref_type="manual_execution",
                execution_ref_id="b1-roll",
                calculation_model_version="v1",
                execution_port=port,
                correlation_id=tenant,
                idempotency_key="B1ROLL",
            )
            raise RuntimeError("force rollback")
    assert await app.fetchval("select count(*) from events where tenant_id = $1", tenant) == before

    # Compensation emits dispatch_failed and cancels the reservation (no correlation crash).
    await adapter.compensate_dispatch_failure(
        app,
        tenant_id=tenant,
        reservation_ids=out.reservation_ids,
        execution_request_ref=out.dispatch_intent_id,
        execution_port=port,
        reason="actuator_nak",
    )
    assert (
        await app.fetchval(
            "select count(*) from events where event_type='irrigation.reservation.dispatch_failed'"
        )
        >= 1
    )
    assert (
        await app.fetchval(
            "select state from irrigation_resource_reservations where reservation_id=$1",
            __import__("uuid").UUID(out.reservation_ids[0]),
        )
        == "cancelled"
    )


async def test_reservation_mqtt_replay_has_one_simulated_device_effect(live, tmp_path, monkeypatch):
    """A lab-issued command for one committed reservation, sent twice on loopback MQTT.

    The test issues the synthetic command explicitly. Production decision authorization
    and its workers are independent of this simulator transport proof.
    """
    import json
    import secrets
    import sys
    from pathlib import Path

    import aiomqtt
    from amqtt.broker import Broker
    from pwdlib import PasswordHash

    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[1] / "services/actuator-service")
    )
    import cmd_signing_v2 as signing

    adapter, kernel = _adapter()
    from api.irrigation_execution_request_port import EmitEventExecutionRequestPort

    app, tenant = live["app"], live["tenant"]
    async with app.transaction():
        result = await adapter.reserve_and_request_dispatch_db(
            app,
            tenant_id=tenant,
            project_id=live["project"],
            requested_start=START,
            requested_end=END,
            resources=[_req(kernel, live["n1"], "shared_capacity", "1", "10")],
            execution_ref_type="manual_execution",
            execution_ref_id="local-device",
            calculation_model_version="v1",
            execution_port=EmitEventExecutionRequestPort(),
            correlation_id=tenant,
        )
    (reservation_id,) = result.reservation_ids
    await app.execute("select set_config('app.current_tenant', $1, false)", str(tenant))
    assert (
        await app.fetchval(
            "SELECT count(*) FROM event_outbox WHERE event_id=$1", UUID(result.dispatch_intent_id)
        )
        == 1
    )

    from api.irrigation_dispatch_relay import build_reservation_dispatch_ingest

    event = await app.fetchrow(
        "SELECT event_type, payload FROM events WHERE event_id=$1", UUID(result.dispatch_intent_id)
    )
    delivery = build_reservation_dispatch_ingest(
        source_event_id=result.dispatch_intent_id,
        event_type=event["event_type"],
        payload=json.loads(event["payload"]),
        correlation_id=str(tenant),
    )
    assert delivery["reservation_ids"] == [reservation_id]
    probe = Path(__file__).resolve().parents[1] / "tests/integration/irrigation/decision_receipt.py"
    decision = await asyncio.create_subprocess_exec(
        sys.executable, str(probe), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
    )
    receipt, _ = await decision.communicate(
        json.dumps({"tenant": str(tenant), "delivery": delivery}).encode()
    )
    assert decision.returncode == 0 and receipt.strip().startswith(b"rcpt_")

    password = secrets.token_urlsafe(24)
    credentials = tmp_path / "broker.passwd"
    credentials.write_text(
        "lab:" + PasswordHash.recommended().hash(password) + "\n", encoding="utf-8"
    )
    broker = Broker(
        {
            "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
            "plugins": {
                "amqtt.plugins.authentication.FileAuthPlugin": {"password_file": str(credentials)}
            },
        }
    )
    await broker.start()
    try:
        port = broker._servers["default"].instance.sockets[0].getsockname()[1]
        endpoint = {"hostname": "127.0.0.1", "port": port, "username": "lab", "password": password}
        device = signing.DeviceState(str(tenant), "lab-device", "lab-field", secrets.token_hex(32))
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        wire = signing.build_command(
            device.key_hex,
            tenant=device.tenant,
            device=device.device,
            field=device.field,
            command_id=reservation_id,
            cmd="OFF",
            payload={},
            duration_ms=0,
            iat=now_ms,
            exp=now_ms + 60_000,
            ctr=1,
        )
        payload = json.dumps(wire).encode()
        topic = f"sahool/actuator/{device.device}/command"
        effects = tmp_path / "device-effects.txt"
        decisions = []
        async with (
            asyncio.timeout(15),
            aiomqtt.Client(**endpoint) as subscriber,
            aiomqtt.Client(**endpoint) as publisher,
        ):
            await subscriber.subscribe(topic, qos=1)
            for _ in range(2):
                await publisher.publish(topic, payload, qos=1)
                message = await anext(aiter(subscriber.messages))
                received = json.loads(message.payload)
                reason = signing.reference_apply(device, received, time_synced=True, now_ms=now_ms)
                decisions.append(reason)
                if reason == signing.ACCEPT:
                    with effects.open("a", encoding="utf-8") as stream:
                        print(received["id"], file=stream)
        assert decisions == [signing.ACCEPT, signing.REJ_REPLAY]
        assert effects.read_text(encoding="utf-8").splitlines() == [reservation_id]
    finally:
        await broker.shutdown()


async def test_period_volume_serial_reservations_over_live_postgres(live):
    """Synthetic quota: two nonoverlapping 50-ha pivot requests, each 1500 m3."""
    import json

    adapter, kernel = _adapter()
    app, tenant, project, node = live["app"], live["tenant"], live["project"], live["n1"]
    hour = timedelta(hours=1)
    resource = adapter.ResourceRequest(
        resource_node_id=node,
        policy=kernel.ResourcePolicy.SHARED_CAPACITY,
        reserved_flow_m3h=Decimal("1500"),
        derated_capacity_m3h=Decimal("2000"),
        requires_period_volume_budget=True,
    )

    async def resolve(conn, req):
        assert conn.is_in_transaction()
        assert req.resource_node_id == node
        assert await conn.fetchval("select current_setting('app.current_tenant')") == str(tenant)
        return kernel.PeriodVolumeBudget(
            START, START + 24 * hour, Decimal("2500"), "synthetic-budget-v1"
        )

    async def reserve(start, ref, resolver):
        async with app.transaction():
            return await adapter.reserve_and_request_dispatch_db(
                app,
                tenant_id=tenant,
                project_id=project,
                requested_start=start,
                requested_end=start + hour,
                resources=[resource],
                execution_ref_type="manual_execution",
                execution_ref_id=ref,
                calculation_model_version="period-volume-test",
                execution_port=_Port(),
                correlation_id=tenant,
                resolve_period_volume_budget=resolver,
            )

    with pytest.raises(ValueError, match="PERIOD_VOLUME_BUDGET_REQUIRED"):
        await reserve(START, "missing-budget", None)

    first = await reserve(START, "pivot-a", resolve)
    with pytest.raises(adapter.CapacityNotAdmissible) as blocked:
        await reserve(START + hour, "pivot-b", resolve)
    assert blocked.value.admission.blocking_code == "PERIOD_VOLUME_EXCEEDED"
    assert blocked.value.admission.peak_existing_flow_m3h == 0

    await app.execute("select set_config('app.current_tenant', $1, false)", str(tenant))
    for table in CORE_TABLES:
        assert await app.fetchval(f"select count(*) from {table}") == 1
    raw = await app.fetchval(
        "select derating_factors from hydraulic_capacity_evaluations where evaluation_id=$1",
        UUID(first.evaluation_id),
    )
    evidence = json.loads(raw)["period_volume_budgets"][str(node)]
    assert evidence["evidence_ref"] == "synthetic-budget-v1"
    assert evidence["available_m3"] == "2500"
    await app.execute("select set_config('app.current_tenant', $1, false)", str(uuid4()))
    assert await app.fetchval("select count(*) from irrigation_resource_reservations") == 0


async def test_period_volume_concurrent_nonoverlapping_requests_serialize(live):
    """Two 1500 m3 requests fit alone but cannot both consume a 2500 m3 quota.

    Their half-open operating windows are adjacent, so peak-flow admission cannot
    detect this overcommit. The second real transaction must read the first one's
    committed volume after acquiring the same resource lock, then leave no rows
    or dispatch intent when period-volume admission rejects it.
    """
    adapter, kernel = _adapter()
    from api.irrigation_execution_request_port import EmitEventExecutionRequestPort

    app, tenant, project, node = live["app"], live["tenant"], live["project"], live["n1"]
    hour = timedelta(hours=1)
    budget = kernel.PeriodVolumeBudget(
        START, START + 24 * hour, Decimal("2500"), "synthetic-concurrent-budget-v1"
    )
    resource = adapter.ResourceRequest(
        resource_node_id=node,
        policy=kernel.ResourcePolicy.SHARED_CAPACITY,
        reserved_flow_m3h=Decimal("1500"),
        derated_capacity_m3h=Decimal("2000"),
        requires_period_volume_budget=True,
    )
    for start in (START, START + hour):
        assert kernel.evaluate_admission(
            policy=resource.policy,
            existing=[],
            requested_start=start,
            requested_end=start + hour,
            requested_flow_m3h=resource.reserved_flow_m3h,
            derated_capacity_m3h=resource.derated_capacity_m3h,
            period_volume_budget=budget,
        ).eligible

    async def resolve(conn, req):
        assert conn.is_in_transaction()
        assert req.resource_node_id == node
        assert await conn.fetchval("select current_setting('app.current_tenant')") == str(tenant)
        return budget

    dispatch_calls = []

    class RecordingPort(EmitEventExecutionRequestPort):
        async def request_dispatch(self, conn, **kwargs):
            dispatch_calls.append(kwargs["execution_ref_id"])
            return await super().request_dispatch(conn, **kwargs)

    port = RecordingPort()
    t1_has_lock = asyncio.Event()
    release_t1 = asyncio.Event()
    t2_has_lock = asyncio.Event()

    async def hook1():
        t1_has_lock.set()
        await release_t1.wait()

    async def hook2():
        t2_has_lock.set()

    async def reserve(conn, start, ref, hook):
        async with conn.transaction():
            return await adapter.reserve_and_request_dispatch_db(
                conn,
                tenant_id=tenant,
                project_id=project,
                requested_start=start,
                requested_end=start + hour,
                resources=[resource],
                execution_ref_type="manual_execution",
                execution_ref_id=ref,
                calculation_model_version="period-volume-concurrency-test",
                execution_port=port,
                correlation_id=tenant,
                idempotency_key=ref,
                after_locks_acquired=hook,
                resolve_period_volume_budget=resolve,
            )

    c1 = await asyncpg.connect(APP_DSN)
    c2 = await asyncpg.connect(APP_DSN)
    tasks = []
    try:
        t1 = asyncio.create_task(reserve(c1, START, "period-cc-1", hook1))
        tasks.append(t1)
        await asyncio.wait_for(t1_has_lock.wait(), timeout=5)
        t2 = asyncio.create_task(reserve(c2, START + hour, "period-cc-2", hook2))
        tasks.append(t2)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(t2_has_lock.wait(), timeout=1.5)
        # Prove the server is actually waiting on T1, rather than interpreting an
        # unscheduled or failed T2 as successful serialization.
        assert not t2.done()
        assert await app.fetchval("select pg_blocking_pids($1)", c2.get_server_pid()) == [
            c1.get_server_pid()
        ]
        assert dispatch_calls == []
        release_t1.set()
        first = await asyncio.wait_for(t1, timeout=10)
        with pytest.raises(adapter.CapacityNotAdmissible) as blocked:
            await asyncio.wait_for(t2, timeout=10)
        assert t2_has_lock.is_set()
        assert blocked.value.resource_node_id == str(node)
        assert blocked.value.admission.blocking_code == "PERIOD_VOLUME_EXCEEDED"
        assert blocked.value.admission.peak_existing_flow_m3h == 0
        assert blocked.value.admission.peak_with_request_m3h == Decimal("1500")
    finally:
        release_t1.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await c1.close()
        await c2.close()

    # The recording wrapper delegates to the real event/outbox port. T2 must not
    # even reach that boundary, and no evaluation, reservation, or event survives.
    assert dispatch_calls == ["period-cc-1"]
    await app.execute("select set_config('app.current_tenant', $1, false)", str(tenant))
    for table in CORE_TABLES:
        assert await app.fetchval(f"select count(*) from {table} where tenant_id=$1", tenant) == 1
    for table in ("hydraulic_capacity_evaluations", "irrigation_resource_reservations"):
        assert (
            await app.fetchval(f"select execution_ref_id from {table} where tenant_id=$1", tenant)
            == "period-cc-1"
        )
    events = await app.fetch(
        "select event_id, entity_id, payload->>'execution_ref_id' as execution_ref_id "
        "from events where tenant_id=$1 "
        "and event_type='irrigation.reservation.dispatch_requested'",
        tenant,
    )
    assert [dict(row) for row in events] == [
        {
            "event_id": UUID(first.dispatch_intent_id),
            "entity_id": first.evaluation_id,
            "execution_ref_id": "period-cc-1",
        }
    ]
    assert (
        await app.fetchval(
            "select count(*) from event_outbox o join events e using (event_id) "
            "where e.tenant_id=$1",
            tenant,
        )
        == 1
    )
