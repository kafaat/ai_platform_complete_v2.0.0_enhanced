"""Atomic, tenant-scoped compensation on the migrated schema and restricted request role."""

import asyncio
from uuid import UUID, uuid4

import pytest

from tests_v9.test_irr_f01_reservation_live_pg import APP_DSN, END, START, _adapter, _req
from tests_v9.test_irr_f01_reservation_live_pg import live as live

pytestmark = pytest.mark.integration


class RecordingPort:
    def __init__(self):
        self.calls = []

    async def mark_dispatch_failed(self, conn, *, execution_request_ref, reason):
        self.calls.append((execution_request_ref, reason))


async def reserve(live, nodes=("n1", "n2")):
    adapter, kernel = _adapter()
    from api.irrigation_execution_request_port import EmitEventExecutionRequestPort

    conn = live["app"]
    port = EmitEventExecutionRequestPort()
    async with conn.transaction():
        outcome = await adapter.reserve_and_request_dispatch_db(
            conn,
            tenant_id=live["tenant"],
            project_id=live["project"],
            requested_start=START,
            requested_end=END,
            resources=[_req(kernel, live[node], "shared_capacity", "1", "10") for node in nodes],
            execution_ref_type="manual_execution",
            execution_ref_id=str(uuid4()),
            calculation_model_version="v1",
            execution_port=port,
            correlation_id=uuid4(),
        )
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(live["tenant"]))
    return dict(
        tenant_id=live["tenant"],
        reservation_ids=outcome.reservation_ids,
        execution_request_ref=outcome.dispatch_intent_id,
        execution_port=port,
        reason="device refused",
    )


async def snapshot(live):
    conn = live["app"]
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(live["tenant"]))
    states = await conn.fetch(
        "SELECT state FROM irrigation_resource_reservations ORDER BY reservation_id"
    )
    events = await conn.fetchval(
        "SELECT count(*) FROM irrigation_resource_reservation_events WHERE event_type='cancelled'"
    )
    failures = await conn.fetchval(
        "SELECT count(*) FROM events WHERE tenant_id=$1 AND event_type='irrigation.reservation.dispatch_failed'",
        live["tenant"],
    )
    return [row["state"] for row in states], events, failures


async def test_empty_and_duplicate_compensation_sets_are_refused_before_the_port(live):
    compensate = _adapter()[0].compensate_dispatch_failure
    args = await reserve(live)
    port = RecordingPort()
    rid = args["reservation_ids"][0]
    for ids, code in [
        ([], "COMPENSATION_RESERVATIONS_REQUIRED"),
        ([rid, rid], "COMPENSATION_DUPLICATE_RESERVATION"),
    ]:
        async with live["app"].transaction():
            with pytest.raises(ValueError, match=f"^{code}$"):
                await compensate(
                    live["app"], **{**args, "reservation_ids": ids, "execution_port": port}
                )
    assert not port.calls
    assert await snapshot(live) == (["reserved", "reserved"], 0, 0)


async def test_compensation_requires_an_active_caller_transaction(live):
    compensate = _adapter()[0].compensate_dispatch_failure
    args = await reserve(live)
    with pytest.raises(ValueError, match="^COMPENSATION_TRANSACTION_REQUIRED$"):
        await compensate(live["app"], **args)
    assert await snapshot(live) == (["reserved", "reserved"], 0, 0)


async def test_exact_compensation_replay_preserves_history_and_one_failure_event(live):
    compensate = _adapter()[0].compensate_dispatch_failure
    args = await reserve(live)
    conn = live["app"]
    async with conn.transaction():
        await compensate(conn, **args)
    async with conn.transaction():
        await compensate(conn, **{**args, "reservation_ids": args["reservation_ids"][::-1]})
    assert await snapshot(live) == (["cancelled", "cancelled"], 2, 1)
    for change in (
        {"reason": "different"},
        {"execution_request_ref": str(uuid4())},
        {"reservation_ids": args["reservation_ids"][:1]},
    ):
        async with conn.transaction():
            with pytest.raises(ValueError, match="^COMPENSATION_CONFLICT$"):
                await compensate(conn, **{**args, **change})
    assert await snapshot(live) == (["cancelled", "cancelled"], 2, 1)


