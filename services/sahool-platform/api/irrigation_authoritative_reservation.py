"""Single governed entry point: intent → authoritative resolution → atomic reservation intent."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from api.irrigation_authoritative_resolver import resolve_authoritative_intent
from api.irrigation_reservation_adapter import (
    ExecutionRequestPort,
    ReservationOutcome,
    reserve_and_request_dispatch_db,
)


async def reserve_authoritative_intent(
    conn: Any,
    *,
    tenant_id: UUID,
    project_id: UUID,
    target_type: str,
    target_id: str,
    target_version_id: str,
    requested_start: datetime,
    requested_end: datetime,
    requested_flow_m3h: Decimal,
    execution_ref_type: str,
    execution_ref_id: str,
    calculation_model_version: str,
    execution_port: ExecutionRequestPort,
    correlation_id: UUID,
    activation_guard=None,
) -> ReservationOutcome:
    resolved = await resolve_authoritative_intent(
        conn,
        tenant_id=tenant_id,
        project_id=project_id,
        target_type=target_type,
        target_id=target_id,
        target_version_id=target_version_id,
        at_time=requested_start,
        requested_flow_m3h=requested_flow_m3h,
    )
    return await reserve_and_request_dispatch_db(
        conn,
        tenant_id=tenant_id,
        project_id=project_id,
        requested_start=requested_start,
        requested_end=requested_end,
        resources=resolved.resources,
        execution_ref_type=execution_ref_type,
        execution_ref_id=execution_ref_id,
        calculation_model_version=calculation_model_version,
        execution_port=execution_port,
        correlation_id=correlation_id,
        canonical_hydraulic_capability_id=resolved.capability_id,
        activation_guard=activation_guard,
    )
