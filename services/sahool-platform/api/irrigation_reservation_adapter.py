"""IRR-F01 DB adapter contract — reserve-and-request-dispatch over the existing DB.

This binds the pure reservation kernel (``irrigation_capacity_reservation``) to the
platform-owned v195 tables and the EXISTING execution-request / outbox path. It adds
no execution SoR: the reservation/evaluation rows are platform-owned; the dispatch
request is delegated to an injected :class:`ExecutionRequestPort` whose real
implementation writes the existing outbox (``emit_event``) so the existing worker
creates the existing ``execution_request`` — i.e. a committed reservation means
``dispatch_requested``, and the actuator receipt alone means ``dispatched``.

Ordering (all inside the caller's transaction, per the IRR-F01 review):
    set tenant GUC → acquire ordered advisory locks → fresh per-resource overlap
    read + kernel admission → INSERT evaluation → INSERT reservations + events →
    execution_port.request_dispatch (outbox intent) → caller commits.

On an actuator failure AFTER commit, recovery is forward compensation
(:func:`compensate_dispatch_failure`) — reservation → cancelled, execution request
→ dispatch_failed — never a retroactive rollback.

The concrete SQL targets platform-owned tables only; live execution (and the
ExecutionRequestPort's outbox binding) is exercised by the deferred Phase-4
PostgreSQL integration gate, not here.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from api.irrigation_capacity_reservation import (
    CapacityAdmission,
    ReservationWindow,
    ResourcePolicy,
    ResourceRef,
    advisory_lock_key,
    evaluate_admission,
    ordered_resources,
)

# --- concrete SQL over platform-owned v195 tables ------------------------------

SET_TENANT_SQL = "SELECT set_config('app.current_tenant', $1, true)"

ADVISORY_XACT_LOCK_SQL = "SELECT pg_advisory_xact_lock($1)"

# Existing reserved/active windows on one resource node overlapping the request.
OVERLAP_WINDOWS_SQL = """
SELECT lower(active_interval) AS starts_at,
       upper(active_interval) AS ends_at,
       reserved_flow_m3h
FROM irrigation_resource_reservations
WHERE tenant_id = $1
  AND resource_node_id = $2
  AND state IN ('reserved', 'active')
  AND active_interval && tstzrange($3, $4, '[)')
"""

INSERT_EVALUATION_SQL = """
INSERT INTO hydraulic_capacity_evaluations (
    tenant_id, project_id, canonical_hydraulic_capability_id,
    execution_ref_type, execution_ref_id, requested_interval, requested_flow_m3h,
    maximum_safe_flow_m3h, derated_available_flow_m3h, peak_reserved_flow_m3h,
    remaining_allocatable_flow_m3h, bottleneck_node_id, eligible,
    blocking_reasons, warnings, derating_factors, capability_digest,
    telemetry_snapshot_version, calculation_model_version, correlation_id
) VALUES (
    $1, $2, $3, $4, $5, tstzrange($6, $7, '[)'), $8,
    $9, $10, $11, $12, $13, $14,
    $15::jsonb, $16::jsonb, $17::jsonb, $18, $19, $20, $21
)
RETURNING evaluation_id
"""

INSERT_RESERVATION_SQL = """
INSERT INTO irrigation_resource_reservations (
    tenant_id, project_id, evaluation_id, execution_ref_type, execution_ref_id,
    resource_node_id, resource_policy, reserved_flow_m3h, active_interval,
    idempotency_key, correlation_id
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, tstzrange($9, $10, '[)'), $11, $12
)
RETURNING reservation_id
"""

INSERT_RESERVATION_EVENT_SQL = """
INSERT INTO irrigation_resource_reservation_events (
    tenant_id, reservation_id, event_type, causation_id, correlation_id, payload
) VALUES ($1, $2, $3, $4, $5, $6::jsonb)
"""

CANCEL_RESERVATION_SQL = """
UPDATE irrigation_resource_reservations
SET state = 'cancelled', released_at = NOW(), release_reason = $3
WHERE tenant_id = $1 AND reservation_id = $2
  AND state IN ('reserved', 'active')
