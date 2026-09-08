#!/usr/bin/env python3
"""Durable, tenant-scoped human review; a workflow ID exists only after commit.

Notification delivery has no configured consumer. Persisted workflows are queryable,
but neither creation nor escalation claims an expert has been notified.
"""

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "")
_pool: asyncpg.Pool | None = None
EXPERT_ROLES = {
    "chemical": ["agronomist", "pesticide_expert"],
    "environmental": ["agronomist", "water_specialist"],
    "economic": ["financial_advisor", "cooperative_manager"],
    "general": ["agronomist", "admin"],
}
APPROVER_ROLES = frozenset(role for roles in EXPERT_ROLES.values() for role in roles) | {
    "regional_manager"
}


class WorkflowUnavailable(RuntimeError):
    """Persistence was unavailable; no approval or successful creation is implied."""


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None and DATABASE_URL:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    if _pool is None:
        raise WorkflowUnavailable("Approval database is not configured")
    return _pool


@asynccontextmanager
async def _tenant_connection(tenant_id: str):
    tenant_id = str(uuid.UUID(tenant_id))
    try:
        pool = await _get_pool()
        if pool is None:
            raise WorkflowUnavailable("Approval database is not configured")
        async with pool.acquire() as conn, conn.transaction():
            # Both historic and current RLS policies exist. Set both locally;
            # transaction completion resets them before the pooled connection is reused.
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_id)
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            yield conn
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError) as exc:
        logger.warning("Approval storage failure: %s", type(exc).__name__)
        raise WorkflowUnavailable("Approval storage unavailable") from exc


def _json_list(value: Any) -> list:
    return (json.loads(value) if value else []) if isinstance(value, str) else (value or [])


async def _locked_workflow(conn, workflow_id: str, tenant_id: str):
    return await conn.fetchrow(
        "SELECT * FROM approval_workflows WHERE workflow_id=$1 AND tenant_id::TEXT=$2 FOR UPDATE",
        workflow_id,
        tenant_id,
    )


async def _pending_error(conn, row) -> dict | None:
    if not row:
        return {"error": "Workflow not found", "status": "not_found"}
    if row["status"] != "pending":
        return {"error": f"Workflow already {row['status']}", "status": row["status"]}
    # An unknown deadline cannot authorize an action either.
    if not row["expires_at"] or row["expires_at"] <= datetime.now(UTC):
        await conn.execute(
            "UPDATE approval_workflows SET status='expired', resolved_at=NOW() WHERE workflow_id=$1",
            row["workflow_id"],
        )
        return {"error": "Workflow expired; submit a new validation", "status": "expired"}
    return None


def _role_error(row, expert_role: str) -> dict | None:
    required = row["required_roles"] or []
    if expert_role != "admin" and expert_role not in required:
        return {
            "error": "Expert role not authorized",
            "authorized_roles": required,
            "status": "unauthorized",
        }
    return None


