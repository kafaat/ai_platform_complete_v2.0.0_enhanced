"""Pin inspection tasks: assignment, hand-off and review (owner: field-management-service).

Rebuilt from the platform routes carrier D #1439 held back (api/routers/scouting.py on
hold/v26-chain-a-held-routes). Public paths keep their shape under the service's prefix:
nginx maps ``/api/v1/field-tasks/...`` to ``/internal/field-tasks/...`` here.

What changed from the held code:
* the service that owns field_tasks writes it; the platform writes none of these rows;
* gap P3: an evidence version (v274) names the pin's scout photo evidence record (v260, owned by
  scout-ingest) by id and content digest, plus the inspector's notes. field_tasks.photo_url plays
  no part. An approval names the exact version it reviewed; when the pin's photo evidence is no
  longer that version's, the approval stops holding and v277's trigger refuses to close the task;
* the role claim comes from the gateway (fm_gateway), and the caller's current account (active,
  same role) is re-read from ``users`` before any hand-off write, as the held code did;
* no domain event is emitted: the outbox belongs to the platform (declared in the report).
"""

from __future__ import annotations

import hashlib
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fm_gateway import (
    FIELD_EDIT,
    FIELD_VIEW,
    INSPECTION_REVIEW,
    OBSERVATION_RECORD,
    Caller,
    caller_connection,
    caller_dependency,
    require,
)
from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

router = APIRouter(prefix="/internal/field-tasks")

OPEN_STATES = ("pending", "in_progress")
# Accounts that can hold an inspection (the held _ELIGIBLE_INSPECTORS) and that can review one.
INSPECTOR_ROLES = ("worker", "farmer", "agronomist", "expert", "manager", "owner", "admin")
REVIEWER_ROLES = ("agronomist", "expert", "manager", "owner", "admin")


