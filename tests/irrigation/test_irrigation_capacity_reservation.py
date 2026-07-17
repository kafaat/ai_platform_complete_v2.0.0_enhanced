from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "services" / "sahool-platform" / "api" / "irrigation_capacity_reservation.py"
spec = importlib.util.spec_from_file_location("irrigation_capacity_reservation", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

ResourcePolicy = module.ResourcePolicy
ResourceRef = module.ResourceRef
ReservationWindow = module.ReservationWindow
advisory_lock_key = module.advisory_lock_key
evaluate_admission = module.evaluate_admission
ordered_resources = module.ordered_resources
peak_reserved_flow = module.peak_reserved_flow
reserve_and_request_dispatch = module.reserve_and_request_dispatch

TENANT = UUID("11111111-1111-1111-1111-111111111111")
START = datetime(2026, 7, 17, 10, tzinfo=UTC)


def window(start_min: int, end_min: int, flow: str) -> ReservationWindow:
    return ReservationWindow(
        starts_at=START + timedelta(minutes=start_min),
        ends_at=START + timedelta(minutes=end_min),
        reserved_flow_m3h=Decimal(flow),
    )


def test_lock_key_is_stable_tenant_scoped_signed_int64() -> None:
    ref = ResourceRef(
        TENANT, "pump", UUID("22222222-2222-2222-2222-222222222222"), ResourcePolicy.SHARED_CAPACITY
    )
    assert advisory_lock_key(ref) == advisory_lock_key(ref)
    assert -(2**63) <= advisory_lock_key(ref) < 2**63
    other = ResourceRef(
        UUID("33333333-3333-3333-3333-333333333333"), "pump", ref.resource_id, ref.policy
    )
    assert advisory_lock_key(ref) != advisory_lock_key(other)


def test_resource_order_is_deterministic_and_deduplicated() -> None:
    pump = ResourceRef(
        TENANT, "pump", UUID("22222222-2222-2222-2222-222222222222"), ResourcePolicy.SHARED_CAPACITY
    )
    valve = ResourceRef(
        TENANT, "valve", UUID("33333333-3333-3333-3333-333333333333"), ResourcePolicy.EXCLUSIVE
    )
    assert ordered_resources([valve, pump, valve]) == (pump, valve)


def test_peak_load_uses_segment_boundaries_not_naive_overlap_sum() -> None:
    reservations = [window(0, 30, "100"), window(20, 50, "80"), window(35, 60, "90")]
    # Peak is 180 in [20,30) and [35,50), never 270.
    assert peak_reserved_flow(reservations, START, START + timedelta(hours=1)) == Decimal("180")


def test_non_overlapping_future_reservations_do_not_conflict() -> None:
    reservations = [window(0, 30, "100")]
    result = evaluate_admission(
        policy=ResourcePolicy.SHARED_CAPACITY,
        existing=reservations,
        requested_start=START + timedelta(minutes=30),
        requested_end=START + timedelta(minutes=60),
        requested_flow_m3h=Decimal("100"),
        derated_capacity_m3h=Decimal("100"),
    )
    assert result.eligible is True
    assert result.peak_existing_flow_m3h == 0


def test_shared_capacity_rejects_peak_overload() -> None:
    result = evaluate_admission(
        policy=ResourcePolicy.SHARED_CAPACITY,
        existing=[window(0, 30, "100"), window(20, 50, "80")],
        requested_start=START + timedelta(minutes=25),
        requested_end=START + timedelta(minutes=40),
        requested_flow_m3h=Decimal("90"),
        derated_capacity_m3h=Decimal("260"),
    )
    assert result.eligible is False
    assert result.peak_with_request_m3h == Decimal("270")
    assert result.blocking_code == "CONCURRENT_LOAD_EXCEEDED"


def test_exclusive_resource_rejects_any_overlap() -> None:
    result = evaluate_admission(
        policy=ResourcePolicy.EXCLUSIVE,
        existing=[window(0, 30, "1")],
        requested_start=START + timedelta(minutes=5),
        requested_end=START + timedelta(minutes=10),
        requested_flow_m3h=Decimal("1"),
        derated_capacity_m3h=None,
    )
    assert result.eligible is False
    assert result.blocking_code == "RESOURCE_CONFLICT"


def test_orchestration_locks_before_fresh_evaluation_and_writes_dispatch_request() -> None:
    calls: list[str] = []
    resource = ResourceRef(
        TENANT, "pump", UUID("22222222-2222-2222-2222-222222222222"), ResourcePolicy.SHARED_CAPACITY
    )

    class Tx:
        def __enter__(self):
            calls.append("begin")
            return self

        def __exit__(self, exc_type, exc, traceback):
            calls.append("commit" if exc is None else "rollback")
            return False

    result = reserve_and_request_dispatch(
        transaction_factory=Tx,
        resolve_resources=lambda: calls.append("resolve") or [resource],
        acquire_lock=lambda _key: calls.append("lock"),
        evaluate_fresh=lambda _resources: calls.append("evaluate") or {"eligible": True},
        assert_admissible=lambda _evaluation: calls.append("admit"),
        create_reservation=lambda _evaluation: calls.append("reserve") or "reservation",
        create_dispatch_request=lambda _reservation, _evaluation: (
            calls.append("request") or "dispatch-request"
        ),
        write_outbox=lambda _request: calls.append("outbox"),
    )

    assert result.dispatch_request == "dispatch-request"
    assert calls == [
        "begin",
        "resolve",
        "lock",
        "evaluate",
        "admit",
        "reserve",
        "request",
        "outbox",
        "commit",
    ]
