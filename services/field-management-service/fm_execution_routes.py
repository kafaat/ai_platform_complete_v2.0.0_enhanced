"""Private, owner-local inspection commands and the independent DS proof read.

The platform coordinator authenticates the human and supplies source-bound commands.
This module never calls decision-service. Store calls retain their own tenant/user
transactions; authoritative confirmations and historical acknowledgements stay here.
"""

from __future__ import annotations

import hmac
import os
import re
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Path, Response
from fm_execution_task_store import PostgresExecutionStore
from fm_execution_tasks import (
    ExecutionBinding,
    ExecutionSettings,
    binding_from_source,
    identifier,
    iso,
    refuse,
)
from fm_gateway import (
    FIELD_EDIT,
    FIELD_VIEW,
    INSPECTION_REVIEW,
    Caller,
    canonical_role,
    require,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

router = APIRouter()
OWNER_SCHEMA = "sahool.field-inspection-owner/v1"
Operation = Literal[
    "require-field",
    "get-link",
    "list-links",
    "validate-binding",
    "ensure-task",
    "readback",
    "preview-confirmation",
    "prepare-confirmation",
    "save-outcome",
]
FieldReference = Annotated[str, Field(min_length=1, max_length=50)]
Reference = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")]
RequestId = Annotated[str, Path(min_length=1, max_length=200)]


class StrictCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FieldCommand(StrictCommand):
    field_id: FieldReference


class RequestCommand(StrictCommand):
    execution_request_id: Reference


class FieldRequestCommand(FieldCommand, RequestCommand):
    pass


class ListCommand(FieldCommand):
    limit: int = Field(default=50, ge=1, le=100)


class SourceEnvelope(StrictCommand):
    # These are native DS projections, not a caller-chosen ExecutionBinding.
    # The pure binding contract validates their required lineage/plan semantics.
    item: dict[str, Any]
    lineage: dict[str, Any]
    plan: dict[str, Any]


class SourceCommand(FieldRequestCommand):
    source: SourceEnvelope


class ClaimedRequest(StrictCommand):
    authoritative: bool
    persisted: bool
    execution_request_id: Reference
    adapter_id: Reference
    adapter_kind: Literal["task"]
    delivery_state: Literal["delivering"]


class EnsureCommand(SourceCommand):
    claim: ClaimedRequest


class TaskCommand(FieldCommand):
    task_id: Annotated[
        str,
        Field(
            pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        ),
    ]


class OutcomeResult(StrictCommand):
    """The source verify-outcome response, never a browser-supplied proof."""

    status: Literal["ok"]
    authoritative: bool
    persisted: bool
    outcome_id: Reference
    execution_request_id: Reference
    execution_plan_id: Reference
    dispatch_authorization_id: Reference
    decision_id: Reference
    receipt_id: Reference
    verification_state: Literal["verified_success"]
    evidence_snapshot_id: Annotated[str, Field(pattern=r"^inspection_[0-9a-f]{64}$")]
    success: bool
    verified_by: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,9}$")]
    verified_at: Annotated[str, Field(min_length=1, max_length=64)]
    accepted: bool | None = None
    tenant_id: str | None = None
    replay: bool = False

    @field_validator("verified_at")
    @classmethod
    def aware_time(cls, value: str) -> str:
        try:
            iso(value)
        except Exception as exc:
            raise ValueError("verified_at must be an aware ISO timestamp") from exc
        return value


class AcknowledgementCommand(RequestCommand):
    confirmation_id: Annotated[str, Field(pattern=r"^fic_[0-9a-f]{32}$")]
    result: OutcomeResult


_COMMAND_MODELS: dict[str, type[StrictCommand]] = {
    "require-field": FieldCommand,
    "get-link": RequestCommand,
    "list-links": ListCommand,
    "validate-binding": SourceCommand,
    "ensure-task": EnsureCommand,
    "readback": FieldRequestCommand,
    "preview-confirmation": RequestCommand,
    "prepare-confirmation": TaskCommand,
    "save-outcome": AcknowledgementCommand,
}
_READ_OPERATIONS = {"require-field", "get-link", "list-links", "readback"}
_IMMUTABLE_RESULT = (
    "status",
    "authoritative",
    "persisted",
    "outcome_id",
    "execution_request_id",
    "execution_plan_id",
    "dispatch_authorization_id",
    "decision_id",
    "receipt_id",
    "verification_state",
    "evidence_snapshot_id",
    "success",
    "verified_by",
    "verified_at",
)


