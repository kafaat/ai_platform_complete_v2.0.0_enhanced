"""IRR-F01 Gate B — the real ExecutionRequestPort bound to the existing outbox.

Implements the ``ExecutionRequestPort`` used by ``irrigation_reservation_adapter``:
a committed reservation writes an ``irrigation.reservation.dispatch_requested`` event
through the EXISTING ``emit_event`` outbox on the SAME transaction connection — so the
reservation and the dispatch INTENT are atomic. It does NOT create a new execution SoR
and does NOT mark anything ``dispatched``: the existing outbox worker delivers the event
and creates the existing ``execution_request`` (that live delivery + decision-service
handoff is the remaining Gate-B integration step). Compensation emits
``irrigation.reservation.dispatch_failed``.

The event type strings are registered EventType members
(``IRRIGATION_RESERVATION_DISPATCH_REQUESTED`` / ``_FAILED``) so downstream catalog and
routing stay consistent.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from core.event_schema import new_event, validate_envelope

from api.event_bus import EventType

# emit_event(event_type, entity_type, entity_id, tenant_id, payload, source, actor_id,
#            command_id, occurred_at) -> event_id (NULL on idempotent duplicate).
_EMIT_EVENT_SQL = """
SELECT emit_event(
    $1::text, $2::text, $3::text, $4::uuid, $5::jsonb, $6::text, $7::text, $8::uuid, $9::timestamptz
)
"""

# events.entity_type is a CHECK'd coarse category (v11 + v51:
# field/farm/operation/equipment/sensor/well/sample/season/user/activity/soil_lab_test).
# A reservation dispatch is an operational intent → 'operation'. Using an out-of-set
# value would be rejected by the CHECK (and, as a non-critical emit, silently swallowed).
# The fine-grained meaning lives in event_type (irrigation.reservation.dispatch_requested).
_ENTITY_TYPE = "operation"


async def _emit(
    conn: Any,
    *,
    event_type: str,
    entity_id: str,
    tenant_id: str,
    payload: dict[str, Any],
    correlation_id: str | None,
    occurred_at: datetime,
) -> str | None:
    envelope = new_event(
        event_type,
        _ENTITY_TYPE,
        entity_id,
        tenant_id,
        payload=payload,
        source="system",
        correlation_id=correlation_id,
    )
    errors = validate_envelope(envelope)
    if errors:
        raise ValueError(f"invalid reservation dispatch envelope: {'; '.join(errors)}")
    args = envelope.to_emit_args()
    event_id = await conn.fetchval(
        _EMIT_EVENT_SQL,
        args["event_type"],
        args["entity_type"],
        str(args["entity_id"]),
        UUID(args["tenant_id"]),
        json.dumps(args["payload"]),
        args["source"],
        args["actor_id"],
        UUID(args["command_id"]) if args["command_id"] else None,
        occurred_at,
    )
    return str(event_id) if event_id is not None else None


class EmitEventExecutionRequestPort:
    """Writes the dispatch INTENT to the existing outbox, atomic with the reservation."""

    def __init__(self, *, now: datetime | None = None) -> None:
        self._now = now

    def _timestamp(self) -> datetime:
        return self._now or datetime.now(UTC)

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
    ) -> str:
        payload = {
            "evaluation_id": evaluation_id,
            "reservation_ids": list(reservation_ids),
            "execution_ref_type": execution_ref_type,
            "execution_ref_id": execution_ref_id,
            "state": "dispatch_requested",
        }
        event_id = await _emit(
            conn,
            event_type=EventType.IRRIGATION_RESERVATION_DISPATCH_REQUESTED.value,
            entity_id=evaluation_id,
            tenant_id=tenant_id,
            payload=payload,
            correlation_id=correlation_id,
            occurred_at=self._timestamp(),
        )
        # A None event_id means the outbox already carries this intent (idempotent
        # replay); the reference is the stable execution ref, not a new row.
        return event_id or f"dispatch-requested:{execution_ref_type}:{execution_ref_id}"

    async def mark_dispatch_failed(
        self, conn: Any, *, execution_request_ref: str, reason: str
    ) -> None:
        tenant_id = await conn.fetchval("select current_setting('app.current_tenant', true)")
        if not tenant_id:
            raise ValueError("dispatch-failed emit requires app.current_tenant")
        await _emit(
            conn,
            event_type=EventType.IRRIGATION_RESERVATION_DISPATCH_FAILED.value,
            entity_id=execution_request_ref,
            tenant_id=tenant_id,
            payload={"execution_request_ref": execution_request_ref, "reason": reason},
            correlation_id=None,
            occurred_at=self._timestamp(),
        )
