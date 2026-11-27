"""Ground-scouting tasks for vegetation signal anomalies (owner: field-management-service).

Plan item W1-20 (findings remote-7 / scout-5). vegetation-analysis-service's ground-verification
bridge asks for a scouting task when a signal anomaly needs a field check, and only moves the
anomaly to ``verification_requested`` on a reply that says the task is stored and names it. No
service served that request, so every verification failed. This module serves it on the owner of
``field_tasks`` (docs/architecture/db_ownership.yml), with the v282 columns:

* ``POST /internal/field-tasks/scouting`` stores one ``task_type='scouting'`` row per anomaly and
  answers ``{"persisted": true, "task_id", "task_ref"}``. The ``Idempotency-Key`` header is
  required: a replay with the same key and the same request returns the stored task (200,
  ``replayed: true``) and writes nothing; the same key with another request is 409; a second key
  for an anomaly that already has a task is 409 (one task per anomaly per tenant, v282 indexes);
* ``GET /internal/field-tasks/scouting?field_id=...`` lists a field's anomaly tasks, for the
  remote-sensing workspace's ground section.

These are service-to-service routes: the caller is a service, not a person, so they use
main.py's ``_require_tenant`` (shared service token, optional caller allowlist, and the
short-lived tenant assertion bound to method, path and request id). The gateway path
``/api/v1/field-tasks/`` reaches the same prefix, but nginx clears ``X-Agent-Token``
(proxy_params.conf) and injects only ``X-Field-Tasks-Token``, so a browser cannot call them.
The task carries references only (anomaly, geometry, reason codes): never a diagnosis.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import AwareDatetime, BaseModel, Field, field_validator

TASK_REF_PREFIX = "urn:sahool:task:"
SOURCE_EVENT_TYPE = "vegetation.signal_anomaly"

# The anomaly engine's severities (vegetation anomaly_engine._severity), most urgent first. The
# platform orders tasks by priority ASC, so 1 is the most urgent.
SEVERITY_PRIORITY = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}

_ID = r"[A-Za-z0-9_.:-]"
_FIELD_ID_RE = re.compile(rf"^{_ID}{{1,50}}$")  # field_tasks.field_id is VARCHAR(50)
_KEY_RE = re.compile(rf"^{_ID}{{16,128}}$")
# season_id is accepted as vegetation's DetectRequest accepts it (any 1-128 characters, e.g.
# "2026/2027" or Arabic text), minus control characters. It is only ever a bound parameter.
_SEASON = r"[^\x00-\x1f\x7f]"
_SEASON_RE = re.compile(rf"^{_SEASON}{{1,128}}$")

_COLUMNS = (
    "task_id, field_id, season_id, anomaly_ref, task_type, status, priority, assigned_to, "
    "recommended_date, verification_deadline, geometry_ref, reason_codes, requested_by_service, "
    "created_at, completed_at"
)


class ScoutingTaskRequest(BaseModel):
    """The bridge's body (ground_verification_bridge.py): references only, no diagnosis."""

    anomaly_ref: str = Field(pattern=rf"^urn:sahool:anomaly:{_ID}{{1,200}}$")
    field_id: str = Field(pattern=rf"^{_ID}{{1,50}}$")
    season_id: str = Field(pattern=rf"^{_SEASON}{{1,128}}$")
    geometry_ref: str | None = Field(default=None, min_length=1, max_length=512)
    priority: Literal["critical", "high", "medium", "low", "info"] = "medium"
    verification_deadline: AwareDatetime | None = None
    reason_codes: list[str] = Field(default_factory=list, max_length=32)

    model_config = {"extra": "forbid"}

    @field_validator("reason_codes")
    @classmethod
    def _codes(cls, value: list[str]) -> list[str]:
        for code in value:
            if not isinstance(code, str) or not 1 <= len(code) <= 128:
                raise ValueError("each reason code is a string of 1 to 128 characters")
        return value


def request_digest(req: ScoutingTaskRequest) -> str:
    """sha256 of the normalized request: what an Idempotency-Key is bound to."""
    data = req.model_dump(mode="json")
    if req.verification_deadline is not None:
        # The same instant written with another offset is the same request.
        data["verification_deadline"] = (
            req.verification_deadline.astimezone(UTC).isoformat().replace("+00:00", "Z")
        )
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def task_ref(task_id: Any) -> str:
    return f"{TASK_REF_PREFIX}{task_id}"


