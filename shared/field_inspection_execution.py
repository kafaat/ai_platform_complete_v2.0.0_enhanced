"""Pure contracts for field-inspection execution across coordinator and owner.

This module performs no service or database I/O. The platform coordinates the
request; field-management owns tasks, evidence and acknowledgements; decision
independently reads current owner proof before accepting a successful outcome.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid5

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

FIELD_EDIT = "field:edit"
FIELD_VIEW = "field:view"
INSPECTION_REVIEW = "inspection:review"


class Caller(Protocol):
    tenant_id: str
    user_id: str
    role: str

    def can(self, permission: str) -> bool: ...


def require(caller: Caller, permission: str) -> Caller:
    if not caller.can(permission):
        raise HTTPException(403, "permission_denied")
    return caller


TASK_NAMESPACE = UUID("da3b1315-7c73-5fd2-8886-658fc6d70192")
PROVIDER = "field-management-service"
OPERATION = "field_inspection"
SCHEMA = "sahool.field-inspection-execution-proof/v1"
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def refuse(code: str, status: int = 409) -> HTTPException:
    return HTTPException(status, {"code": code})


def canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def iso(value: datetime | str) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise refuse("inspection_time_must_be_aware", 422)
    return value.astimezone(UTC).isoformat()


def identifier(value: Any) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise refuse("invalid_execution_reference", 422)
    return value


class InspectionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pin_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")
    assigned_to: int = Field(strict=True, gt=0, le=2147483647)
    due_at: AwareDatetime
    priority: int = Field(strict=True, ge=1, le=5)

    def stable(self) -> dict:
        return {
            "pin_id": self.pin_id,
            "assigned_to": self.assigned_to,
            "due_at": iso(self.due_at),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class ExecutionBinding:
    tenant_id: str
    execution_request_id: str
    task_id: str
    field_id: str
    pin_id: str
    decision_id: str
    execution_plan_id: str
    dispatch_authorization_id: str
    correlation_id: str
    assigned_to: str
    due_at: str
    priority: int
    request_digest: str
    adapter_id: str
    receipt_id: str
    received_by: str
    operation_type: str = OPERATION

    @classmethod
    def from_record(cls, record: dict) -> ExecutionBinding:
        data = {f.name: record[f.name] for f in fields(cls)}
        for key in ("tenant_id", "task_id", "correlation_id"):
            data[key] = str(data[key])
        data["due_at"] = iso(data["due_at"])
        data["request_digest"] = str(data["request_digest"]).strip()
        return cls(**data)

    def receipt_payload(self) -> dict:
        return {
            "provider": PROVIDER,
            "operation_type": OPERATION,
            "provider_task_id": self.task_id,
            "task_ref": "urn:sahool:task:" + self.task_id,
            "tenant_id": self.tenant_id,
            "field_id": self.field_id,
            "pin_id": self.pin_id,
            "execution_request_id": self.execution_request_id,
            "decision_id": self.decision_id,
            "execution_plan_id": self.execution_plan_id,
            "dispatch_authorization_id": self.dispatch_authorization_id,
            "correlation_id": self.correlation_id,
            "persisted": True,
        }


@dataclass(frozen=True)
class ExecutionSettings:
    enabled: bool = False
    adapter_id: str = "field-management-service-inspection-v1"
    token_key: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> ExecutionSettings:
        return cls(
            enabled=os.getenv("FIELD_INSPECTION_EXECUTION_ENABLED", "0").strip().lower()
            in {"1", "true", "yes", "on"},
            adapter_id=os.getenv(
                "FIELD_INSPECTION_EXECUTION_ADAPTER_ID", "field-management-service-inspection-v1"
            ),
            token_key=os.getenv("FIELD_INSPECTION_DELIVERY_TOKEN_KEY", ""),
        )

    def check(self) -> None:
        if not self.enabled:
            raise refuse("field_inspection_execution_disabled", 503)
        if len(self.token_key.encode()) < 32:
            raise refuse("field_inspection_delivery_key_unconfigured", 503)
        identifier(self.adapter_id)

    def token(self, tenant: str, request_id: str) -> str:
        # Secret-bound, stable across restart; never stored in a row or returned to a browser.
        self.check()
        raw = canonical([str(UUID(tenant)), identifier(request_id), self.adapter_id])
        return hmac.new(self.token_key.encode(), raw.encode(), hashlib.sha256).hexdigest()


def binding_from_source(
    caller: Caller,
    item: dict,
    lineage: dict,
    plan: dict,
    expected_field_id: str,
    adapter_id: str,
) -> ExecutionBinding:
    """Only an explicit pin/assignee contract bound to the approved plan is deliverable."""
    if item.get("target_type") != "task" or item.get("operation_type") != OPERATION:
        raise refuse("only_field_inspection_tasks_are_supported", 422)
    decision_id = identifier(item.get("decision_id"))
    request_id = identifier(item.get("execution_request_id"))
    plan_id = identifier(item.get("execution_plan_id"))
    authorization_id = identifier(item.get("dispatch_authorization_id"))
    tenant = str(UUID(caller.tenant_id))
    decision = lineage.get("decision")
    if (
        lineage.get("authoritative") is not True
        or lineage.get("tenant_id") != tenant
        or lineage.get("decision_id") != decision_id
        or not isinstance(decision, dict)
        or decision.get("decision_id") != decision_id
    ):
        raise refuse("decision_lineage_unproven", 503)
    field_id = decision.get("field_id")
    if not isinstance(field_id, str) or not field_id or len(field_id) > 50:
        raise refuse("decision_field_unbound", 409)
    if field_id != expected_field_id:
        raise refuse("execution_field_mismatch", 404)
    if (
        plan.get("authoritative") is not True
        or plan.get("tenant_id") != tenant
        or plan.get("execution_plan_id") != plan_id
        or plan.get("decision_id") != decision_id
        or plan.get("field_id") != field_id
        or plan.get("operation_type") != OPERATION
        or plan.get("plan_state") != "planned"
        or plan.get("bound") is not True
        or plan.get("review_state") != "approved"
        or not _DIGEST.fullmatch(str(plan.get("plan_digest") or ""))
        or not _DIGEST.fullmatch(str(plan.get("decision_value_digest") or ""))
        or plan.get("decision_value_digest") != plan.get("current_decision_value_digest")
        or plan.get("target_zone_ids") != [field_id]
    ):
        raise refuse("inspection_plan_unbound", 409)
    command = item.get("command_payload")
    constraints = plan.get("constraints")
    if (
        not isinstance(command, dict)
        or set(command) != {"field_id", "inspection"}
        or command.get("field_id") != field_id
        or not isinstance(constraints, dict)
        or constraints.get("field_id") != field_id
    ):
        raise refuse("inspection_payload_scope_mismatch", 422)
    try:
        spec = InspectionSpec.model_validate(command["inspection"])
        approved = InspectionSpec.model_validate(constraints.get("inspection"))
    except ValidationError:
        raise refuse("invalid_inspection_payload", 422) from None
    if spec.stable() != approved.stable():
        raise refuse("inspection_payload_not_in_plan", 409)
    if item.get("target_id") != spec.pin_id:
        raise refuse("inspection_target_pin_mismatch", 409)
    try:
        correlation_id = str(UUID(str(decision.get("correlation_id"))))
    except (TypeError, ValueError):
        raise refuse("decision_correlation_unbound", 409) from None
    source = {
        "tenant_id": tenant,
        "execution_request_id": request_id,
        "decision_id": decision_id,
        "execution_plan_id": plan_id,
        "dispatch_authorization_id": authorization_id,
        "field_id": field_id,
        "correlation_id": correlation_id,
        "operation_type": OPERATION,
        "inspection": spec.stable(),
        "plan_digest": plan["plan_digest"],
        "decision_value_digest": plan["decision_value_digest"],
    }
    task_id = str(uuid5(TASK_NAMESPACE, canonical([tenant, request_id])))
    receipt_id = "ftr_" + digest([adapter_id, tenant, request_id])[:32]
    return ExecutionBinding(
        tenant,
        request_id,
        task_id,
        field_id,
        spec.pin_id,
        decision_id,
        plan_id,
        authorization_id,
        correlation_id,
        str(spec.assigned_to),
        iso(spec.due_at),
        spec.priority,
        digest(source),
        adapter_id,
        receipt_id,
        caller.user_id,
    )


def _operator(caller: Caller, *, verification: bool = False) -> None:
    require(caller, INSPECTION_REVIEW if verification else FIELD_EDIT)
    # Preserve the existing BFF's DECISION_EXECUTE boundary (owner/manager).
    if caller.role not in {"owner", "manager"}:
        raise refuse("decision_execute_required", 403)


def outcome_payload(proof: dict) -> dict:
    return {
        key: proof[key]
        for key in (
            "execution_plan_id",
            "dispatch_authorization_id",
            "decision_id",
            "receipt_id",
            "evidence_snapshot_id",
            "actual",
            "metrics",
            "idempotency_key",
        )
    } | {"verification_state": "verified_success"}
