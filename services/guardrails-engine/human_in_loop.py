#!/usr/bin/env python3
"""
Human-in-the-Loop Approval Workflow for SAHOOL Guardrails (FIXED)
FIX: Persist to PostgreSQL instead of in-memory dict
"""

import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None and DATABASE_URL:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    return _pool


class HumanApprovalWorkflow:
    def __init__(self):
        self._expert_roles = {
            "chemical": ["agronomist", "pesticide_expert"],
            "environmental": ["agronomist", "water_specialist"],
            "economic": ["financial_advisor", "cooperative_manager"],
            "general": ["agronomist", "admin"],
        }

    async def create(self, request: Any, checks: list[dict], risk_level: str) -> str:
        workflow_id = f"SAHOOL-HIL-{uuid.uuid4().hex[:8].upper()}"
        required_experts = set()
        for check in checks:
            if not check.get("passed", True):
                tier = check.get("tier", "general")
                required_experts.update(self._expert_roles.get(tier, ["agronomist"]))
        pool = await _get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO approval_workflows (workflow_id, tenant_id, user_id, status, risk_level, action_type, action_data, farm_context, required_roles, approvals, rejections, escalation_count, expires_at, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
                """,
                    workflow_id,
                    request.tenant_id,
                    request.user_id,
                    "pending",
                    risk_level,
                    request.action_type,
                    json.dumps(request.action_data),
                    json.dumps(request.farm_context),
                    list(required_experts),
                    "[]",
                    "[]",
                    0,
                    datetime.now(UTC) + timedelta(hours=48),
                )
        await self._notify_experts(workflow_id, list(required_experts), risk_level)
        return workflow_id

    async def approve(
        self,
        workflow_id: str,
        expert_id: str,
        expert_role: str,
        notes: str = "",
        modifications: dict | None = None,
    ) -> dict:
        pool = await _get_pool()
        if not pool:
            return {"error": "Database not available", "status": "error"}
        async with pool.acquire() as conn:
            # Hardening (مراجعة 7): قفل صفّي داخل معاملة لمنع تسابق موافقتين
            # متزامنتين. SELECT FOR UPDATE يحجز الصفّ حتّى تُنهى المعاملة، فلا
            # تقرأ موافقتان "pending" معاً وتمرّان (double-approval).
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT * FROM approval_workflows WHERE workflow_id=$1 FOR UPDATE", workflow_id
                )
                if not row:
                    return {"error": "Workflow not found", "status": "not_found"}
                if row["status"] != "pending":
                    return {"error": f"Workflow already {row['status']}", "status": row["status"]}
                required = row["required_roles"] or []
                if expert_role not in required:
                    return {
                        "error": f"Expert role '{expert_role}' not authorized",
                        "authorized_roles": required,
                        "status": "unauthorized",
                    }
                approvals = (
                    json.loads(row["approvals"])
                    if isinstance(row["approvals"], str)
                    else (row["approvals"] or [])
                )
                # منع موافقة الخبير نفسه مرّتين (idempotency على مستوى الخبير)
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
                        "modifications": modifications,
                    }
                )
                required_count = {"MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}.get(row["risk_level"], 1)
                if len(approvals) >= required_count:
                    await conn.execute(
                        "UPDATE approval_workflows SET status=$1, approvals=$2, resolved_at=NOW() WHERE workflow_id=$3",
                        "approved",
                        json.dumps(approvals),
                        workflow_id,
                    )
                    return {
                        "status": "approved",
                        "workflow_id": workflow_id,
                        "approvals_count": len(approvals),
                        "modifications": modifications,
                        "message_ar": f"✅ تمت الموافقة على الإجراء بواسطة {len(approvals)} خبير(ين).",
                    }
                else:
                    await conn.execute(
                        "UPDATE approval_workflows SET approvals=$1 WHERE workflow_id=$2",
                        json.dumps(approvals),
                        workflow_id,
                    )
                    return {
                        "status": "pending",
                        "workflow_id": workflow_id,
                        "approvals_received": len(approvals),
                        "approvals_required": required_count,
                        "message_ar": f"⏳ تم تسجيل موافقة خبير. في انتظار {required_count - len(approvals)} خبير(ين) إضافي(ين).",
                    }

    async def reject(
        self,
        workflow_id: str,
        expert_id: str,
        expert_role: str,
        reason: str,
        suggested_alternative: dict | None = None,
    ) -> dict:
        pool = await _get_pool()
        if not pool:
            return {"error": "Database not available", "status": "error"}
        async with pool.acquire() as conn:
            # Hardening (مراجعة 7): قفل صفّي + فحص الحالة (لا رفض ما حُسم)
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT * FROM approval_workflows WHERE workflow_id=$1 FOR UPDATE", workflow_id
                )
                if not row:
                    return {"error": "Workflow not found", "status": "not_found"}
                if row["status"] != "pending":
                    return {"error": f"Workflow already {row['status']}", "status": row["status"]}
                rejections = (
                    json.loads(row["rejections"])
                    if isinstance(row["rejections"], str)
                    else (row["rejections"] or [])
                )
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
            "message_ar": f"❌ تم رفض الإجراء بواسطة خبير. السبب: {reason}",
        }

    async def escalate(self, workflow_id: str, reason: str) -> dict:
        pool = await _get_pool()
        if not pool:
            return {"error": "Database not available", "status": "error"}
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM approval_workflows WHERE workflow_id=$1", workflow_id
            )
            if not row:
                return {"error": "Workflow not found"}
            if row["escalation_count"] >= 2:
                await conn.execute(
                    "UPDATE approval_workflows SET status=$1 WHERE workflow_id=$2",
                    "auto_rejected",
                    workflow_id,
                )
                return {
                    "status": "auto_rejected",
                    "workflow_id": workflow_id,
                    "reason": "لم يتم الرد خلال المدة المحددة — تم الرفض التلقائي لسلامة المزرعة.",
                    "message_ar": "⏰ لم يتم الرد خلال المدة المحددة — تم الرفض التلقائي لسلامة المزرعة.",
                }
            new_count = (row["escalation_count"] or 0) + 1
            current_roles = set(row["required_roles"] or [])
            current_roles.add("admin")
            current_roles.add("regional_manager")
            await conn.execute(
                "UPDATE approval_workflows SET escalation_count=$1, required_roles=$2, expires_at=$3 WHERE workflow_id=$4",
                new_count,
                list(current_roles),
                datetime.now(UTC) + timedelta(hours=24),
                workflow_id,
            )
        await self._notify_experts(
            workflow_id, list(current_roles), row["risk_level"], escalation=True
        )
        return {
            "status": "escalated",
            "workflow_id": workflow_id,
            "escalation_level": new_count,
            "message_ar": f"⚠️ تم التصعيد للمستوى {new_count} — إشعار للإدارة العليا.",
        }

    async def _notify_experts(
        self, workflow_id: str, roles: list[str], risk_level: str, escalation: bool = False
    ):
        logger.info(f"[HIL] Notifying experts for workflow {workflow_id}")
        logger.info(f"[HIL] Required roles: {roles}")
        logger.info(f"[HIL] Risk level: {risk_level}")
        logger.info(f"[HIL] Escalation: {escalation}")

    def get_status(self, workflow_id: str) -> dict | None:
        # In production: query DB; here placeholder
        return None
