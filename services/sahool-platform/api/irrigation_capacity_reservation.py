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
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
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


@dataclass(frozen=True, slots=True)
class PeriodVolumeBudget:
    """Owner-resolved quota net of settled consumption, before outstanding reservations.

    This is not an authorization or a new allocation store. The caller must resolve the
    current approved version under the same resource lock as reservation and settlement.
    """

    starts_at: datetime
    ends_at: datetime
    available_m3: Decimal
    evidence_ref: str

    def __post_init__(self) -> None:
        start, end = _utc(self.starts_at), _utc(self.ends_at)
        if end <= start:
            raise ValueError("PERIOD_VOLUME_INTERVAL_INVALID")
        if not self.available_m3.is_finite() or self.available_m3 < 0:
            raise ValueError("PERIOD_VOLUME_BUDGET_INVALID")
        if not isinstance(self.evidence_ref, str) or not self.evidence_ref.strip():
            raise ValueError("PERIOD_VOLUME_EVIDENCE_REQUIRED")


def _utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("PERIOD_VOLUME_TIMESTAMP_UNZONED")
    return value.astimezone(UTC)


def _volume_in_period(window: ReservationWindow, start: datetime, end: datetime) -> Fraction:
    """Integrate constant flow exactly over the clipped half-open window."""
    flow = window.reserved_flow_m3h
    if not flow.is_finite() or flow <= 0:
        raise ValueError("PERIOD_VOLUME_FLOW_INVALID")
    delta = min(end, _utc(window.ends_at)) - max(start, _utc(window.starts_at))
    micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return Fraction(flow) * max(0, micros) / 3_600_000_000


def _period_volume_blocker(
    budget: PeriodVolumeBudget,
    existing: Sequence[ReservationWindow],
    requested_start: datetime,
    requested_end: datetime,
    requested_flow_m3h: Decimal,
) -> str | None:
    start, end = _utc(budget.starts_at), _utc(budget.ends_at)
    request_start, request_end = _utc(requested_start), _utc(requested_end)
    if not start <= request_start < request_end <= end:
        return "REQUEST_OUTSIDE_VOLUME_PERIOD"
    # v195 persists NUMERIC(14,4): never admit less volume than the stored reservation.
    if (
        not requested_flow_m3h.is_finite()
        or requested_flow_m3h <= 0
        or requested_flow_m3h > Decimal("9999999999.9999")
        or (Fraction(requested_flow_m3h) * 10_000).denominator != 1
    ):
        raise ValueError("PERIOD_VOLUME_FLOW_NOT_STORABLE")
    committed = sum((_volume_in_period(item, start, end) for item in existing), Fraction(0))
    requested = _volume_in_period(
        ReservationWindow(request_start, request_end, requested_flow_m3h), start, end
    )
    if committed + requested > Fraction(budget.available_m3):
        return "PERIOD_VOLUME_EXCEEDED"
    return None


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
    period_volume_budget: PeriodVolumeBudget | None = None,
) -> CapacityAdmission:
    """Evaluate one locked resource for exclusive or shared-capacity admission."""

    if requested_flow_m3h <= 0:
        raise ValueError("REQUESTED_FLOW_MUST_BE_POSITIVE")

    peak_existing = peak_reserved_flow(existing, requested_start, requested_end)
    if period_volume_budget is not None:
        blocker = _period_volume_blocker(
            period_volume_budget, existing, requested_start, requested_end, requested_flow_m3h
        )
        if blocker is not None:
            return CapacityAdmission(
                eligible=False,
                peak_existing_flow_m3h=peak_existing,
                peak_with_request_m3h=peak_existing + requested_flow_m3h,
                remaining_at_peak_m3h=Decimal("0"),
                blocking_code=blocker,
            )
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