def _coordinator_caller(
    coordinator_token: str | None = Header(None, alias="X-Field-Inspection-Coordinator-Token"),
    service_name: str | None = Header(None, alias="X-Service-Name"),
    tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    user_id: str | None = Header(None, alias="X-User-Id"),
    user_role: str | None = Header(None, alias="X-User-Role"),
    gateway_token: str | None = Header(None, alias="X-Field-Tasks-Token"),
) -> Caller:
    if gateway_token is not None:
        raise refuse("inspection_owner_coordinator_only", 403)
    expected = os.getenv("FIELD_INSPECTION_COORDINATOR_TOKEN", "").strip()
    if not expected:
        raise refuse("field_inspection_coordinator_token_unconfigured", 503)
    if not hmac.compare_digest((coordinator_token or "").encode(), expected.encode()):
        raise refuse("field_inspection_coordinator_token_required", 401)
    if service_name != "sahool-platform":
        raise refuse("field_inspection_coordinator_service_required", 403)
    if not ExecutionSettings.from_env().enabled:
        raise refuse("field_inspection_execution_disabled", 503)
    try:
        tenant = str(UUID(tenant_id or ""))
    except (ValueError, TypeError):
        raise refuse("invalid_trusted_tenant", 403) from None
    uid = (user_id or "").strip()
    role = canonical_role(user_role)
    if not re.fullmatch(r"[1-9][0-9]{0,9}", uid) or int(uid) > 2147483647 or not role:
        raise refuse("trusted_tenant_and_user_required", 403)
    return Caller(tenant, uid, role)


def _authorize_operation(caller: Caller, operation: Operation) -> None:
    if operation in _READ_OPERATIONS:
        require(caller, FIELD_VIEW)
        return
    permission = (
        FIELD_EDIT if operation in {"validate-binding", "ensure-task"} else INSPECTION_REVIEW
    )
    require(caller, permission)
    if caller.role not in {"owner", "manager"}:
        raise refuse("decision_execute_required", 403)


def _parse_command(operation: Operation, payload: dict) -> StrictCommand:
    try:
        return _COMMAND_MODELS[operation].model_validate(payload)
    except ValidationError:
        # Do not echo raw source payloads, arbitrary result bodies or credentials.
        raise refuse("invalid_inspection_owner_command", 422) from None


def _source_binding(caller: Caller, command: SourceCommand) -> ExecutionBinding:
    source = command.source
    try:
        binding = binding_from_source(
            caller,
            source.item,
            source.lineage,
            source.plan,
            command.field_id,
            identifier(ExecutionSettings.from_env().adapter_id),
        )
    except (ValueError, TypeError, KeyError):
        raise refuse("invalid_inspection_source_envelope", 422) from None
    if binding.execution_request_id != command.execution_request_id:
        raise refuse("execution_request_binding_mismatch", 409)
    return binding


async def _owner_link(store, caller: Caller, request_id: str) -> dict:
    link = await store.get_link(caller, request_id)
    if link is None:
        raise refuse("inspection_execution_link_not_found", 404)
    if link.get("tenant_id") != caller.tenant_id or link.get("execution_request_id") != request_id:
        raise refuse("inspection_owner_link_unproven", 503)
    return link


def _check_result(caller: Caller, command: AcknowledgementCommand, link: dict) -> dict:
    result = command.result.model_dump(exclude_unset=True)
    expected = {
        "execution_request_id": command.execution_request_id,
        "execution_plan_id": link["execution_plan_id"],
        "dispatch_authorization_id": link["dispatch_authorization_id"],
        "decision_id": link["decision_id"],
        "receipt_id": link["receipt_id"],
        "verified_by": caller.user_id,
    }
    snapshot = result["evidence_snapshot_id"]
    if (
        any(result.get(key) is not True for key in ("authoritative", "persisted", "success"))
        or any(result.get(key) != value for key, value in expected.items())
        or ("accepted" in result and result["accepted"] is not True)
        or ("tenant_id" in result and result["tenant_id"] != caller.tenant_id)
        or command.confirmation_id != "fic_" + snapshot.removeprefix("inspection_")[:32]
    ):
        raise refuse("inspection_outcome_unproven", 409)
    return result


def _result_projection(result: dict) -> dict:
    checked = OutcomeResult.model_validate(result)
    data = checked.model_dump()
    data["verified_at"] = iso(data["verified_at"])
    return {key: data[key] for key in _IMMUTABLE_RESULT}