def evidence_digest(photo_evidence_id, photo_content_sha256, notes) -> str:
    """The digest v274's guard recomputes: sha256('<id>|<sha>|<notes>'), '' for a NULL."""
    raw = "|".join(
        ["" if v is None else str(v) for v in (photo_evidence_id, photo_content_sha256, notes)]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def same_photo(version: dict | None, photo: dict | None) -> bool:
    """Whether a recorded version names exactly the pin's current photo evidence (or both none)."""
    if version is None:
        return False
    want = (version.get("photo_evidence_id"), version.get("photo_content_sha256"))
    have = (photo["evidence_id"], photo["content_sha256"]) if photo else (None, None)
    return tuple(None if v is None else str(v).strip() for v in want) == tuple(
        None if v is None else str(v).strip() for v in have
    )


# ── requests ────────────────────────────────────────────────────────────────


class PinInspectionRequest(BaseModel):
    assigned_to: int = Field(gt=0, le=2147483647)
    due_at: AwareDatetime
    priority: int = Field(ge=1, le=5, default=3)


class InspectionRevision(BaseModel):
    expected_revision: int = Field(ge=0, le=2147483646)


class Reassignment(InspectionRevision):
    assigned_to: int = Field(gt=0, le=2147483647)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class InspectionFinding(InspectionRevision):
    action: Literal["submit", "approve", "return"]
    reason: str = Field(min_length=1, max_length=2000)
    # submit: the inspector's notes, and the photo evidence the inspector saw (must still be the
    # pin's current one). approve/return: the evidence version the reviewer saw (required).
    notes: str | None = Field(default=None, max_length=4000)
    photo_evidence_id: UUID | None = None
    evidence_version: int | None = Field(default=None, gt=0, le=2147483647)

    @field_validator("reason", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _shape(self):
        if self.action == "submit":
            if self.evidence_version is not None:
                raise ValueError("a submit records a new evidence version; do not name one")
        else:
            if self.notes is not None or self.photo_evidence_id is not None:
                raise ValueError("notes and photo are attached by the inspector's submit")
            if self.evidence_version is None:
                raise ValueError("a review names the evidence_version it reviewed")
        return self


# ── reads ───────────────────────────────────────────────────────────────────

_INSPECTION_TASK = """
    SELECT task_id, source_scouting_pin_id AS pin_id, assigned_to,
           inspection_assigned_by AS assigned_by, inspection_initial_assignee,
           inspection_due_at AS due_at, priority, status
      FROM field_tasks
     WHERE tenant_id=$1::uuid AND field_id=$2 AND source_scouting_pin_id=$3
"""
_ELIGIBLE = " FROM users WHERE tenant_id=$1::uuid AND active AND role = ANY($2::text[])"


async def _require_field(conn, caller: Caller, field_id: str) -> None:
    if not await conn.fetchval(
        "SELECT true FROM fields WHERE tenant_id=$1::uuid AND field_id=$2",
        caller.tenant_id,
        field_id,
    ):
        raise HTTPException(404, "field not found for this tenant")


async def _require_pin(conn, caller: Caller, field_id: str, pin_id: str) -> None:
    await _require_field(conn, caller, field_id)
    if not await conn.fetchval(
        "SELECT true FROM scouting_pins WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3",
        caller.tenant_id,
        field_id,
        pin_id,
    ):
        raise HTTPException(404, "الدبوس غير موجود في هذا الحقل")


async def _eligible(conn, caller: Caller, user_id: str, roles) -> bool:
    return bool(
        await conn.fetchval(
            "SELECT true" + _ELIGIBLE + " AND id::text=$3", caller.tenant_id, list(roles), user_id
        )
    )


async def _photo(conn, caller: Caller, field_id: str, pin_id: str):
    row = await conn.fetchrow(
        "SELECT evidence_id, content_sha256 FROM scout_photo_evidence "
        "WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3",
        caller.tenant_id,
        field_id,
        pin_id,
    )
    return dict(row) if row else None


async def _load(conn, caller: Caller, field_id: str, task_id: UUID, *, write: bool):
    lock = "FOR UPDATE" if write else "FOR SHARE"
    row = await conn.fetchrow(
        f"""SELECT assigned_to, status, created_at, inspection_due_at, inspection_assigned_by,
                   source_scouting_pin_id AS pin_id
              FROM field_tasks WHERE tenant_id=$1::uuid AND field_id=$2 AND task_id=$3
               AND source_scouting_pin_id IS NOT NULL {lock}""",
        caller.tenant_id,
        field_id,
        task_id,
    )
    if row is None:
        raise HTTPException(404, "لم توجد مهمة تفتيش لهذا الدبوس في الحقل")
    events = await conn.fetch(
        """SELECT revision, action, previous_assignee, assignee, actor, reason, occurred_at,
                  evidence_version
             FROM inspection_handoffs WHERE tenant_id=$1::uuid AND field_id=$2 AND task_id=$3
            ORDER BY revision""",
        caller.tenant_id,
        field_id,
        task_id,
    )
    versions = await conn.fetch(
        """SELECT version, photo_evidence_id, photo_content_sha256, notes, digest, recorded_by,
                  recorded_at
             FROM inspection_evidence_versions WHERE tenant_id=$1::uuid AND field_id=$2
              AND task_id=$3 ORDER BY version""",
        caller.tenant_id,
        field_id,
        task_id,
    )
    task = dict(row) | {
        "evidence": [_version(v) for v in versions],
        "photo": await _photo(conn, caller, field_id, row["pin_id"]),
    }
    return task, [dict(e) for e in events]


def _version(row) -> dict:
    data = dict(row)
    if data.get("photo_evidence_id") is not None:
        data["photo_evidence_id"] = str(data["photo_evidence_id"])
    for key in ("photo_content_sha256", "digest"):
        if data.get(key) is not None:
            data[key] = str(data[key]).strip()
    return data


def view(task: dict, events: list[dict], caller: Caller) -> dict:
    """The hand-off state as the caller sees it (pure; unit-tested without a database)."""
    last = events[-1] if events else None
    accepted = bool(
        last
        and last["action"] not in ("reassign", "reopen")
        and last["assignee"] == task["assigned_to"]
    )
    open_task = task["status"] in OPEN_STATES
    history = task["evidence"]
    photo = task["photo"]
    latest = history[-1] if history else None
    current = latest if same_photo(latest, photo) else None
    approval = next((e for e in reversed(events) if e["action"] == "approve"), None)
    approved = next(
        (v for v in history if approval and v["version"] == approval["evidence_version"]), None
    )
    approved_holds = bool(approved and same_photo(approved, photo))
    mine = task["assigned_to"] == caller.user_id
    return {
        "review_state": last["action"] if last else "assigned",
        # Every recorded version stays readable; the approved one is never overwritten.
        "evidence": history,
        "approved_evidence": approved,
        "current_evidence": current
        or {
            "version": None,
            "photo_evidence_id": str(photo["evidence_id"]) if photo else None,
            "photo_content_sha256": str(photo["content_sha256"]).strip() if photo else None,
        },
        "evidence_approved": bool(last and last["action"] == "approve" and approved_holds),
        "evidence_pending_review": (approved is not None and not approved_holds)
        or bool(last and last["action"] == "submit"),
        "revision": last["revision"] if last else 0,
        "assigned_to": task["assigned_to"],
        "accepted": accepted,
        "assigned_by": task["inspection_assigned_by"],
        "assigned_at": task["created_at"],
        "initial_assignee": events[0]["previous_assignee"] if events else task["assigned_to"],
        "due_at": task["inspection_due_at"],
        "events": events,
        "can_accept": open_task and not accepted and mine and caller.can(OBSERVATION_RECORD),
        "can_reassign": open_task and caller.can(FIELD_EDIT),
        "can_submit": open_task
        and accepted
        and bool(last and last["action"] in ("accept", "return", "approve"))
        and mine
        and caller.can(OBSERVATION_RECORD),
        "can_review": open_task
        and bool(last and last["action"] == "submit")
        and not mine
        and caller.can(INSPECTION_REVIEW),
    }


# ── routes ──────────────────────────────────────────────────────────────────


def _db_error(exc: Exception) -> HTTPException:
    return HTTPException(503, "field task store unavailable")


@router.get("/fields/{field_id}/inspection-assignees")
async def list_inspection_assignees(
    field_id: str, caller: Caller = Depends(caller_dependency(FIELD_EDIT))
):
    try:
        async with caller_connection(caller) as conn:
            await _require_field(conn, caller, field_id)
            rows = await conn.fetch(
                "SELECT id, full_name" + _ELIGIBLE + " ORDER BY full_name, id",
                caller.tenant_id,
                list(INSPECTOR_ROLES),
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - a store failure is the documented 503
        raise _db_error(exc) from exc
    return {"assignees": [dict(r) for r in rows]}


@router.get("/fields/{field_id}/pins/{pin_id}/inspection-task")
async def get_pin_inspection_task(
    field_id: str, pin_id: str, caller: Caller = Depends(caller_dependency(FIELD_VIEW))
):
    try:
        async with caller_connection(caller) as conn:
            await _require_pin(conn, caller, field_id, pin_id)
            row = await conn.fetchrow(_INSPECTION_TASK, caller.tenant_id, field_id, pin_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_error(exc) from exc
    return {"task": dict(row) if row else None}


@router.post("/fields/{field_id}/pins/{pin_id}/inspection-task")
async def assign_pin_inspection(
    field_id: str,
    pin_id: str,
    req: PinInspectionRequest,
    caller: Caller = Depends(caller_dependency(FIELD_EDIT)),
):
    try:
        async with caller_connection(caller) as conn:
            await _require_pin(conn, caller, field_id, pin_id)
            # Serialize creation and retries for this pin, including other managers' requests.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"inspection:{caller.tenant_id}:{pin_id}",
            )
            row = await conn.fetchrow(_INSPECTION_TASK, caller.tenant_id, field_id, pin_id)
            if row:
                same = (row["inspection_initial_assignee"], row["due_at"], row["priority"]) == (
                    str(req.assigned_to),
                    req.due_at,
                    req.priority,
                )
                if not same:
                    raise HTTPException(409, "يوجد تكليف تفتيش آخر لهذا الدبوس")
                return {"task": dict(row), "persisted": True}
            if not await _eligible(conn, caller, str(req.assigned_to), INSPECTOR_ROLES):
                raise HTTPException(422, "المستلم غير متاح للتكليف في هذه المزرعة")
            await conn.execute(
                """INSERT INTO field_tasks
                    (tenant_id, field_id, task_type, source_scouting_pin_id, assigned_to,
                     recommended_date, inspection_due_at, inspection_assigned_by,
                     inspection_initial_assignee, priority)
                   VALUES ($1::uuid,$2,'scouting',$3,$4::text,$5,$6,$7,$4::text,$8)""",
                caller.tenant_id,
                field_id,
                pin_id,
                str(req.assigned_to),
                req.due_at.date(),
                req.due_at,
                caller.user_id,
                req.priority,
            )
            row = await conn.fetchrow(_INSPECTION_TASK, caller.tenant_id, field_id, pin_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_error(exc) from exc
    return {"task": dict(row), "persisted": True}


@router.get("/fields/{field_id}/tasks/{task_id}/handoff")
async def inspect_handoff(
    field_id: str, task_id: UUID, caller: Caller = Depends(caller_dependency(FIELD_VIEW))
):
    try:
        async with caller_connection(caller) as conn:
            task, events = await _load(conn, caller, field_id, task_id, write=False)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_error(exc) from exc
    return view(task, events, caller)


async def _append(
    conn, caller, field_id, task_id, revision, action, previous, assignee, reason, version=None
):
    await conn.execute(
        """INSERT INTO inspection_handoffs
            (tenant_id, field_id, task_id, revision, action, previous_assignee, assignee, actor,
             reason, evidence_version)
           VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
        caller.tenant_id,
        field_id,
        task_id,
        revision,
        action,
        previous,
        assignee,
        caller.user_id,
        reason,
        version,
    )


async def _transition(field_id: str, task_id: UUID, req, caller: Caller):
    reassignment = isinstance(req, Reassignment)
    action = "reassign" if reassignment else "accept"
    new_assignee = str(req.assigned_to) if reassignment else caller.user_id
    reason = req.reason if reassignment else None
    async with caller_connection(caller) as conn:
        task, events = await _load(conn, caller, field_id, task_id, write=True)
        current = view(task, events, caller)
        # A revision names the exact command slot, even after a later shift has taken over.
        if req.expected_revision < current["revision"]:
            event = events[req.expected_revision]
            if (event["actor"], event["action"], event["assignee"], event["reason"]) == (
                caller.user_id,
                action,
                new_assignee,
                reason,
            ):
                return current
        if req.expected_revision != current["revision"]:
            raise HTTPException(409, "تغيّر سجل التكليف. حدّث البيانات")
        if task["status"] not in OPEN_STATES:
            raise HTTPException(409, "مهمة التفتيش مغلقة")
        if reassignment:
            if new_assignee == task["assigned_to"]:
                raise HTTPException(422, "اختر مستلماً مختلفاً")
            if not await _eligible(conn, caller, new_assignee, INSPECTOR_ROLES):
                raise HTTPException(422, "المستلم غير متاح في المزرعة")
            await conn.execute(
                """UPDATE field_tasks SET assigned_to=$4, updated_at=clock_timestamp()
                    WHERE tenant_id=$1::uuid AND field_id=$2 AND task_id=$3""",
                caller.tenant_id,
                field_id,
                task_id,
                new_assignee,
            )
        elif task["assigned_to"] != caller.user_id:
            raise HTTPException(403, "قبول المهمة متاح للمستلم المعيّن")
        elif current["accepted"]:
            raise HTTPException(409, "سبق قبول هذا التكليف")
        elif not await _eligible(conn, caller, caller.user_id, INSPECTOR_ROLES):
            raise HTTPException(403, "حساب المستلم غير نشط أو لم يعد مخولاً للتفتيش")
        await _append(
            conn,
            caller,
            field_id,
            task_id,
            current["revision"] + 1,
            action,
            task["assigned_to"],
            new_assignee,
            reason,
        )
        task, events = await _load(conn, caller, field_id, task_id, write=False)
        return view(task, events, caller)


@router.post("/fields/{field_id}/tasks/{task_id}/handoff/accept")
async def accept_inspection(
    field_id: str,
    task_id: UUID,
    req: InspectionRevision,
    caller: Caller = Depends(caller_dependency(OBSERVATION_RECORD)),
):
    try:
        return await _transition(field_id, task_id, req, caller)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_error(exc) from exc


@router.post("/fields/{field_id}/tasks/{task_id}/handoff/reassign")
async def reassign_inspection(
    field_id: str,
    task_id: UUID,
    req: Reassignment,
    caller: Caller = Depends(caller_dependency(FIELD_EDIT)),
):
    try:
        return await _transition(field_id, task_id, req, caller)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_error(exc) from exc


async def _record_version(conn, caller, field_id, task_id, pin_id, photo, notes) -> int:
    """Append (photo, notes) as the next evidence version unless it already is the latest."""
    photo_id = str(photo["evidence_id"]) if photo else None
    photo_sha = str(photo["content_sha256"]).strip() if photo else None
    digest = evidence_digest(photo_id, photo_sha, notes)
    latest = await conn.fetchrow(
        """SELECT version, digest FROM inspection_evidence_versions
            WHERE tenant_id=$1::uuid AND task_id=$2 ORDER BY version DESC LIMIT 1""",
        caller.tenant_id,
        task_id,
    )
    if latest is not None and str(latest["digest"]).strip() == digest:
        return latest["version"]
    version = (latest["version"] if latest else 0) + 1
    await conn.execute(
        """INSERT INTO inspection_evidence_versions
            (tenant_id, field_id, task_id, version, pin_id, photo_evidence_id,
             photo_content_sha256, notes, digest, recorded_by)
           VALUES ($1::uuid,$2,$3,$4,$5,$6::uuid,$7,$8,$9,$10)""",
        caller.tenant_id,
        field_id,
        task_id,
        version,
        pin_id,
        photo_id,
        photo_sha,
        notes,
        digest,
        caller.user_id,
    )
    return version


async def _finding(field_id: str, task_id: UUID, req: InspectionFinding, caller: Caller):
    submit = req.action == "submit"
    require(caller, OBSERVATION_RECORD if submit else INSPECTION_REVIEW)
    async with caller_connection(caller) as conn:
        task, events = await _load(conn, caller, field_id, task_id, write=True)
        if not await _eligible(
            conn, caller, caller.user_id, INSPECTOR_ROLES if submit else REVIEWER_ROLES
        ):
            raise HTTPException(403, "الحساب غير نشط أو تغيرت صلاحياته")
        current = view(task, events, caller)
        if req.expected_revision < current["revision"]:
            prior = events[req.expected_revision]
            seen = next(
                (v for v in task["evidence"] if v["version"] == prior["evidence_version"]), {}
            )
            same_event = (prior["action"], prior["actor"], prior["reason"]) == (
                req.action,
                caller.user_id,
                req.reason,
            )
            same_evidence = (
                seen.get("notes") == req.notes
                if submit
                else prior["evidence_version"] == req.evidence_version
            )
            if same_event and same_evidence:
                return current
        if (caller.user_id == task["assigned_to"]) != submit:
            raise HTTPException(403, "يرفع المستلم نتيجة الزيارة ويراجعها شخص آخر")
        if (
            req.expected_revision != current["revision"]
            or not current["can_submit" if submit else "can_review"]
        ):
            raise HTTPException(409, "تغيرت حالة الزيارة أو لم تجهز لهذا الإجراء")
        photo = task["photo"]
        if submit:
            if req.photo_evidence_id is not None and (
                photo is None or str(photo["evidence_id"]) != str(req.photo_evidence_id)
            ):
                raise HTTPException(409, "تغيرت صورة الدبوس. حدّث البيانات قبل رفع النتيجة")
            version = await _record_version(
                conn, caller, field_id, task_id, task["pin_id"], photo, req.notes
            )
            approved = current["approved_evidence"]
            if (
                events[-1]["action"] == "approve"
                and approved
                and approved["version"] == version
                and current["evidence_approved"]
            ):
                raise HTTPException(409, "لم تتغير الصورة أو الملاحظات منذ اعتماد النتيجة")
        else:
            # The review binds to the version that was submitted, which must be the one the
            # reviewer names and still match the pin's photo evidence.
            version = events[-1]["evidence_version"]
            if req.evidence_version != version:
                raise HTTPException(409, "النسخة المراجَعة ليست النسخة المرفوعة. حدّث البيانات")
            submitted = next((v for v in task["evidence"] if v["version"] == version), None)
            if req.action == "approve" and not same_photo(submitted, photo):
                raise HTTPException(409, "تغيرت صورة الدبوس بعد رفع النتيجة. أعدها للاستكمال")
        await _append(
            conn,
            caller,
            field_id,
            task_id,
            current["revision"] + 1,
            req.action,
            task["assigned_to"],
            task["assigned_to"],
            req.reason,
            version,
        )
        task, events = await _load(conn, caller, field_id, task_id, write=False)
        return view(task, events, caller)


@router.post("/fields/{field_id}/tasks/{task_id}/handoff/finding")
async def record_inspection_finding(
    field_id: str,
    task_id: UUID,
    req: InspectionFinding,
    caller: Caller = Depends(caller_dependency(FIELD_VIEW)),
):
    """The assignee submits the finding; someone else approves or returns that exact version."""
    try:
        return await _finding(field_id, task_id, req, caller)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_error(exc) from exc