class HumanApprovalWorkflow:
    def __init__(self):
        self._expert_roles = EXPERT_ROLES

    async def create(self, request: Any, checks: list[dict], risk_level: str) -> str:
        # GuardrailsRequest normalizes HTTP input. Defend internal callers as well.
        if (
            isinstance(request.user_id, bool)
            or not isinstance(request.user_id, int)
            or not 0 < request.user_id <= 2147483647
        ):
            raise ValueError("user_id must be a positive users.id integer")
        tenant_id = str(uuid.UUID(request.tenant_id))
        workflow_id = f"SAHOOL-HIL-{uuid.uuid4().hex[:16].upper()}"
        required_experts = set()
        for check in checks:
            if not check.get("passed", True) or check.get("findings"):
                required_experts.update(
                    self._expert_roles.get(check.get("tier"), self._expert_roles["general"])
                )
        if not required_experts:
            required_experts.update(self._expert_roles["general"])
        async with _tenant_connection(tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO approval_workflows (workflow_id, tenant_id, user_id, status, risk_level, action_type, action_data, farm_context, required_roles, approvals, rejections, escalation_count, expires_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
                """,
                workflow_id,
                tenant_id,
                request.user_id,
                "pending",
                risk_level,
                request.action_type,
                json.dumps(request.action_data, allow_nan=False),
                json.dumps(request.farm_context, allow_nan=False),
                sorted(required_experts),
                "[]",
                "[]",
                0,
                datetime.now(UTC) + timedelta(hours=48),
            )
        return workflow_id

    async def approve(
        self,
        workflow_id: str,
        expert_id: str,
        expert_role: str,
        tenant_id: str,
        notes: str = "",
        modifications: dict | None = None,
    ) -> dict:
        if not tenant_id:
            return {"error": "Workflow not found", "status": "not_found"}
        tenant_id = str(uuid.UUID(tenant_id))
        async with _tenant_connection(tenant_id) as conn:
            row = await _locked_workflow(conn, workflow_id, tenant_id)
            error = await _pending_error(conn, row)
            if error:
                return error
            error = _role_error(row, expert_role)
            if error:
                return error
            if modifications:
                return {
                    "status": "requires_revalidation",
                    "error": "Modified actions require a new validation",
                }
            approvals = _json_list(row["approvals"])
            if any(a.get("expert_id") == expert_id for a in approvals):
                return {
                    "status": "pending",
                    "workflow_id": workflow_id,
                    "approvals_received": len(approvals),
                    "message_ar": "سبق أن سجّلت موافقتك على هذا الإجراء.",
                }
            approvals.append(
                {
                    "expert_id": expert_id,
                    "expert_role": expert_role,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "notes": notes,
                }
            )
            required_count = {"LOW": 1, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}[row["risk_level"]]
            status = "approved" if len(approvals) >= required_count else "pending"
            await conn.execute(
                # `status` هو VARCHAR(20) بينما 'approved' حرفيّةٌ نصّيّة، فاستعمالُ
                # `$1` في الإسنادِ والمقارنةِ معاً يستنتج له نوعين متضاربين
                # (character varying مقابل text) فيفشل التحضيرُ بـAmbiguousParameterError
                # قبل أن يُكتَب أيُّ صفّ. التصريحُ بالنوع في **الموضعين** يوحّده،
                # والإسنادُ إلى العمود يُكيَّف بعده. مقيسٌ على PostgreSQL 16.13:
                # `$1::text` في موضعٍ واحد لا يكفي — يبقى التضاربُ قائماً.
                "UPDATE approval_workflows SET status=$1::text, approvals=$2, "
                "resolved_at=CASE WHEN $1::text='approved' THEN NOW() ELSE NULL END "
                "WHERE workflow_id=$3",
                status,
                json.dumps(approvals),
                workflow_id,
            )
            return {
                "status": status,
                "workflow_id": workflow_id,
                "approvals_count": len(approvals),
                "approvals_received": len(approvals),
                "approvals_required": required_count,
            }

    async def reject(
        self,
        workflow_id: str,
        expert_id: str,
        expert_role: str,
        reason: str,
        tenant_id: str,
        suggested_alternative: dict | None = None,
    ) -> dict:
        if not tenant_id:
            return {"error": "Workflow not found", "status": "not_found"}
        tenant_id = str(uuid.UUID(tenant_id))
        async with _tenant_connection(tenant_id) as conn:
            row = await _locked_workflow(conn, workflow_id, tenant_id)
            error = await _pending_error(conn, row)
            if error:
                return error
            error = _role_error(row, expert_role)
            if error:
                return error
            rejections = _json_list(row["rejections"])
            rejections.append(
                {
                    "expert_id": expert_id,
                    "expert_role": expert_role,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "reason": reason,
                    "suggested_alternative": suggested_alternative,
                }
            )
            await conn.execute(
                "UPDATE approval_workflows SET status=$1, rejections=$2, resolved_at=NOW() WHERE workflow_id=$3",
                "rejected",
                json.dumps(rejections),
                workflow_id,
            )
        return {
            "status": "rejected",
            "workflow_id": workflow_id,
            "reason": reason,
            "suggested_alternative": suggested_alternative,
        }

    async def escalate(self, workflow_id: str, reason: str, tenant_id: str) -> dict:
        """Explicitly scoped escalation cannot resurrect an expired or decided workflow."""
        tenant_id = str(uuid.UUID(tenant_id))
        async with _tenant_connection(tenant_id) as conn:
            row = await _locked_workflow(conn, workflow_id, tenant_id)
            error = await _pending_error(conn, row)
            if error:
                return error
            new_count = (row["escalation_count"] or 0) + 1
            if new_count > 2:
                await conn.execute(
                    "UPDATE approval_workflows SET status='auto_rejected', resolved_at=NOW() WHERE workflow_id=$1",
                    workflow_id,
                )
                return {"status": "auto_rejected", "workflow_id": workflow_id}
            roles = sorted(set(row["required_roles"] or []) | {"admin", "regional_manager"})
            await conn.execute(
                "UPDATE approval_workflows SET escalation_count=$1, required_roles=$2 WHERE workflow_id=$3",
                new_count,
                roles,
                workflow_id,
            )
        return {
            "status": "escalated",
            "workflow_id": workflow_id,
            "escalation_level": new_count,
            "notification_delivery": "not_configured",
        }

    async def get_status(self, workflow_id: str, tenant_id: str) -> dict | None:
        tenant_id = str(uuid.UUID(tenant_id))
        async with _tenant_connection(tenant_id) as conn:
            row = await _locked_workflow(conn, workflow_id, tenant_id)
            if not row:
                return None
            error = await _pending_error(conn, row)
            status = error["status"] if error else row["status"]
            return {
                "workflow_id": row["workflow_id"],
                "tenant_id": str(row["tenant_id"]),
                "status": status,
                "risk_level": row["risk_level"],
                "action_type": row["action_type"],
                "required_roles": list(row["required_roles"] or []),
                "approvals": _json_list(row["approvals"]),
                "rejections": _json_list(row["rejections"]),
                "escalation_count": row["escalation_count"] or 0,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
                "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
                "notification_delivery": "not_configured",
            }
