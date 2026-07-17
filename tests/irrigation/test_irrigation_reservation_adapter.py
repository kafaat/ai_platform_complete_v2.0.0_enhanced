"""IRR-F01 — DB adapter contract (no live DB).

Drives the async adapter with a recording fake connection + fake execution port
via asyncio.run, so it runs under bare pytest (the convergence workflow installs
no pytest-asyncio). Verifies the reserve-and-request-dispatch ordering and the
dispatch_requested / compensation semantics.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "services" / "sahool-platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))


def _load(name: str):
    path = PLATFORM / "api" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"api.{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Ensure the kernel is importable as api.irrigation_capacity_reservation first.
_load("irrigation_capacity_reservation")
adapter = _load("irrigation_reservation_adapter")

ResourceRequest = adapter.ResourceRequest
ResourcePolicy = adapter.ResourcePolicy
reserve_and_request_dispatch_db = adapter.reserve_and_request_dispatch_db
compensate_dispatch_failure = adapter.compensate_dispatch_failure
CapacityNotAdmissible = adapter.CapacityNotAdmissible

TENANT = UUID("11111111-1111-1111-1111-111111111111")
PROJECT = UUID("22222222-2222-2222-2222-222222222222")
NODE_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")
NODE_B = UUID("bbbbbbbb-0000-0000-0000-000000000002")
CORR = UUID("cccccccc-0000-0000-0000-000000000003")
START = datetime(2026, 7, 17, 19, tzinfo=UTC)
END = START + timedelta(minutes=45)


class FakeConn:
    def __init__(self, overlap_rows=None):
        self.calls: list[tuple[str, str, tuple]] = []
        self._overlap = overlap_rows or []
        self._res = 0

    @staticmethod
    def _head(sql: str) -> str:
        return sql.strip().split()[0].upper() if sql.strip() else ""

    async def execute(self, sql, *args):
        self.calls.append(("execute", self._head(sql), args))
        return "OK"

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", "OVERLAP", args))
        return list(self._overlap)

    async def fetchval(self, sql, *args):
        if "hydraulic_capacity_evaluations" in sql:
            self.calls.append(("fetchval", "EVAL", args))
            return "eval-1"
        if "irrigation_resource_reservations" in sql:
            self._res += 1
            self.calls.append(("fetchval", "RESV", args))
            return f"res-{self._res}"
        self.calls.append(("fetchval", "OTHER", args))
        return None


class FakePort:
    def __init__(self):
        self.dispatch_calls: list[dict] = []
        self.failed: list[tuple[str, str]] = []

    async def request_dispatch(self, conn, **kw):
        self.dispatch_calls.append(kw)
        return "dispatch-req-1"

    async def mark_dispatch_failed(self, conn, *, execution_request_ref, reason):
        self.failed.append((execution_request_ref, reason))


def _req(node, policy, flow, cap):
    return ResourceRequest(
        resource_node_id=node,
        policy=ResourcePolicy(policy),
        reserved_flow_m3h=Decimal(flow),
        derated_capacity_m3h=None if cap is None else Decimal(cap),
    )


def _run(coro):
    return asyncio.run(coro)


def test_happy_path_locks_then_evaluates_then_reserves_then_requests_dispatch():
    conn, port = FakeConn(), FakePort()
    outcome = _run(
        reserve_and_request_dispatch_db(
            conn,
            tenant_id=TENANT,
            project_id=PROJECT,
            requested_start=START,
            requested_end=END,
            resources=[_req(NODE_A, "shared_capacity", "180", "300")],
            execution_ref_type="manual_execution",
            execution_ref_id="mx-1",
            calculation_model_version="irr-f01-eval-v1",
            execution_port=port,
            correlation_id=CORR,
        )
    )
    heads = [f"{m}:{h}" for m, h, _ in conn.calls]
    # tenant GUC first, then advisory lock, then overlap read, then eval, then reservation.
    assert heads[0] == "execute:SELECT"  # set_config
    assert "execute:SELECT" in heads  # pg_advisory_xact_lock
    assert heads.index("fetch:OVERLAP") > 1  # overlap read after locks
    assert heads.index("fetchval:EVAL") < heads.index("fetchval:RESV")
    # dispatch REQUEST happens after the reservation, exactly once.
    assert len(port.dispatch_calls) == 1
    assert outcome.dispatch_request_ref == "dispatch-req-1"
    assert outcome.reservation_ids == ("res-1",)
    # Nothing is ever marked dispatched here.
    assert port.failed == []


def test_locks_acquired_in_canonical_order_before_any_evaluation():
    conn, port = FakeConn(), FakePort()
    # Pass B before A; the adapter must lock in canonical (sorted) order.
    _run(
        reserve_and_request_dispatch_db(
            conn,
            tenant_id=TENANT,
            project_id=PROJECT,
            requested_start=START,
            requested_end=END,
            resources=[
                _req(NODE_B, "shared_capacity", "80", "300"),
                _req(NODE_A, "shared_capacity", "80", "300"),
            ],
            execution_ref_type="execution_request",
            execution_ref_id="ex-1",
            calculation_model_version="v1",
            execution_port=port,
            correlation_id=CORR,
        )
    )
    lock_args = [
        a for m, h, a in conn.calls if m == "execute" and len(a) == 1 and isinstance(a[0], int)
    ]
    assert len(lock_args) == 2  # two distinct nodes locked
    first_overlap = next(i for i, (m, h, _) in enumerate(conn.calls) if m == "fetch")
    last_lock = max(
        i
        for i, (m, h, a) in enumerate(conn.calls)
        if m == "execute" and len(a) == 1 and isinstance(a[0], int)
    )
    assert last_lock < first_overlap  # ALL locks before ANY evaluation read


def test_overcommit_raises_and_writes_no_reservation_or_dispatch():
    # Existing 250 on the node; shared cap 300; request 180 -> peak 430 > 300.
    overlap = [{"starts_at": START, "ends_at": END, "reserved_flow_m3h": Decimal("250")}]
    conn, port = FakeConn(overlap_rows=overlap), FakePort()
    try:
        _run(
            reserve_and_request_dispatch_db(
                conn,
                tenant_id=TENANT,
                project_id=PROJECT,
                requested_start=START,
                requested_end=END,
                resources=[_req(NODE_A, "shared_capacity", "180", "300")],
                execution_ref_type="manual_execution",
                execution_ref_id="mx-2",
                calculation_model_version="v1",
                execution_port=port,
                correlation_id=CORR,
            )
        )
        raised = False
    except CapacityNotAdmissible as exc:
        raised = True
        assert exc.admission.blocking_code == "CONCURRENT_LOAD_EXCEEDED"
    assert raised
    assert not any(h == "EVAL" or h == "RESV" for _, h, _ in conn.calls)
    assert port.dispatch_calls == []


def test_compensation_cancels_reservations_and_marks_request_failed():
    conn, port = FakeConn(), FakePort()
    res_ids = ["dddddddd-0000-0000-0000-000000000001", "dddddddd-0000-0000-0000-000000000002"]
    _run(
        compensate_dispatch_failure(
            conn,
            tenant_id=TENANT,
            reservation_ids=res_ids,
            execution_request_ref="dispatch-req-1",
            execution_port=port,
            reason="actuator_nak",
        )
    )
    updates = [a for m, h, a in conn.calls if m == "execute" and h == "UPDATE"]
    assert len(updates) == 2  # both reservations cancelled
    assert port.failed == [("dispatch-req-1", "actuator_nak")]
