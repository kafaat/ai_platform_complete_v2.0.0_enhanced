"""Session-authenticated inspection coordination; field ownership stays remote.

Only route identifiers cross this public boundary. The coordinator resolves the
decision, assignment and approved evidence from their authoritative services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from core.authorization import Permission, has_permission
from core.canonical_schemas import UserRole, UserSchema
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict

from api.inspection_execution_adapter import build_adapter
from api.main import require_permission
from shared.field_inspection_execution import identifier, refuse


class _NoStoreRoute(APIRoute):
    """Apply the same cache policy to success, validation and authorization replies."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store(request: Request) -> Response:
            try:
                response = await handler(request)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), "Cache-Control": "no-store"}
                raise
            except RequestValidationError as exc:
                response = await request_validation_exception_handler(request, exc)
            response.headers["Cache-Control"] = "no-store"
            return response

        return no_store


router = APIRouter(prefix="/api/v1/inspection-executions", route_class=_NoStoreRoute)
FieldId = Annotated[str, Path(min_length=1, max_length=50)]
RequestId = Annotated[str, Path(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")]


class OwnerResolvedCommand(BaseModel):
    """The browser cannot supply assignment, tenant or execution evidence."""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class SessionCaller:
    user: UserSchema
    tenant_id: str
    user_id: str
    role: str

    def can(self, permission: str) -> bool:
        try:
            canonical_permission = Permission(permission)
        except ValueError:
            return False
        return has_permission(self.user, canonical_permission)


def _caller(user: UserSchema, *, operator: bool = False) -> SessionCaller:
    if operator and user.role not in {UserRole.OWNER, UserRole.MANAGER}:
        raise refuse("decision_execute_required", 403)
    if not isinstance(user.user_id, str) or not user.user_id.strip():
        raise refuse("trusted_tenant_and_user_required", 403)
    try:
        tenant_id = str(UUID(user.tenant_id))
    except (TypeError, ValueError, AttributeError):
        raise refuse("invalid_trusted_tenant", 403) from None
    return SessionCaller(user, tenant_id, user.user_id, user.role.value)


@router.get("/fields/{field_id}")
async def list_inspection_executions(
    field_id: FieldId,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
) -> dict:
    caller = _caller(user)
    return await build_adapter().list_for_field(caller, field_id, limit=limit)


@router.post("/fields/{field_id}/requests/{execution_request_id}/receive")
async def receive_inspection_execution(
    field_id: FieldId,
    execution_request_id: RequestId,
    command: OwnerResolvedCommand = Body(...),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
) -> dict:
    caller = _caller(user, operator=True)
    return await build_adapter().receive(
        caller, identifier(execution_request_id), expected_field_id=field_id
    )


@router.post("/fields/{field_id}/tasks/{task_id}/verify")
async def verify_inspection_execution(
    field_id: FieldId,
    task_id: UUID,
    command: OwnerResolvedCommand = Body(...),
    user: UserSchema = Depends(require_permission(Permission.INSPECTION_REVIEW)),
) -> dict:
    caller = _caller(user, operator=True)
    return await build_adapter().verify(caller, str(task_id), expected_field_id=field_id)
