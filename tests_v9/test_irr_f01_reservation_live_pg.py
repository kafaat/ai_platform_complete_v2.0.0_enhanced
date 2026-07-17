"""IRR-F01 — live PostgreSQL Gate A for the capacity/reservation slice.

Runs only under ``pytest -m integration`` and skips when a live database or a
NOBYPASSRLS app role is unavailable. It drives the REAL adapter
(``reserve_and_request_dispatch_db``) over the REAL v195/v196 tables to certify
what CI cannot: FORCE RLS isolation, WITH CHECK write fail-closed, transactional
advisory-lock serialization, exclusive/shared admission, and rollback safety.

Requires (env):
  TEST_DATABASE_URL        — app-role DSN (NOSUPERUSER, NOBYPASSRLS), TCP.
  TEST_DATABASE_ADMIN_URL  — owner/superuser DSN used ONLY to seed dependency rows
                             (optional; falls back to TEST_DATABASE_URL).
The database must already have migrations through v196 applied.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")
pytestmark = pytest.mark.integration

APP_DSN = os.getenv("TEST_DATABASE_URL")
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", APP_DSN)

CORE_TABLES = (
    "hydraulic_capacity_evaluations",
    "irrigation_resource_reservations",
    "irrigation_resource_reservation_events",
)


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
        pytest.skip("TEST_DATABASE_URL unset")
    try:
        app = await asyncpg.connect(APP_DSN)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}")
    # Skip when connected as a superuser/bypassrls role — RLS asserts need a real app role.
    is_super = await app.fetchval("select current_setting('is_superuser')")
    bypass = await app.fetchval("select rolbypassrls from pg_roles where rolname = current_user")
    for table in CORE_TABLES:
        if await app.fetchval("select to_regclass($1)", table) is None:
            await app.close()
            pytest.skip(f"{table} absent — migrate to v196 first")
    if is_super == "on" or bypass:
        await app.close()
        pytest.skip("connect as a NOSUPERUSER/NOBYPASSRLS app role to certify RLS")

    admin = await asyncpg.connect(ADMIN_DSN)
    tenant = uuid4()
    project = uuid4()
    node1 = uuid4()
    node2 = uuid4()
    await admin.execute(
        "insert into irrigation_projects(id, tenant_id) values ($1,$2)", project, tenant
    )
    for node, kind in ((node1, "pump"), (node2, "valve")):
        await admin.execute(
            "insert into irrigation_hydraulic_nodes(id, tenant_id, project_id, node_type) values ($1,$2,$3,$4)",
            node,
            tenant,
            project,
            kind,
        )
    ctx = {"app": app, "tenant": tenant, "project": project, "n1": node1, "n2": node2}
    try:
        yield ctx
    finally:
        # The reservation event log is DB-enforced append-only (trigger) and every FK is
        # ON DELETE RESTRICT, so per-row cleanup is impossible BY DESIGN. This certification
        # therefore requires a DISPOSABLE database: the owner/superuser admin truncates the
        # reservation tables (TRUNCATE bypasses the row-level append-only trigger). If the
        # admin lacks owner rights, rows for this random tenant are left behind (harmless on
        # a throwaway instance). NEVER point TEST_DATABASE_URL at a shared DB with real data.
        try:
            await admin.execute(
                "TRUNCATE irrigation_resource_reservation_events, "
                "irrigation_resource_reservations, hydraulic_capacity_evaluations CASCADE"
            )
        except asyncpg.PostgresError:
            pass
        if await admin.fetchval("select to_regclass('events')") is not None:
            try:
                await admin.execute("TRUNCATE events, event_outbox CASCADE")
            except asyncpg.PostgresError:
                pass
        try:
            await admin.execute("delete from irrigation_hydraulic_nodes where tenant_id = $1", tenant)
            await admin.execute("delete from irrigation_projects where id = $1", project)
        except asyncpg.PostgresError:
            pass
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


START = datetime(2026, 7, 17, 19, tzinfo=UTC)
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
    with pytest.raises(asyncpg.PostgresError):
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


async def test_gate_b1_dispatch_intent_emitted_to_outbox_atomically(live):
    """Gate B1 — the real EmitEventExecutionRequestPort writes the dispatch INTENT to
    the existing outbox atomically with the reservation. Skips without the events subsystem."""
    adapter, kernel = _adapter()
    app, tenant, project, n1 = live["app"], live["tenant"], live["project"], live["n1"]
    if await app.fetchval("select to_regclass('events')") is None:
        pytest.skip("events table absent — apply the events-bus migrations for Gate B1")
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
    assert out.dispatch_request_ref == str(ev["event_id"])
    # The outbox carries the intent for the existing worker (dispatch_requested, not dispatched).
    assert (
        await app.fetchval("select count(*) from event_outbox where event_id=$1", ev["event_id"])
        == 1
    )

    # Atomicity: a rolled-back reservation emits NO outbox event.
    before = await app.fetchval("select count(*) from events")
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
    assert await app.fetchval("select count(*) from events") == before

    # Compensation emits dispatch_failed and cancels the reservation (no correlation crash).
    await adapter.compensate_dispatch_failure(
        app,
        tenant_id=tenant,
        reservation_ids=out.reservation_ids,
        execution_request_ref=out.dispatch_request_ref,
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
