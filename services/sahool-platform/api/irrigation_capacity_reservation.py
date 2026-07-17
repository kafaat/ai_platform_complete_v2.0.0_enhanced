"""IRR-F01 transaction-safe hydraulic capacity helpers.

This module deliberately works with references to the existing irrigation
execution stores instead of introducing a new execution aggregate.  It provides
pure, deterministic primitives used by the database adapter and test simulator:

* stable 64-bit PostgreSQL advisory-lock keys;
* canonical lock ordering;
* peak shared-flow calculation over half-open time intervals;
* exclusive/shared resource admission checks;
* lock-before-evaluate reserve-and-dispatch orchestration contract.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, TypeVar
from uuid import UUID

LOCK_SCHEMA_VERSION = "irr-resource-lock-v1"


class ResourcePolicy(StrEnum):
    EXCLUSIVE = "exclusive"
    SHARED_CAPACITY = "shared_capacity"


@dataclass(frozen=True, slots=True)
class ResourceRef:
    tenant_id: UUID
    resource_type: str
    resource_id: UUID
    policy: ResourcePolicy


@dataclass(frozen=True, slots=True)
class ReservationWindow:
    starts_at: datetime
    ends_at: datetime
    reserved_flow_m3h: Decimal

    def __post_init__(self) -> None:
        if self.ends_at <= self.starts_at:
            raise ValueError("RESERVATION_INTERVAL_INVALID")
        if self.reserved_flow_m3h <= 0:
            raise ValueError("RESERVED_FLOW_MUST_BE_POSITIVE")


@dataclass(frozen=True, slots=True)
class CapacityAdmission:
    eligible: bool
    peak_existing_flow_m3h: Decimal
    peak_with_request_m3h: Decimal
    remaining_at_peak_m3h: Decimal
    blocking_code: str | None = None


def advisory_lock_key(resource: ResourceRef) -> int:
    """Return a stable signed int64 advisory-lock key.

    Python's ``hash`` and PostgreSQL ``hashtext`` are intentionally avoided:
    they are not a cross-language contract and are too easy to use without a
    tenant namespace.  The first eight bytes of SHA-256 are interpreted as a
    signed big-endian int64 and are stable across runtimes.
    """

    canonical = (
        f"{LOCK_SCHEMA_VERSION}|{resource.tenant_id}|"
        f"{resource.resource_type.lower()}|{resource.resource_id}"
    ).encode()
    raw = hashlib.sha256(canonical).digest()[:8]
    return int.from_bytes(raw, byteorder="big", signed=True)


def ordered_resources(resources: Iterable[ResourceRef]) -> tuple[ResourceRef, ...]:
    """Deduplicate and return resources in a deterministic deadlock-safe order."""

    unique = {(r.tenant_id, r.resource_type.lower(), r.resource_id): r for r in resources}
    return tuple(
        unique[key]
        for key in sorted(unique, key=lambda item: (str(item[0]), item[1], str(item[2])))
    )


def _overlaps(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    # PostgreSQL tstzrange default semantics are [start, end).
    return left_start < right_end and right_start < left_end


def peak_reserved_flow(
    reservations: Sequence[ReservationWindow],
    requested_start: datetime,
    requested_end: datetime,
) -> Decimal:
    """Calculate peak existing reserved flow inside a requested half-open interval.

    The implementation evaluates every segment boundary.  Summing every
    reservation that merely overlaps the whole request would over-count flows
    that never coexist.
    """

    if requested_end <= requested_start:
        raise ValueError("REQUEST_INTERVAL_INVALID")

    relevant = [
        item
        for item in reservations
        if _overlaps(item.starts_at, item.ends_at, requested_start, requested_end)
    ]
    if not relevant:
        return Decimal("0")

    boundaries = {requested_start, requested_end}
    for item in relevant:
        boundaries.add(max(requested_start, item.starts_at))
        boundaries.add(min(requested_end, item.ends_at))
    points = sorted(boundaries)

    peak = Decimal("0")
    for start, end in zip(points, points[1:], strict=False):
        if end <= start:
            continue
        # Sampling the segment start is valid for [start, end) ranges.
        load = sum(
            (item.reserved_flow_m3h for item in relevant if item.starts_at <= start < item.ends_at),
            Decimal("0"),
        )
        peak = max(peak, load)
    return peak


def evaluate_admission(
    *,
    policy: ResourcePolicy,
    existing: Sequence[ReservationWindow],
    requested_start: datetime,
    requested_end: datetime,
    requested_flow_m3h: Decimal,
    derated_capacity_m3h: Decimal | None,
) -> CapacityAdmission:
    """Evaluate one locked resource for exclusive or shared-capacity admission."""

    if requested_flow_m3h <= 0:
        raise ValueError("REQUESTED_FLOW_MUST_BE_POSITIVE")

    peak_existing = peak_reserved_flow(existing, requested_start, requested_end)
    if policy is ResourcePolicy.EXCLUSIVE:
        if peak_existing > 0:
            return CapacityAdmission(
                eligible=False,
                peak_existing_flow_m3h=peak_existing,
                peak_with_request_m3h=peak_existing + requested_flow_m3h,
                remaining_at_peak_m3h=Decimal("0"),
                blocking_code="RESOURCE_CONFLICT",
            )
        return CapacityAdmission(
            eligible=True,
            peak_existing_flow_m3h=Decimal("0"),
            peak_with_request_m3h=requested_flow_m3h,
            remaining_at_peak_m3h=Decimal("0"),
        )

    if derated_capacity_m3h is None:
        return CapacityAdmission(
            eligible=False,
            peak_existing_flow_m3h=peak_existing,
            peak_with_request_m3h=peak_existing + requested_flow_m3h,
            remaining_at_peak_m3h=Decimal("0"),
            blocking_code="CAPACITY_UNKNOWN",
        )
    if derated_capacity_m3h < 0:
        raise ValueError("DERATED_CAPACITY_INVALID")

    peak_with_request = peak_existing + requested_flow_m3h
    remaining = max(Decimal("0"), derated_capacity_m3h - peak_with_request)
    return CapacityAdmission(
        eligible=peak_with_request <= derated_capacity_m3h,
        peak_existing_flow_m3h=peak_existing,
        peak_with_request_m3h=peak_with_request,
        remaining_at_peak_m3h=remaining,
        blocking_code=(
            None if peak_with_request <= derated_capacity_m3h else "CONCURRENT_LOAD_EXCEEDED"
        ),
    )


T = TypeVar("T")
E = TypeVar("E")
R = TypeVar("R")


class TransactionContext(Protocol):
    def __enter__(self) -> TransactionContext: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool | None: ...


@dataclass(frozen=True, slots=True)
class ReserveDispatchResult:
    evaluation: object
    reservation: object
    dispatch_request: object


def reserve_and_request_dispatch(
    *,
    transaction_factory: Callable[[], TransactionContext],
    resolve_resources: Callable[[], Sequence[ResourceRef]],
    acquire_lock: Callable[[int], None],
    evaluate_fresh: Callable[[Sequence[ResourceRef]], E],
    assert_admissible: Callable[[E], None],
    create_reservation: Callable[[E], R],
    create_dispatch_request: Callable[[R, E], T],
    write_outbox: Callable[[T], None],
) -> ReserveDispatchResult:
    """Canonical lock-before-evaluate reserve-and-dispatch-request sequence.

    The function intentionally creates a *dispatch request*, not a dispatched
    state. Physical dispatch is owned by the existing actuator/execution-request
    pipeline and is confirmed by its receipt.
    """

    with transaction_factory():
        resources = ordered_resources(resolve_resources())
        if not resources:
            raise ValueError("NO_HYDRAULIC_RESOURCES")
        for resource in resources:
            acquire_lock(advisory_lock_key(resource))

        evaluation = evaluate_fresh(resources)
        assert_admissible(evaluation)
        reservation = create_reservation(evaluation)
        request = create_dispatch_request(reservation, evaluation)
        write_outbox(request)

    return ReserveDispatchResult(
        evaluation=evaluation,
        reservation=reservation,
        dispatch_request=request,
    )
