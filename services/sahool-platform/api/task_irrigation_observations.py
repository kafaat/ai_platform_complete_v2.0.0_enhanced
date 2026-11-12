"""Append field evidence to an existing irrigation operation, never to the ledger.

Observation identity is durable across offline delivery. The existing append-only
event table supplies the uniqueness boundary; no lifecycle transition is performed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from core.authorization import Permission, has_permission
from fastapi import HTTPException

from api.irrigation_observations import IrrigationObservationInput

EVENT_TYPE = "task.irrigation_observation.v1"
#: Closed executions accept no new field evidence: a cancelled run never happened and a
#: reconciled run is already settled in the as-applied ledger. Honest replays of an
#: observation recorded before the close still return the stored payload.
CLOSED_EXECUTION_STATES = frozenset({"cancelled", "reconciled"})


def _payload(row):
    value = row["payload"]
    return json.loads(value) if isinstance(value, str) else dict(value)


async def _task(conn, user, task_id: str):
    # Explicit tenant predicates supplement RLS, including owner-role deployments.
    row = await conn.fetchrow(
        "SELECT task_id, field_id, source_scouting_pin_id, assigned_to, status FROM field_tasks "
        "WHERE task_id::text=$1 AND tenant_id=$2::uuid FOR SHARE",
        task_id,
        str(user.tenant_id),
    )
    if row is None:
        raise HTTPException(404, "المهمة غير موجودة")
    return row


async def record_observation(conn, user, task_id: str, req: IrrigationObservationInput):
    task = await _task(conn, user, task_id)
    execution = await conn.fetchrow(
        "SELECT execution_id, field_id, state FROM irrigation_manual_executions "
        "WHERE execution_id=$1::uuid AND tenant_id=$2::uuid FOR UPDATE",
        str(req.execution_id),
        str(user.tenant_id),
    )
    if execution is None:
        raise HTTPException(404, "عملية الري غير موجودة")
    if execution["field_id"] != task["field_id"]:
        raise HTTPException(422, "عملية الري والمهمة يجب أن تنتميا للحقل نفسه")

    identity = {
        **req.model_dump(mode="json"),
        "event_type": EVENT_TYPE,
        "task_id": str(task["task_id"]),
        "tenant_id": str(user.tenant_id),
        "actor_id": str(user.user_id),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if task.get("source_scouting_pin_id") and not has_permission(user, Permission.FIELD_EDIT):
        previous = await _replayed(conn, user, req, digest)
        if previous is not None:
            return previous
        if task["assigned_to"] != str(user.user_id):
            raise HTTPException(403, "إفادة التفتيش متاحة للمفتش المعيّن أو المشرف")
        active = await conn.fetchval(
            """SELECT true FROM users WHERE tenant_id=$1::uuid AND id::text=$2 AND active
               AND role IN ('worker','farmer','agronomist','expert','manager','owner','admin')""",
            user.tenant_id,
            str(user.user_id),
        )
        if not active:
            raise HTTPException(403, "المفتش غير متاح")
        action = await conn.fetchval(
            """SELECT action FROM inspection_handoffs WHERE tenant_id=$1::uuid AND task_id=$2
               ORDER BY revision DESC LIMIT 1""",
            user.tenant_id,
            task["task_id"],
        )
        if task["status"] not in ("pending", "in_progress") or action not in ("accept", "return"):
            raise HTTPException(409, "يلزم تكليف مقبول ومفتوح لتسجيل إفادة التفتيش")
    if execution["state"] in CLOSED_EXECUTION_STATES:
        previous = await _replayed(conn, user, req, digest)
        if previous is not None:
            return previous
        raise HTTPException(409, f"عملية الري مغلقة ({execution['state']})؛ لا تُقبل ملاحظات جديدة")
    payload = {
        **identity,
        "request_digest": digest,
        "field_id": task["field_id"],
        "computed": req.computed_quantity(),
        "received_at": datetime.now(UTC).isoformat(),
    }
    inserted = await conn.fetchrow(
        """INSERT INTO irrigation_manual_execution_events
        (event_id,tenant_id,execution_id,from_state,to_state,actor_id,payload,event_digest)
        VALUES ($1::uuid,$2::uuid,$3::uuid,$4,$4,$5,$6::jsonb,$7)
        ON CONFLICT DO NOTHING RETURNING payload""",
        str(req.observation_id),
        str(user.tenant_id),
        str(req.execution_id),
        execution["state"],
        str(user.user_id),
        json.dumps(payload, ensure_ascii=False),
        digest,
    )
    if inserted is not None:
        return _payload(inserted)
    previous = await _replayed(conn, user, req, digest)
    if previous is not None:
        return previous
    raise HTTPException(409, "معرّف الملاحظة مستخدم؛ أعد إرسال الملاحظة الأصلية دون تعديل")


async def _replayed(conn, user, req: IrrigationObservationInput, digest: str):
    """The stored payload when this exact observation was already recorded, else None."""
    # A fresh READ COMMITTED statement sees the winning committed insert. Do not
    # compare lifecycle state: an operation may advance before an offline retry.
    prior = await conn.fetchrow(
        "SELECT payload FROM irrigation_manual_execution_events "
        "WHERE event_id=$1::uuid AND tenant_id=$2::uuid",
        str(req.observation_id),
        str(user.tenant_id),
    )
    if prior is not None:
        previous = _payload(prior)
        if (
            previous.get("request_digest") == digest
            and previous.get("actor_id") == str(user.user_id)
            and previous.get("event_type") == EVENT_TYPE
        ):
            return previous
    return None


async def list_observations(conn, user, task_id: str):
    task = await _task(conn, user, task_id)
    rows = await conn.fetch(
        """SELECT payload FROM irrigation_manual_execution_events
        WHERE tenant_id=$1::uuid AND payload->>'event_type'=$2
          AND payload->>'task_id'=$3
        ORDER BY occurred_at DESC, event_id DESC LIMIT 200""",
        str(user.tenant_id),
        EVENT_TYPE,
        str(task["task_id"]),
    )
    return {"observations": [_payload(row) for row in rows]}