async def _save_acknowledgement(store, caller: Caller, command: AcknowledgementCommand) -> dict:
    link = await _owner_link(store, caller, command.execution_request_id)
    result = _check_result(caller, command, link)
    # Only owner-resolved link IDs and the confirmation reference reach the store.
    # v291 resolves that historical confirmation and validates the DS response.
    # Re-reading CURRENT proof here would wrongly reject a committed historical ack.
    projection = {
        "confirmation_id": command.confirmation_id,
        "execution_request_id": link["execution_request_id"],
        "task_id": link["task_id"],
        "field_id": link["field_id"],
    }
    saved = await store.save_outcome(caller, projection, result)
    expected = {
        **projection,
        "tenant_id": caller.tenant_id,
        "outcome_id": result["outcome_id"],
    }
    try:
        proven = all(
            saved.get(key) == value for key, value in expected.items()
        ) and _result_projection(saved["upstream_result"]) == _result_projection(result)
    except (KeyError, TypeError, ValidationError, ValueError):
        proven = False
    if not proven:
        raise refuse("inspection_outcome_acknowledgement_unproven", 409)
    return saved


@router.post("/internal/field-inspection-execution-owner/{operation}")
async def execute_owner_command(
    operation: Operation,
    response: Response,
    payload: dict[str, Any] = Body(...),
    caller: Caller = Depends(_coordinator_caller),
) -> dict:
    _authorize_operation(caller, operation)
    command = _parse_command(operation, payload)
    store = PostgresExecutionStore()
    if operation == "require-field":
        data = await store.require_field(caller, command.field_id)
    elif operation == "get-link":
        data = await store.get_link(caller, command.execution_request_id)
        if data is not None and (
            data.get("tenant_id") != caller.tenant_id
            or data.get("execution_request_id") != command.execution_request_id
        ):
            raise refuse("inspection_owner_link_unproven", 503)
    elif operation == "list-links":
        await store.require_field(caller, command.field_id)
        data = await store.list_links(caller, command.field_id, command.limit)
    elif operation == "validate-binding":
        data = await store.validate(caller, _source_binding(caller, command))
    elif operation == "ensure-task":
        binding = _source_binding(caller, command)
        claim = command.claim
        if (
            claim.authoritative is not True
            or claim.persisted is not True
            or claim.execution_request_id != binding.execution_request_id
            or claim.adapter_id != binding.adapter_id
        ):
            raise refuse("execution_claim_unproven", 409)
        data = await store.ensure_task(caller, binding)
    elif operation == "readback":
        link = await _owner_link(store, caller, command.execution_request_id)
        if link["field_id"] != command.field_id:
            raise refuse("execution_field_mismatch", 404)
        data = await store.readback(caller, ExecutionBinding.from_record(link))
    elif operation == "preview-confirmation":
        link = await _owner_link(store, caller, command.execution_request_id)
        data = await store.preview_confirmation(caller, link)
    elif operation == "prepare-confirmation":
        data = await store.prepare_confirmation(
            caller, str(UUID(command.task_id)), command.field_id
        )
    elif operation == "save-outcome":
        data = await _save_acknowledgement(store, caller, command)
    else:
        # Both the Literal path and the closed command model map reject unknown actions.
        raise refuse("unsupported_inspection_owner_operation", 422)
    response.headers["Cache-Control"] = "no-store"
    return {
        "schema": OWNER_SCHEMA,
        "authoritative": True,
        "tenant_id": caller.tenant_id,
        "operation": operation,
        "data": data,
    }


def _proof_tenant(
    proof_token: str | None = Header(None, alias="X-Field-Inspection-Proof-Token"),
    tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    gateway_token: str | None = Header(None, alias="X-Field-Tasks-Token"),
) -> str:
    if gateway_token is not None:
        raise refuse("inspection_proof_service_only", 403)
    expected = os.getenv("FIELD_INSPECTION_PROOF_TOKEN", "").strip()
    if not expected:
        raise refuse("field_inspection_proof_token_unconfigured", 503)
    if not hmac.compare_digest((proof_token or "").encode(), expected.encode()):
        raise refuse("field_inspection_proof_token_required", 401)
    if not ExecutionSettings.from_env().enabled:
        raise refuse("field_inspection_execution_disabled", 503)
    try:
        return str(UUID(tenant_id or ""))
    except (ValueError, TypeError):
        raise refuse("invalid_tenant_id", 400) from None


@router.get("/internal/field-tasks/execution-proofs/{execution_request_id}")
async def read_inspection_execution_proof(
    execution_request_id: RequestId,
    response: Response,
    tenant_id: str = Depends(_proof_tenant),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return await PostgresExecutionStore().read_execution_proof(
        tenant_id, identifier(execution_request_id)
    )