"""


class CapacityNotAdmissible(Exception):
    """Raised when a locked resource fails admission — the transaction must abort."""

    def __init__(self, resource_node_id: str, admission: CapacityAdmission) -> None:
        super().__init__(f"{resource_node_id}: {admission.blocking_code}")
        self.resource_node_id = resource_node_id
        self.admission = admission


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    resource_node_id: UUID
    policy: ResourcePolicy
    reserved_flow_m3h: Decimal
    derated_capacity_m3h: Decimal | None


@dataclass(frozen=True, slots=True)
class ReservationOutcome:
    evaluation_id: str
    reservation_ids: tuple[str, ...]
    dispatch_request_ref: str


class ExecutionRequestPort(Protocol):
    """The existing execution-request/outbox boundary — NOT a new execution SoR.

    The real implementation writes the existing outbox (``emit_event`` on the same
    transaction connection) so the existing worker creates the existing
    ``execution_request``. It never marks anything ``dispatched``.
    """

    async def request_dispatch(
        self,
        conn: Any,
        *,
        tenant_id: str,
        evaluation_id: str,
        reservation_ids: Sequence[str],
        execution_ref_type: str,
        execution_ref_id: str,
        correlation_id: str,
    ) -> str: ...

    async def mark_dispatch_failed(
        self, conn: Any, *, execution_request_ref: str, reason: str
    ) -> None: ...


async def reserve_and_request_dispatch_db(
    conn: Any,
    *,
    tenant_id: UUID,
    project_id: UUID,
    requested_start: datetime,
    requested_end: datetime,
    resources: Sequence[ResourceRequest],
    execution_ref_type: str,
    execution_ref_id: str,
    calculation_model_version: str,
    execution_port: ExecutionRequestPort,
    correlation_id: UUID,
    canonical_hydraulic_capability_id: str | None = None,
    idempotency_key: str | None = None,
) -> ReservationOutcome:
    """Lock-before-evaluate reserve + dispatch-REQUEST inside the caller's tx."""

    if not resources:
        raise ValueError("NO_HYDRAULIC_RESOURCES")
    if requested_end <= requested_start:
        raise ValueError("REQUEST_INTERVAL_INVALID")

    tenant = str(tenant_id)
    await conn.execute(SET_TENANT_SQL, tenant)

    # Deterministic, deadlock-safe lock order over the distinct resources.
    ordered = ordered_resources(
        ResourceRef(tenant_id, "hydraulic_node", r.resource_node_id, r.policy) for r in resources
    )
    for ref in ordered:
        await conn.execute(ADVISORY_XACT_LOCK_SQL, advisory_lock_key(ref))

    idem = idempotency_key or f"{execution_ref_type}:{execution_ref_id}"
    reservation_ids: list[str] = []
    peak_over_all = Decimal("0")

    # After locks are held, evaluate every resource against a FRESH overlap read.
    for req in resources:
        rows = await conn.fetch(
            OVERLAP_WINDOWS_SQL, tenant, req.resource_node_id, requested_start, requested_end
        )
        existing = [
            ReservationWindow(r["starts_at"], r["ends_at"], Decimal(str(r["reserved_flow_m3h"])))
            for r in rows
        ]
        admission = evaluate_admission(
            policy=req.policy,
            existing=existing,
            requested_start=requested_start,
            requested_end=requested_end,
            requested_flow_m3h=req.reserved_flow_m3h,
            derated_capacity_m3h=req.derated_capacity_m3h,
        )
        if not admission.eligible:
            raise CapacityNotAdmissible(str(req.resource_node_id), admission)
        peak_over_all = max(peak_over_all, admission.peak_with_request_m3h)

    evaluation_id = await conn.fetchval(
        INSERT_EVALUATION_SQL,
        tenant_id,
        project_id,
        canonical_hydraulic_capability_id,
        execution_ref_type,
        execution_ref_id,
        requested_start,
        requested_end,
        max((r.reserved_flow_m3h for r in resources), default=Decimal("0")),
        None,  # maximum_safe_flow_m3h — filled by the capability read at integration
        min(
            (r.derated_capacity_m3h for r in resources if r.derated_capacity_m3h is not None),
            default=None,
        ),
        peak_over_all,
        None,  # remaining_allocatable_flow_m3h
        None,  # bottleneck_node_id — never declared from topology here
        True,
        json.dumps([]),
        json.dumps([]),
        json.dumps({}),
        None,
        None,
        calculation_model_version,
        correlation_id,
    )

    for req in resources:
        reservation_id = await conn.fetchval(
            INSERT_RESERVATION_SQL,
            tenant_id,
            project_id,
            evaluation_id,
            execution_ref_type,
            execution_ref_id,
            req.resource_node_id,
            req.policy.value,
            req.reserved_flow_m3h,
            requested_start,
            requested_end,
            idem,
            correlation_id,
        )
        reservation_ids.append(str(reservation_id))
        await conn.execute(
            INSERT_RESERVATION_EVENT_SQL,
            tenant_id,
            reservation_id,
            "reserved",
            None,
            correlation_id,
            json.dumps({"resource_node_id": str(req.resource_node_id)}),
        )

    dispatch_request_ref = await execution_port.request_dispatch(
        conn,
        tenant_id=tenant,
        evaluation_id=str(evaluation_id),
        reservation_ids=reservation_ids,
        execution_ref_type=execution_ref_type,
        execution_ref_id=execution_ref_id,
        correlation_id=str(correlation_id),
    )

    return ReservationOutcome(
        evaluation_id=str(evaluation_id),
        reservation_ids=tuple(reservation_ids),
        dispatch_request_ref=dispatch_request_ref,
    )


async def compensate_dispatch_failure(
    conn: Any,
    *,
    tenant_id: UUID,
    reservation_ids: Sequence[str],
    execution_request_ref: str,
    execution_port: ExecutionRequestPort,
    reason: str,
) -> None:
    """Forward compensation for an actuator failure after commit — no rollback."""

    tenant = str(tenant_id)
    await conn.execute(SET_TENANT_SQL, tenant)
    for reservation_id in reservation_ids:
        await conn.execute(CANCEL_RESERVATION_SQL, tenant_id, UUID(reservation_id), reason)
        await conn.execute(
            INSERT_RESERVATION_EVENT_SQL,
            tenant_id,
            UUID(reservation_id),
            "cancelled",
            None,
            None,
            json.dumps({"reason": reason}),
        )
    await execution_port.mark_dispatch_failed(
        conn, execution_request_ref=execution_request_ref, reason=reason
    )