@pytest.mark.parametrize("terminal", ["expired", "cancelled"])
async def test_terminal_or_historical_cancellation_is_preserved(live, terminal):
    compensate = _adapter()[0].compensate_dispatch_failure
    args = await reserve(live, ("n1",))
    conn = live["app"]
    # Seed the existing terminal history through the owner connection: it is fixture state, not
    # the behaviour under test, and the certifying writer (irr_f01_writer) holds column UPDATE on
    # state/released_at/release_reason only, while the SECURITY INVOKER transition also writes
    # activated_at. Granting the writer more to make setup pass would widen production rights.
    await live["admin"].execute(
        "SELECT transition_irrigation_reservation($1,$2,$3,$4)",
        live["tenant"],
        UUID(args["reservation_ids"][0]),
        terminal,
        "existing history",
    )
    before = await snapshot(live)
    async with conn.transaction():
        with pytest.raises(ValueError, match="^COMPENSATION_CONFLICT$"):
            await compensate(conn, **args)
    assert await snapshot(live) == before


async def test_missing_foreign_and_mixed_reservations_leave_all_rows_intact(live):
    compensate = _adapter()[0].compensate_dispatch_failure
    a = await reserve(live, ("n1",))
    b = await reserve(live, ("n2",))
    for change, code in [
        (
            {"reservation_ids": [a["reservation_ids"][0], str(uuid4())]},
            "COMPENSATION_RESERVATION_NOT_FOUND",
        ),
        ({"tenant_id": uuid4()}, "COMPENSATION_RESERVATION_NOT_FOUND"),
        (
            {"reservation_ids": [*a["reservation_ids"], *b["reservation_ids"]]},
            "COMPENSATION_GROUP_MISMATCH",
        ),
    ]:
        async with live["app"].transaction():
            with pytest.raises(ValueError, match=f"^{code}$"):
                await compensate(live["app"], **{**a, **change})
    assert await snapshot(live) == (["reserved", "reserved"], 0, 0)


async def test_port_error_caught_by_caller_rolls_back_rows_and_does_not_retry(live):
    compensate = _adapter()[0].compensate_dispatch_failure
    args = await reserve(live)
    conn = live["app"]
    calls = []
    real_port = args["execution_port"]

    class FailingPort:
        async def mark_dispatch_failed(self, conn, **kwargs):
            calls.append(kwargs)
            await real_port.mark_dispatch_failed(conn, **kwargs)
            raise TypeError("correlation_id rejected inside port after local outbox write")

    async with conn.transaction():
        with pytest.raises(TypeError, match="inside port"):
            await compensate(conn, **{**args, "execution_port": FailingPort()})
        assert await conn.fetchval("SELECT 1") == 1
    assert len(calls) == 1
    assert await snapshot(live) == (["reserved", "reserved"], 0, 0)


async def test_pre_trace_port_signature_is_bound_before_call(live):
    compensate = _adapter()[0].compensate_dispatch_failure
    args = await reserve(live, ("n1",))
    port = RecordingPort()
    async with live["app"].transaction():
        await compensate(live["app"], **{**args, "execution_port": port})
    assert port.calls == [(args["execution_request_ref"], args["reason"])]
    assert await snapshot(live) == (["cancelled"], 1, 0)


async def test_concurrent_reverse_order_replay_waits_then_preserves_one_outbox(live):
    import asyncpg

    compensate = _adapter()[0].compensate_dispatch_failure
    args = await reserve(live)
    first = live["app"]
    second = await asyncpg.connect(APP_DSN)
    task = None

    async def replay():
        async with second.transaction(isolation="read_committed"):
            await compensate(second, **{**args, "reservation_ids": args["reservation_ids"][::-1]})

    try:
        async with first.transaction(isolation="read_committed"):
            await compensate(first, **args)
            task = asyncio.create_task(replay())
            async with asyncio.timeout(10):
                while not await first.fetchval(
                    "SELECT pg_backend_pid() = ANY(pg_blocking_pids($1))", second.get_server_pid()
                ):
                    assert not task.done()
                    await asyncio.sleep(0.01)
        await asyncio.wait_for(task, timeout=10)
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await second.close()
    assert await snapshot(live) == (["cancelled", "cancelled"], 2, 1)


async def test_incomplete_first_attempts_preserve_group_for_full_compensation(live):
    compensate = _adapter()[0].compensate_dispatch_failure
    args = await reserve(live)
    conn = live["app"]
    for rid, reason in zip(
        args["reservation_ids"], ("first failure", "other failure"), strict=True
    ):
        async with conn.transaction():
            with pytest.raises(ValueError, match="^COMPENSATION_CONFLICT$"):
                await compensate(conn, **{**args, "reservation_ids": [rid], "reason": reason})
        assert await snapshot(live) == (["reserved", "reserved"], 0, 0)
    async with conn.transaction():
        await compensate(conn, **args)
        await compensate(conn, **args)
    assert await snapshot(live) == (["cancelled", "cancelled"], 2, 1)
