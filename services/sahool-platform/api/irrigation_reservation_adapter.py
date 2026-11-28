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

import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from api.irrigation_capacity_reservation import (
    CapacityAdmission,
    PeriodVolumeBudget,
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
    requires_period_volume_budget: bool = False


@dataclass(frozen=True, slots=True)
class ReservationOutcome:
    evaluation_id: str
    reservation_ids: tuple[str, ...]
    dispatch_intent_id: str

    @property
    def dispatch_request_ref(self) -> str:
        """Backward-compatible alias; this is an outbox INTENT, not an execution receipt."""
        return self.dispatch_intent_id


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
        self,
        conn: Any,
        *,
        execution_request_ref: str,
        reason: str,
        correlation_id: str | None = None,
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
    capability_digest: str | None = None,
    telemetry_snapshot_version: str | None = None,
    idempotency_key: str | None = None,
    activation_guard: Callable[[], Awaitable[None]] | None = None,
    after_locks_acquired: Callable[[], Awaitable[None]] | None = None,
    resolve_period_volume_budget: (
        Callable[[Any, ResourceRequest], Awaitable[PeriodVolumeBudget | None]] | None
    ) = None,
) -> ReservationOutcome:
    """Lock-before-evaluate reserve + dispatch-REQUEST inside the caller's tx.

    ``activation_guard`` is the IRR-F01 activation enforcement seam (default ``None`` =
    off, so the current mirror deployment is unchanged). When the caller wires it (to the
    ``irr_f01_reservation`` gate's ``enforce_enabled``), it is awaited BEFORE any tenant
    GUC / advisory lock / DB write, so a disabled or revoked gate refuses the reservation
    at its source — never at the delivery inbox alone. A raised exception propagates
    unchanged (the caller maps it to a 403), and NOTHING is written.

    ``after_locks_acquired`` is a test-only deterministic injection point (default
    ``None``; production callers never pass it): it is awaited once, with every
    advisory lock held but BEFORE the fresh overlap read, so a concurrency test can
    interleave a second transaction and certify end-to-end serialization without sleeps.

    The caller must use a PostgreSQL READ COMMITTED transaction (READ UNCOMMITTED
    has equivalent statement snapshots). After a lock wait, admission must see
    the preceding holder's committed reservations, including legacy peak-capacity rows.

    Period volume is opt-in, not an authority grant. Only an owner-side resolver may
    mark a resource as requiring a budget and supply the current approved quota net of
    settled use. Resolution and settlement must share the same lock and transaction
    contract. No existing groundwater eligibility gate is changed by this seam.
    """

    if not resources:
        raise ValueError("NO_HYDRAULIC_RESOURCES")
    if requested_end <= requested_start:
        raise ValueError("REQUEST_INTERVAL_INVALID")
    # Reject duplicate resource requests before any lock/write — a caller asking to
    # reserve the same node twice in one request is a bug, not a silent dedup.
    resource_ids = [r.resource_node_id for r in resources]
    if len(resource_ids) != len(set(resource_ids)):
        raise ValueError("DUPLICATE_HYDRAULIC_RESOURCE")

    needs_period_budget = any(r.requires_period_volume_budget for r in resources)
    if needs_period_budget and resolve_period_volume_budget is None:
        raise ValueError("PERIOD_VOLUME_BUDGET_REQUIRED")

    # Activation enforcement AT THE SOURCE: gate the reservation before any side effect.
    # A disabled/revoked gate raises here, so no lock is taken and no row is written.
    if activation_guard is not None:
        await activation_guard()

    if not conn.is_in_transaction():
        raise ValueError(
            "PERIOD_VOLUME_TRANSACTION_REQUIRED"
            if needs_period_budget
            else "RESERVATION_TRANSACTION_REQUIRED"
        )
    # The lock covers a fresh admission read and all writes through the caller's commit.
    isolation = await conn.fetchval("SELECT current_setting('transaction_isolation')")
    if isolation not in ("read committed", "read uncommitted"):
        raise ValueError(
            "PERIOD_VOLUME_FRESH_SNAPSHOT_REQUIRED"
            if needs_period_budget
            else "RESERVATION_FRESH_SNAPSHOT_REQUIRED"
        )

    tenant = str(tenant_id)
    await conn.execute(SET_TENANT_SQL, tenant)

    # Deterministic, deadlock-safe lock order over the distinct resources.
    ordered = ordered_resources(
        ResourceRef(tenant_id, "hydraulic_node", r.resource_node_id, r.policy) for r in resources
    )
    for ref in ordered:
        await conn.execute(ADVISORY_XACT_LOCK_SQL, advisory_lock_key(ref))

    # All advisory locks held, nothing read/written yet — deterministic test interleave point.
    if after_locks_acquired is not None:
        await after_locks_acquired()

    idem = idempotency_key or f"{execution_ref_type}:{execution_ref_id}"
    reservation_ids: list[str] = []
    peak_over_all = Decimal("0")

    # After locks are held, evaluate every resource against a FRESH overlap read.
    period_evidence: dict[str, dict[str, str]] = {}
    for req in resources:
        budget = None
        read_start, read_end = requested_start, requested_end
        if req.requires_period_volume_budget:
            if resolve_period_volume_budget is None:
                raise ValueError("PERIOD_VOLUME_BUDGET_REQUIRED")
            budget = await resolve_period_volume_budget(conn, req)
            if budget is None:
                raise ValueError("PERIOD_VOLUME_BUDGET_REQUIRED")
            # Include sequential reservations anywhere in the quota period, not
            # just reservations concurrent with this request.
            read_start, read_end = budget.starts_at, budget.ends_at
            period_evidence[str(req.resource_node_id)] = {
                "starts_at": budget.starts_at.isoformat(),
                "ends_at": budget.ends_at.isoformat(),
                "available_m3": str(budget.available_m3),
                "evidence_ref": budget.evidence_ref,
            }
        rows = await conn.fetch(
            OVERLAP_WINDOWS_SQL, tenant, req.resource_node_id, read_start, read_end
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
            period_volume_budget=budget,
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
        min(
            (r.derated_capacity_m3h for r in resources if r.derated_capacity_m3h is not None),
            default=None,
        ),  # maximum_safe_flow_m3h from authoritative capability resolution
        min(
            (r.derated_capacity_m3h for r in resources if r.derated_capacity_m3h is not None),
            default=None,
        ),
        peak_over_all,
        max(
            Decimal("0"),
            min(
                (r.derated_capacity_m3h for r in resources if r.derated_capacity_m3h is not None),
                default=peak_over_all,
            )
            - peak_over_all,
        ),
        None,  # bottleneck_node_id remains unset unless a per-node envelope proves it
        True,
        json.dumps([]),
        json.dumps([]),
        json.dumps({"period_volume_budgets": period_evidence} if period_evidence else {}),
        capability_digest,
        telemetry_snapshot_version,
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

    dispatch_intent_id = await execution_port.request_dispatch(
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
        dispatch_intent_id=dispatch_intent_id,
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
    """Record a failed dispatch atomically within the caller's transaction."""

    if not conn.is_in_transaction():
        raise ValueError("COMPENSATION_TRANSACTION_REQUIRED")
    ids = sorted(UUID(value) for value in reservation_ids)
    if not ids:
        raise ValueError("COMPENSATION_RESERVATIONS_REQUIRED")
    if len(set(ids)) != len(ids):
        raise ValueError("COMPENSATION_DUPLICATE_RESERVATION")

    # The request reference identifies this operation. The tenant predicate on the
    # locked rows determines which reservations the operation may change.
    payload = json.dumps(
        {
            "reason": reason,
            "execution_request_ref": execution_request_ref,
            "reservation_scope_sha256": hashlib.sha256(
                b"".join(rid.bytes for rid in ids)
            ).hexdigest(),
        }
    )
    async with conn.transaction():
        await conn.execute(SET_TENANT_SQL, str(tenant_id))
        rows = await conn.fetch(
            """SELECT reservation_id, evaluation_id, execution_ref_type, execution_ref_id,
                      correlation_id, state
               FROM irrigation_resource_reservations
               WHERE tenant_id = $1 AND reservation_id = ANY($2::uuid[])
               ORDER BY reservation_id FOR UPDATE""",
            tenant_id,
            ids,
        )
        if len(rows) != len(ids):
            raise ValueError("COMPENSATION_RESERVATION_NOT_FOUND")
        groups = {
            (
                row["evaluation_id"],
                row["execution_ref_type"],
                row["execution_ref_id"],
                row["correlation_id"],
            )
            for row in rows
        }
        if len(groups) != 1:
            raise ValueError("COMPENSATION_GROUP_MISMATCH")

        states = {row["state"] for row in rows}
        if states == {"cancelled"}:
            matching = await conn.fetchval(
                """SELECT count(*) FROM irrigation_resource_reservation_events
                   WHERE tenant_id = $1 AND reservation_id = ANY($2::uuid[])
                     AND event_type = 'cancelled' AND causation_id IS NULL AND payload = $3::jsonb""",
                tenant_id,
                ids,
                payload,
            )
            if matching == len(ids):
                return
        if not states <= {"reserved", "active"}:
            raise ValueError("COMPENSATION_CONFLICT")

        correlation_id = rows[0]["correlation_id"]
        mark_failed = execution_port.mark_dispatch_failed
        kwargs = {
            "execution_request_ref": execution_request_ref,
            "reason": reason,
            "correlation_id": str(correlation_id) if correlation_id else None,
        }
        signature = inspect.signature(mark_failed)
        try:
            signature.bind(conn, **kwargs)
        except TypeError:
            # Legacy ports predate correlation_id. Select the signature before any writes.
            del kwargs["correlation_id"]
            signature.bind(conn, **kwargs)

        for rid in ids:
            await conn.execute(CANCEL_RESERVATION_SQL, tenant_id, rid, reason)
            await conn.execute(
                INSERT_RESERVATION_EVENT_SQL,
                tenant_id,
                rid,
                "cancelled",
                None,
                correlation_id or rid,
                payload,
            )
        await mark_failed(conn, **kwargs)