def task_view(row: Any) -> dict[str, Any]:
    """A stored row as the callers read it (pure)."""
    data = dict(row)
    data["task_id"] = str(data["task_id"])
    data["task_ref"] = task_ref(data["task_id"])
    codes = data.get("reason_codes")
    if isinstance(codes, str):
        data["reason_codes"] = json.loads(codes)
    elif codes is None:
        data["reason_codes"] = []
    return data


def tenant_uuid(tenant: str) -> str:
    try:
        return str(UUID(tenant))
    except (TypeError, ValueError):
        raise HTTPException(400, "X-Tenant-Id must be a tenant UUID") from None


class IdempotencyConflict(Exception):
    """The key names another request, or the anomaly already has a task under another key."""

    def __init__(self, code: str, existing: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.existing = existing


class FieldNotFound(Exception):
    pass


# ── store (one transaction, app.current_tenant set; unit tests stub these two functions) ──


async def store_create(
    conn,
    tenant: str,
    req: ScoutingTaskRequest,
    key: str,
    digest: str,
    service: str | None,
) -> tuple[dict[str, Any], bool]:
    """Insert the task, or return the stored one for an exact replay. (task, replayed)."""
    # Serialize retries of one key, including concurrent ones, before reading.
    await conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
        f"scouting-task:{tenant}:{key}",
    )
    row = await conn.fetchrow(
        f"SELECT {_COLUMNS}, scouting_request_digest FROM field_tasks"
        " WHERE tenant_id=$1::uuid AND scouting_idempotency_key=$2",
        tenant,
        key,
    )
    if row is not None:
        stored = dict(row)
        if str(stored.pop("scouting_request_digest") or "").strip() != digest:
            raise IdempotencyConflict("idempotency_key_reused_with_different_request")
        return task_view(stored), True
    other = await conn.fetchrow(
        f"SELECT {_COLUMNS} FROM field_tasks WHERE tenant_id=$1::uuid AND anomaly_ref=$2",
        tenant,
        req.anomaly_ref,
    )
    if other is not None:
        raise IdempotencyConflict("anomaly_already_has_task", task_view(other))
    if not await conn.fetchval(
        "SELECT true FROM fields WHERE tenant_id=$1::uuid AND field_id=$2", tenant, req.field_id
    ):
        raise FieldNotFound(req.field_id)
    deadline = req.verification_deadline
    row = await conn.fetchrow(
        f"""INSERT INTO field_tasks
               (tenant_id, field_id, task_type, priority, status, recommended_date,
                source_event_type, source_agent, anomaly_ref, season_id, geometry_ref,
                verification_deadline, reason_codes, scouting_idempotency_key,
                scouting_request_digest, requested_by_service)
            VALUES ($1::uuid, $2, 'scouting', $3, 'pending', COALESCE($4::date, CURRENT_DATE),
                    $5, $6::text, $7, $8, $9, $10, $11::jsonb, $12, $13, $6::text)
            RETURNING {_COLUMNS}""",
        tenant,
        req.field_id,
        SEVERITY_PRIORITY[req.priority],
        deadline.date() if deadline else None,
        SOURCE_EVENT_TYPE,
        service,
        req.anomaly_ref,
        req.season_id,
        req.geometry_ref,
        deadline,
        json.dumps(req.reason_codes, ensure_ascii=False),
        key,
        digest,
    )
    return task_view(row), False


def parse_page_cursor(cursor: str | None) -> tuple[datetime | None, UUID | None]:
    if cursor is None:
        return None, None
    try:
        timestamp, task_id = cursor.split("|")
        when = datetime.fromisoformat(timestamp) if timestamp else None
        if when is not None:
            if when.tzinfo is None:
                raise ValueError("missing UTC offset")
            when = when.astimezone(UTC)
        return when, UUID(task_id)
    except (ValueError, OverflowError) as exc:
        raise HTTPException(400, "invalid scouting cursor") from exc


