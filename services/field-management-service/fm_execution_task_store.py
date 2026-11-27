"""PostgreSQL owner store for the opt-in field-inspection execution adapter.

No SQL touches decision-owned tables. Existing pin/user/photo read helpers keep
their owner contracts; new writes are field_tasks and the three v291 owner tables.
The connection factory must yield one tenant/user scoped transaction per call.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from fm_execution_tasks import (
    OPERATION,
    PROVIDER,
    SCHEMA,
    ExecutionBinding,
    canonical,
    digest,
    iso,
    refuse,
)
from fm_gateway import Caller, caller_connection
from fm_task_inspection import (
    INSPECTOR_ROLES,
    _eligible,
    _load,
    _require_field,
    _require_pin,
    evidence_digest,
    same_photo,
)

_ROLE_ALIASES = {
    "owner": ("owner", "admin"),
    "manager": ("manager",),
    "agronomist": ("agronomist", "expert"),
    "worker": ("worker", "farmer"),
    "viewer": ("viewer",),
}
_LINK_SELECT = (
    "SELECT l.*, t.assigned_to AS current_assigned_to, assignee.full_name AS assignee_name, "
    "r.outcome_id "
    "FROM field_task_execution_links l "
    "JOIN field_tasks t ON t.tenant_id=l.tenant_id AND t.field_id=l.field_id AND t.task_id=l.task_id "
    "LEFT JOIN field_task_execution_outcome_receipts r "
    "ON r.tenant_id=l.tenant_id AND r.execution_request_id=l.execution_request_id "
    "LEFT JOIN users assignee ON assignee.tenant_id=l.tenant_id "
    "AND assignee.id::text=t.assigned_to AND assignee.active "
)


def row_dict(row: Any) -> dict:
    data = dict(row)
    for key, value in list(data.items()):
        if isinstance(value, UUID):
            data[key] = str(value)
        elif isinstance(value, datetime):
            data[key] = iso(value)
        elif key in {"receipt_payload", "actual", "metrics", "upstream_result"} and isinstance(
            value, str
        ):
            data[key] = json.loads(value)
        elif key.endswith("digest") or key.endswith("sha256"):
            data[key] = str(value).strip() if value is not None else None
    return data


def inspection_proof(link: dict, task: dict, events: list[dict]) -> dict:
    """Build a point-in-time proof; administrative completion is never sufficient."""
    if (
        task.get("status") != "completed"
        or task.get("task_type") != "scouting"
        or task.get("anomaly_ref") is not None
        or not task.get("completed_at")
        or str(task.get("pin_id") or "") != link["pin_id"]
        or str(task.get("task_id") or "") != str(link["task_id"])
        or task.get("field_id") != link["field_id"]
        or str(task.get("tenant_id") or "") != str(link["tenant_id"])
        or not events
    ):
        raise refuse("inspection_not_completed", 409)
    last = events[-1]
    submitted = next((e for e in reversed(events) if e.get("action") == "submit"), None)
    reopened = max((int(e["revision"]) for e in events if e.get("action") == "reopen"), default=0)
    versions = task.get("evidence") or []
    newest = max(versions, key=lambda v: int(v["version"]), default=None)
    if (
        last.get("action") != "approve"
        or submitted is None
        or newest is None
        or last.get("evidence_version") != newest["version"]
        or submitted.get("evidence_version") != newest["version"]
        or not reopened < int(submitted["revision"]) < int(last["revision"])
        or str(last.get("assignee")) != str(task.get("assigned_to"))
        or str(submitted.get("assignee")) != str(task.get("assigned_to"))
        or str(submitted.get("actor")) != str(task.get("assigned_to"))
        or str(newest.get("recorded_by")) != str(submitted.get("actor"))
        or str(last.get("actor")) == str(submitted.get("actor"))
        or str(last.get("actor")) == str(newest.get("recorded_by"))
        or not same_photo(newest, task.get("photo"))
    ):
        raise refuse("current_independent_inspection_approval_required", 409)
    if (
        evidence_digest(
            newest.get("photo_evidence_id"), newest.get("photo_content_sha256"), newest.get("notes")
        )
        != str(newest.get("digest", "")).strip()
    ):
        raise refuse("inspection_evidence_digest_mismatch", 409)
    actual = {
        "provider": PROVIDER,
        "operation_type": OPERATION,
        "tenant_id": str(link["tenant_id"]),
        "field_id": link["field_id"],
        "pin_id": link["pin_id"],
        "provider_task_id": str(link["task_id"]),
        "execution_request_id": link["execution_request_id"],
        "decision_id": link["decision_id"],
        "execution_plan_id": link["execution_plan_id"],
        "dispatch_authorization_id": link["dispatch_authorization_id"],
        "receipt_id": link["receipt_id"],
        "correlation_id": str(link["correlation_id"]),
        "task_status": "completed",
        "completed_at": iso(task["completed_at"]),
        "handoff_revision": int(last["revision"]),
        "evidence_version": int(newest["version"]),
        "evidence_digest": str(newest["digest"]).strip(),
        "photo_evidence_id": str(newest["photo_evidence_id"])
        if newest.get("photo_evidence_id")
        else None,
        "photo_content_sha256": (
            str(newest["photo_content_sha256"]).strip()
            if newest.get("photo_content_sha256")
            else None
        ),
        "inspector_id": str(submitted["actor"]),
        "reviewer_id": str(last["actor"]),
        "finding_notes": newest.get("notes"),
    }
    metrics = {"inspection_approved": True}
    fingerprint = digest({"actual": actual, "metrics": metrics})
    identity = {
        key: actual[key]
        for key in (
            "tenant_id",
            "field_id",
            "pin_id",
            "execution_request_id",
            "decision_id",
            "execution_plan_id",
            "dispatch_authorization_id",
            "receipt_id",
            "correlation_id",
            "handoff_revision",
            "evidence_version",
            "evidence_digest",
            "photo_evidence_id",
            "photo_content_sha256",
            "inspector_id",
            "reviewer_id",
        )
    }
    return {
        **identity,
        "schema": SCHEMA,
        "authoritative": True,
        "persisted": True,
        "current": True,
        "observed_at": datetime.now(UTC).isoformat(),
        "completed": True,
        "task_id": str(link["task_id"]),
        "task_ref": "urn:sahool:task:" + str(link["task_id"]),
        "completed_at": actual["completed_at"],
        "confirmation_id": "fic_" + fingerprint[:32],
        "verified_by": actual["reviewer_id"],
        "verification_state": "verified_success",
        "evidence_snapshot_id": "inspection_" + fingerprint,
        "idempotency_key": "inspect-outcome-" + fingerprint,
        "actual": actual,
        "metrics": metrics,
    }


class PostgresExecutionStore:
    def __init__(self, connection_factory: Callable = caller_connection):
        self.connection_factory = connection_factory

    @asynccontextmanager
    async def _connection(self, caller: Caller):
        try:
            async with self.connection_factory(caller) as conn:
                yield conn
        except HTTPException:
            raise
        except Exception as exc:
            if getattr(exc, "sqlstate", None) in {
                "23505",
                "23514",
                "23503",
                "SH001",
                "SH002",
                "SH003",
                "SH004",
                "SH006",
                "SH007",
                "SH008",
            }:
                raise refuse("inspection_execution_store_conflict", 409) from None
            raise refuse("inspection_execution_store_unavailable", 503) from None

    async def _current_user(self, conn, caller: Caller) -> None:
        roles = _ROLE_ALIASES.get(caller.role, ())
        if not roles or not await _eligible(conn, caller, caller.user_id, roles):
            raise refuse("current_account_permission_required", 403)

    async def require_field(self, caller: Caller, field_id: str) -> None:
        async with self._connection(caller) as conn:
            await self._current_user(conn, caller)
            await _require_field(conn, caller, field_id)

    async def get_link(self, caller: Caller, request_id: str) -> dict | None:
        async with self._connection(caller) as conn:
            await self._current_user(conn, caller)
            row = await conn.fetchrow(
                _LINK_SELECT + "WHERE l.tenant_id=$1::uuid AND l.execution_request_id=$2",
                caller.tenant_id,
                request_id,
            )
            return row_dict(row) if row else None

    async def list_links(self, caller: Caller, field_id: str, limit: int = 50) -> list[dict]:
        async with self._connection(caller) as conn:
            await self._current_user(conn, caller)
            rows = await conn.fetch(
                _LINK_SELECT + "WHERE l.tenant_id=$1::uuid AND l.field_id=$2 "
                "ORDER BY l.created_at DESC, l.execution_request_id LIMIT $3",
                caller.tenant_id,
                field_id,
                max(1, min(100, int(limit))),
            )
            return [row_dict(row) for row in rows]

    async def _validate(self, conn, caller: Caller, binding: ExecutionBinding) -> None:
        if (
            binding.tenant_id != caller.tenant_id
            or binding.operation_type != OPERATION
            or binding.received_by != caller.user_id
        ):
            raise refuse("inspection_scope_mismatch", 404)
        await self._current_user(conn, caller)
        await _require_pin(conn, caller, binding.field_id, binding.pin_id)
        if not await _eligible(conn, caller, binding.assigned_to, INSPECTOR_ROLES):
            raise refuse("inspection_assignee_unavailable", 422)
        existing = await conn.fetchrow(
            "SELECT task_id FROM field_tasks WHERE tenant_id=$1::uuid "
            "AND source_scouting_pin_id=$2",
            caller.tenant_id,
            binding.pin_id,
        )
        if existing:
            linked = await conn.fetchrow(
                "SELECT task_id, request_digest FROM field_task_execution_links "
                "WHERE tenant_id=$1::uuid AND execution_request_id=$2",
                caller.tenant_id,
                binding.execution_request_id,
            )
            if (
                linked is None
                or str(linked["task_id"]) != str(existing["task_id"])
                or str(linked["task_id"]) != binding.task_id
                or str(linked["request_digest"]).strip() != binding.request_digest
            ):
                # A manually created pin task is never silently adopted by a decision request.
                raise refuse("inspection_pin_already_has_another_task", 409)

    async def validate(self, caller: Caller, binding: ExecutionBinding) -> str | None:
        async with self._connection(caller) as conn:
            await self._validate(conn, caller, binding)
            # Same existing user-read boundary as inspection-assignees. The name
            # is display metadata only; the immutable binding keeps the user id.
            return await conn.fetchval(
                "SELECT full_name FROM users WHERE tenant_id=$1::uuid "
                "AND id::text=$2 AND active AND role=ANY($3::text[])",
                caller.tenant_id,
                binding.assigned_to,
                list(INSPECTOR_ROLES),
            )

    async def ensure_task(self, caller: Caller, binding: ExecutionBinding) -> dict:
        async with self._connection(caller) as conn:
            # Same pin lock as assign_pin_inspection: serializes manual and adapter creates.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"inspection:{caller.tenant_id}:{binding.pin_id}",
            )
            await self._validate(conn, caller, binding)
            prior = await conn.fetchrow(
                "SELECT * FROM field_task_execution_links "
                "WHERE tenant_id=$1::uuid AND execution_request_id=$2",
                caller.tenant_id,
                binding.execution_request_id,
            )
            if prior:
                saved = row_dict(prior)
                if (
                    saved["request_digest"] != binding.request_digest
                    or saved["task_id"] != binding.task_id
                    or saved["adapter_id"] != binding.adapter_id
                    or saved["receipt_id"] != binding.receipt_id
                ):
                    raise refuse("execution_request_binding_conflict", 409)
                return saved
            await conn.execute(
                """INSERT INTO field_tasks
                   (task_id,tenant_id,field_id,task_type,status,source_scouting_pin_id,assigned_to,
                    recommended_date,inspection_due_at,inspection_assigned_by,
                    inspection_initial_assignee,priority)
                   VALUES($1::uuid,$2::uuid,$3,'scouting','pending',$4,$5::text,$6,$7,$8,$5::text,$9)""",
                UUID(binding.task_id),
                caller.tenant_id,
                binding.field_id,
                binding.pin_id,
                binding.assigned_to,
                datetime.fromisoformat(binding.due_at).date(),
                datetime.fromisoformat(binding.due_at),
                caller.user_id,
                binding.priority,
            )
            row = await conn.fetchrow(
                """INSERT INTO field_task_execution_links
                   (tenant_id,execution_request_id,task_id,field_id,pin_id,operation_type,
                    decision_id,execution_plan_id,dispatch_authorization_id,correlation_id,
                    assigned_to,due_at,priority,request_digest,adapter_id,receipt_id,
                    receipt_payload,received_by)
                   VALUES($1::uuid,$2,$3::uuid,$4,$5,$6,$7,$8,$9,$10::uuid,$11,$12,$13,$14,
                          $15,$16,$17::jsonb,$18) RETURNING *""",
                caller.tenant_id,
                binding.execution_request_id,
                UUID(binding.task_id),
                binding.field_id,
                binding.pin_id,
                OPERATION,
                binding.decision_id,
                binding.execution_plan_id,
                binding.dispatch_authorization_id,
                UUID(binding.correlation_id),
                binding.assigned_to,
                datetime.fromisoformat(binding.due_at),
                binding.priority,
                binding.request_digest,
                binding.adapter_id,
                binding.receipt_id,
                canonical(binding.receipt_payload()),
                caller.user_id,
            )
            return row_dict(row)

    async def readback(self, caller: Caller, binding: ExecutionBinding) -> dict:
        """A separate transaction proves the task AND link are committed before receipt."""
        async with self._connection(caller) as conn:
            await self._current_user(conn, caller)
            row = await conn.fetchrow(
                """SELECT l.*, t.source_scouting_pin_id AS task_pin,
                          t.inspection_initial_assignee AS initial_assignee,
                          t.inspection_assigned_by AS task_creator, t.inspection_due_at AS task_due,
                          t.task_type, t.priority AS task_priority
                     FROM field_task_execution_links l
                     JOIN field_tasks t ON t.tenant_id=l.tenant_id AND t.field_id=l.field_id
                                       AND t.task_id=l.task_id
                    WHERE l.tenant_id=$1::uuid AND l.execution_request_id=$2""",
                caller.tenant_id,
                binding.execution_request_id,
            )
            if not row:
                raise refuse("committed_inspection_task_missing", 503)
            saved = row_dict(row)
            if (
                saved["task_id"] != binding.task_id
                or saved["field_id"] != binding.field_id
                or saved["task_pin"] != binding.pin_id
                or saved["task_type"] != "scouting"
                or saved["initial_assignee"] != binding.assigned_to
                or saved["task_creator"] != saved["received_by"]
                or iso(saved["task_due"]) != binding.due_at
                or saved["task_priority"] != binding.priority
                or saved["request_digest"] != binding.request_digest
                or saved["receipt_payload"] != binding.receipt_payload()
            ):
                raise refuse("committed_inspection_task_mismatch", 409)
            return saved

    async def _proof(self, conn, caller: Caller, link: dict, *, write: bool) -> dict:
        task_id = UUID(str(link["task_id"]))
        task, events = await _load(conn, caller, link["field_id"], task_id, write=write)
        state = await conn.fetchrow(
            "SELECT completed_at, task_type, anomaly_ref FROM field_tasks WHERE tenant_id=$1::uuid "
            "AND field_id=$2 AND task_id=$3",
            caller.tenant_id,
            link["field_id"],
            task_id,
        )
        task.update(
            tenant_id=caller.tenant_id,
            field_id=link["field_id"],
            task_id=str(task_id),
            **dict(state),
        )
        proof = inspection_proof(link, task, events)
        # A revoked/inactive reviewer cannot attest a new current owner proof.
        if not await _eligible(conn, caller, proof["reviewer_id"], ("owner", "admin", "manager")):
            raise refuse("inspection_reviewer_unavailable", 403)
        return proof

    async def preview_confirmation(self, caller: Caller, link: dict) -> dict:
        async with self._connection(caller) as conn:
            await self._current_user(conn, caller)
            proof = await self._proof(conn, caller, link, write=False)
            if proof["reviewer_id"] != caller.user_id:
                raise refuse("only_current_approver_may_verify", 403)
            return proof

    async def prepare_confirmation(self, caller: Caller, task_id: str, field_id: str) -> dict:
        try:
            uuid = UUID(task_id)
        except (ValueError, TypeError):
            raise refuse("invalid_task_id", 422) from None
        async with self._connection(caller) as conn:
            await self._current_user(conn, caller)
            row = await conn.fetchrow(
                "SELECT * FROM field_task_execution_links WHERE tenant_id=$1::uuid "
                "AND field_id=$2 AND task_id=$3",
                caller.tenant_id,
                field_id,
                uuid,
            )
            if not row:
                raise refuse("inspection_execution_link_not_found", 404)
            link = row_dict(row)
            # _load FOR UPDATE takes the same task lock as handoff/close/reopen.
            proof = await self._proof(conn, caller, link, write=True)
            if proof["reviewer_id"] != caller.user_id:
                raise refuse("only_current_approver_may_verify", 403)
            prior = await conn.fetchrow(
                "SELECT * FROM field_task_execution_confirmations WHERE tenant_id=$1::uuid "
                "AND confirmation_id=$2",
                caller.tenant_id,
                proof["confirmation_id"],
            )
            if prior:
                existing = row_dict(prior)
                if existing["actual"] != proof["actual"] or existing["metrics"] != proof["metrics"]:
                    raise refuse("inspection_confirmation_conflict", 409)
                return proof
            if await conn.fetchval(
                "SELECT true FROM field_task_execution_outcome_receipts "
                "WHERE tenant_id=$1::uuid AND execution_request_id=$2",
                caller.tenant_id,
                link["execution_request_id"],
            ):
                raise refuse("inspection_outcome_already_recorded", 409)
            await conn.execute(
                """INSERT INTO field_task_execution_confirmations
                   (confirmation_id,tenant_id,execution_request_id,task_id,field_id,pin_id,
                    handoff_revision,evidence_version,evidence_digest,photo_evidence_id,
                    photo_content_sha256,inspector_id,reviewer_id,verified_by,
                    evidence_snapshot_id,idempotency_key,actual,metrics)
                   VALUES($1,$2::uuid,$3,$4::uuid,$5,$6,$7,$8,$9,$10::uuid,$11,$12,$13,$14,
                          $15,$16,$17::jsonb,$18::jsonb)""",
                proof["confirmation_id"],
                caller.tenant_id,
                proof["execution_request_id"],
                uuid,
                field_id,
                proof["pin_id"],
                proof["handoff_revision"],
                proof["evidence_version"],
                proof["evidence_digest"],
                UUID(proof["photo_evidence_id"]) if proof["photo_evidence_id"] else None,
                proof["photo_content_sha256"],
                proof["inspector_id"],
                proof["reviewer_id"],
                caller.user_id,
                proof["evidence_snapshot_id"],
                proof["idempotency_key"],
                canonical(proof["actual"]),
                canonical(proof["metrics"]),
            )
        # The owner transaction is over before any remote decision call.
        return proof

    async def read_execution_proof(self, tenant_id: str, execution_request_id: str) -> dict:
        """S2S read, called only after the router authenticates FIELD_INSPECTION_PROOF_TOKEN.

        Requires an existing confirmation and rechecks current task/photo/approval.
        observed_at reports the read time; this is not a distributed lock or perpetual attestation.
        """
        try:
            tenant = str(UUID(tenant_id))
        except (ValueError, TypeError):
            raise refuse("invalid_tenant_id", 400) from None
        caller = Caller(tenant, "field-inspection-proof-reader", "")
        async with self._connection(caller) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM field_task_execution_links WHERE tenant_id=$1::uuid "
                "AND execution_request_id=$2",
                tenant,
                execution_request_id,
            )
            if not row:
                raise refuse("inspection_execution_link_not_found", 404)
            proof = await self._proof(conn, caller, row_dict(row), write=False)
            recorded = await conn.fetchrow(
                "SELECT * FROM field_task_execution_confirmations WHERE tenant_id=$1::uuid "
                "AND execution_request_id=$2 AND confirmation_id=$3",
                tenant,
                execution_request_id,
                proof["confirmation_id"],
            )
            if not recorded:
                raise refuse("current_inspection_confirmation_required", 409)
            saved = row_dict(recorded)
            for key in (
                "evidence_snapshot_id",
                "idempotency_key",
                "actual",
                "metrics",
                "verified_by",
                "handoff_revision",
                "evidence_version",
                "evidence_digest",
                "photo_evidence_id",
                "photo_content_sha256",
                "reviewer_id",
                "inspector_id",
            ):
                if saved[key] != proof[key]:
                    raise refuse("current_inspection_confirmation_mismatch", 409)
            return proof

    async def save_outcome(self, caller: Caller, proof: dict, result: dict) -> dict:
        async with self._connection(caller) as conn:
            await self._current_user(conn, caller)
            # Receipt is a historical acknowledgement of the upstream commit, not a fresh
            # attestation of mutable photo state; DS already did that read before its commit.
            prior = await conn.fetchrow(
                "SELECT * FROM field_task_execution_outcome_receipts "
                "WHERE tenant_id=$1::uuid AND execution_request_id=$2",
                caller.tenant_id,
                proof["execution_request_id"],
            )
            if prior:
                stored = row_dict(prior)
                if (
                    stored["confirmation_id"] != proof["confirmation_id"]
                    or stored["outcome_id"] != result["outcome_id"]
                ):
                    raise refuse("inspection_outcome_receipt_conflict", 409)
                return stored
            row = await conn.fetchrow(
                """INSERT INTO field_task_execution_outcome_receipts
                   (tenant_id,confirmation_id,execution_request_id,task_id,field_id,
                    outcome_id,upstream_result)
                   VALUES($1::uuid,$2,$3,$4::uuid,$5,$6,$7::jsonb)
                   ON CONFLICT DO NOTHING RETURNING *""",
                caller.tenant_id,
                proof["confirmation_id"],
                proof["execution_request_id"],
                UUID(proof["task_id"]),
                proof["field_id"],
                result["outcome_id"],
                canonical(result),
            )
            if row is None:
                prior = await conn.fetchrow(
                    "SELECT * FROM field_task_execution_outcome_receipts "
                    "WHERE tenant_id=$1::uuid AND execution_request_id=$2",
                    caller.tenant_id,
                    proof["execution_request_id"],
                )
                if (
                    prior is None
                    or prior["confirmation_id"] != proof["confirmation_id"]
                    or prior["outcome_id"] != result["outcome_id"]
                ):
                    raise refuse("inspection_outcome_receipt_conflict", 409)
                row = prior
            return row_dict(row)

    record_outcome_receipt = save_outcome