async def store_list(
    conn,
    tenant: str,
    field_id: str,
    season_id: str | None,
    anomaly_ref: str | None,
    limit: int = 200,
    after: tuple[datetime | None, UUID | None] = (None, None),
) -> list[dict[str, Any]]:
    select_tasks = f"""SELECT {_COLUMNS} FROM field_tasks
                        WHERE tenant_id=$1::uuid AND field_id=$2 AND anomaly_ref IS NOT NULL
                          AND ($3::text IS NULL OR season_id=$3)
                          AND ($4::text IS NULL OR anomaly_ref=$4)"""
    page_order = "ORDER BY created_at DESC NULLS FIRST, task_id ASC LIMIT $5"
    args = [tenant, field_id, season_id, anomaly_ref, limit]
    created_at, task_id = after
    if task_id is None:
        query = f"{select_tasks} {page_order}"
    else:
        args.append(task_id)
        if created_at is None:
            same_time = "created_at IS NULL"
            later_in_order = "created_at IS NOT NULL"
        else:
            args.append(created_at)
            same_time = "created_at = $7"
            later_in_order = "created_at < $7"
        # These disjoint index ranges seek past the boundary even inside a large tie.
        # Both reads share one statement snapshot and only contribute a page of rows.
        query = f"""({select_tasks} AND {same_time} AND task_id > $6 {page_order})
                    UNION ALL
                    ({select_tasks} AND {later_in_order} {page_order})
                    {page_order}"""
    rows = await conn.fetch(query, *args)
    return [task_view(r) for r in rows]


# ── routes ──────────────────────────────────────────────────────────────────

Connect = Callable[[], Awaitable[Any]]


async def _in_tenant_tx(connect: Connect, tenant: str, work):
    conn = None
    try:
        conn = await connect()
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            return await work(conn)
    finally:
        if conn is not None:
            await conn.close()


def build_router(require_tenant: Callable[..., str], connect: Connect) -> APIRouter:
    """The routes, bound to main.py's service-token + tenant-assertion dependency."""
    # A literal prefix, so the route inventory composes the served path (generate_service_inventory).
    router = APIRouter(prefix="/internal/field-tasks")

    @router.post("/scouting")
    async def create_scouting_task(
        req: ScoutingTaskRequest,
        response: Response,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        x_service_name: str | None = Header(None, alias="X-Service-Name"),
        tenant: str = Depends(require_tenant),
    ):
        key = (idempotency_key or "").strip()
        if not _KEY_RE.fullmatch(key):
            raise HTTPException(400, "Idempotency-Key required (16-128 of [A-Za-z0-9_.:-])")
        tid = tenant_uuid(tenant)
        digest = request_digest(req)
        service = (x_service_name or "").strip() or None
        try:
            task, replayed = await _in_tenant_tx(
                connect,
                tid,
                lambda conn: store_create(conn, tid, req, key, digest, service),
            )
        except HTTPException:
            raise
        except IdempotencyConflict as exc:
            detail: dict[str, Any] = {"code": exc.code}
            if exc.existing is not None:
                detail["task_ref"] = exc.existing["task_ref"]
            raise HTTPException(409, detail) from None
        except FieldNotFound:
            raise HTTPException(404, "field not found for this tenant") from None
        except Exception as exc:  # noqa: BLE001 - a store failure is the documented 503
            if getattr(exc, "sqlstate", None) == "23505":
                # Two keys for one anomaly raced past the read: the index kept one task.
                raise HTTPException(409, {"code": "anomaly_already_has_task"}) from None
            raise HTTPException(503, "field task store unavailable") from exc
        response.status_code = 200 if replayed else 201
        return {
            "persisted": True,
            "replayed": replayed,
            "task_id": task["task_id"],
            "task_ref": task["task_ref"],
            "task": task,
        }

    @router.get("/scouting")
    async def list_scouting_tasks(
        field_id: str = Query(...),
        season_id: str | None = Query(None),
        anomaly_ref: str | None = Query(None),
        limit: int = Query(200, ge=1, le=200),
        cursor: str | None = Query(None, max_length=128),
        tenant: str = Depends(require_tenant),
    ):
        if not _FIELD_ID_RE.fullmatch(field_id):
            raise HTTPException(400, "invalid field_id")
        if season_id is not None and not _SEASON_RE.fullmatch(season_id):
            raise HTTPException(400, "invalid season_id")
        if anomaly_ref is not None and not re.fullmatch(rf"{_ID}{{1,220}}", anomaly_ref):
            raise HTTPException(400, "invalid anomaly_ref")
        after = parse_page_cursor(cursor)
        tid = tenant_uuid(tenant)
        try:
            items = await _in_tenant_tx(
                connect,
                tid,
                lambda conn: store_list(
                    conn, tid, field_id, season_id, anomaly_ref, limit + 1, after
                ),
            )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "field task store unavailable") from exc
        next_cursor = None
        if len(items) > limit:
            items = items[:limit]
            last = items[-1]
            when = last["created_at"]
            next_cursor = f"{when.isoformat() if when else ''}|{last['task_id']}"
        return {
            "field_id": field_id,
            "season_id": season_id,
            "items": items,
            "count": len(items),
            "next_cursor": next_cursor,
        }

    return router
