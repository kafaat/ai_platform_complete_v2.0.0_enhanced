"""api/routers/scouting.py — تصنيف المشاهدات (Scouting Taxonomy)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الكتالوجات/الدوالّ النقيّة (``api.scouting_pins``) تُستورَد مباشرةً من وحدتها — وهي
نفس الكائنات التي كانت في ``main`` (``make_pin`` يبقى مُستورَداً هناك لنقطة الـpins).
أمّا التبعية ``get_current_user``/``UserSchema`` فتبقى في ``main`` وتُستورَد من
``api.main`` حفظاً لاستيرادات الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main``
يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.

نقطة القراءة الدائمة (v94): ``GET /api/v1/scouting/pins?field_id=…`` تُرجِع الدبابيس
المُثبَّتة في ``scouting_pins`` (التي تكتبها نقطة POST ``/fields/{id}/pins``)، معزولةً
بالمستأجِر عبر RLS (نفس نمط قراءات الحقول). صدق: القاعدة غير مفعّلة ⇒ قائمة فارغة
صريحة مع سبب (لا اختراع مشاهدات).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from core.authorization import has_permission
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, Field, field_validator

from api import main as api_main
from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    get_current_user,
    require_permission,
    tenant_connection,
)
from api.scouting_pins import (
    NUTRIENT_DEFICIENCY_GUIDE,
    YEMEN_CROP_ISSUES,
    get_crop_issues,
)

router = APIRouter()

# أعمدة القراءة لجدول scouting_pins (v94) — مطابقة لـ ScoutingPin.to_dict تماماً
# (pin_id هو المعرّف القانوني للدبّوس). created_at يُنسَّق ISO في المُحوِّل أدناه.
# v257: مصدر الموقع ودقّته. صورة الدبّوس ليست هنا: مصدرها scout_photo_evidence (v260، scout-ingest).
_PIN_SELECT_COLS = (
    "pin_id, field_id, lat, lng, issue_category, severity, status, persistence, "
    "crop, issue_code, note_ar, photo_uri, color, created_by, created_at, "
    "location_source, accuracy_m"
)


def _row_to_pin(row) -> dict:
    """يحوّل صفّ scouting_pins إلى dict مطابق لـ ScoutingPin.to_dict (مفتاح pin_id).

    نقيّ (لا I/O) ليُختبَر بـunit بلا قاعدة حيّة. ``created_at`` (timestamptz) يُنسَّق
    ISO؛ إن كان نصّاً أصلاً (mock) يُمرَّر كما هو.
    """
    created = row["created_at"]
    created_iso = created.isoformat() if hasattr(created, "isoformat") else (created or "")
    return {
        "pin_id": row["pin_id"],
        "field_id": row["field_id"],
        "lat": row["lat"],
        "lng": row["lng"],
        "issue_category": row["issue_category"],
        "severity": row["severity"],
        "status": row["status"],
        "persistence": row["persistence"],
        "crop": row["crop"],
        "issue_code": row["issue_code"],
        "note_ar": row["note_ar"],
        "photo_uri": row["photo_uri"],
        "color": row["color"],
        "created_by": row["created_by"],
        "created_at": created_iso,
        # v257: صفّ قبل الهجرة أو من عميل قديم ⇒ unknown (لا استنتاج من الإحداثيّات).
        "location_source": row.get("location_source") or "unknown",
        "accuracy_m": row.get("accuracy_m"),
    }


@router.get("/api/v1/scouting/pins")
async def list_scouting_pins(
    field_id: str = Query(..., description="معرّف الحقل لجلب دبابيسه"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """دبابيس مشاهدة الحقل المُخزَّنة (الأحدث أوّلاً) — معزولة بالمستأجِر (RLS).

    تقرأ من ``scouting_pins`` (v94) ما تكتبه نقطة POST ``/fields/{id}/pins`` — فتُغلِق
    الفجوة التي أبقت الواجهة الدبابيس محلّيّة للجلسة. تتحقّق أوّلاً أنّ الحقل يخصّ
    المستأجِر (404 وإلّا) عبر RLS، ثمّ تُرجِع ``{field_id, pins, total}``. صدق: القاعدة
    غير مفعّلة (``DATABASE_URL``) ⇒ قائمة فارغة + سبب (لا مشاهدات مخترَعة)؛ تعذّر
    القاعدة أثناء التنفيذ ⇒ 503 موثَّق.
    """
    if api_main._DB_POOL is None:
        return {
            "field_id": field_id,
            "pins": [],
            "total": 0,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا دبابيس مُخزَّنة",
        }
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                f"SELECT {_PIN_SELECT_COLS} FROM scouting_pins "
                "WHERE field_id = $1 ORDER BY created_at DESC",
                field_id,
            )
    except HTTPException:
        raise  # 404 (حقل خارج المستأجِر) يصعد كما هو
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا اختراع تاريخ)
        raise _db_unavailable("جلب دبابيس الاستطلاع", e) from e
    pins = [_row_to_pin(r) for r in rows]
    return {"field_id": field_id, "pins": pins, "total": len(pins)}


@router.get("/api/v1/scouting/taxonomy")
def scouting_taxonomy(
    crop: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """قوائم المشاكل (للقوائم المنسدلة). لو crop معطى، يُرجع مشاكله فقط."""
    if crop:
        return {"crop": crop, "issues": get_crop_issues(crop)}
    return {
        "crops": list(YEMEN_CROP_ISSUES.keys()),
        "all_issues": YEMEN_CROP_ISSUES,
        "nutrient_guide": NUTRIENT_DEFICIENCY_GUIDE,
    }


class PinInspectionRequest(BaseModel):
    assigned_to: int = Field(gt=0, le=2147483647)
    due_at: AwareDatetime
    priority: int = Field(ge=1, le=5, default=3)


_INSPECTION_QUERY = """
    SELECT task_id, source_scouting_pin_id AS pin_id, assigned_to,
           inspection_assigned_by AS assigned_by, inspection_initial_assignee, inspection_due_at AS due_at, priority, status
      FROM field_tasks
     WHERE tenant_id=$1::uuid AND field_id=$2 AND source_scouting_pin_id=$3
"""


_ELIGIBLE_INSPECTORS = """
    FROM users WHERE tenant_id=$1::uuid AND active
      AND role IN ('worker','farmer','agronomist','expert','manager','owner','admin')
"""


@router.get("/api/v1/fields/{field_id}/inspection-assignees")
async def list_inspection_assignees(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    async with tenant_connection(user) as conn:
        await _assert_field_in_tenant(conn, field_id)
        rows = await conn.fetch(
            "SELECT id, full_name " + _ELIGIBLE_INSPECTORS + " ORDER BY full_name, id",
            user.tenant_id,
        )
        return {"assignees": [dict(row) for row in rows]}


async def _require_saved_pin(conn, tenant_id, field_id, pin_id):
    await _assert_field_in_tenant(conn, field_id)
    if not await conn.fetchval(
        "SELECT true FROM scouting_pins WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3",
        tenant_id,
        field_id,
        pin_id,
    ):
        raise HTTPException(404, "الدبوس غير موجود في هذا الحقل")


@router.get("/api/v1/fields/{field_id}/pins/{pin_id}/inspection-task")
async def get_pin_inspection_task(
    field_id: str,
    pin_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    async with tenant_connection(user) as conn:
        await _require_saved_pin(conn, user.tenant_id, field_id, pin_id)
        row = await conn.fetchrow(_INSPECTION_QUERY, user.tenant_id, field_id, pin_id)
        return {"task": dict(row) if row else None}


@router.post("/api/v1/fields/{field_id}/pins/{pin_id}/inspection-task")
async def assign_pin_inspection(
    field_id: str,
    pin_id: str,
    req: PinInspectionRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    async with tenant_connection(user) as conn:
        await _require_saved_pin(conn, user.tenant_id, field_id, pin_id)
        # Serialize creation and retries for this pin, including requests from other managers.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", "inspection:" + pin_id
        )
        row = await conn.fetchrow(_INSPECTION_QUERY, user.tenant_id, field_id, pin_id)
        if row:
            if (row["inspection_initial_assignee"], row["due_at"], row["priority"]) != (
                str(req.assigned_to),
                req.due_at,
                req.priority,
            ):
                raise HTTPException(409, "يوجد تكليف تفتيش آخر لهذا الدبوس")
        else:
            if not await conn.fetchval(
                "SELECT true " + _ELIGIBLE_INSPECTORS + " AND id=$2",
                user.tenant_id,
                req.assigned_to,
            ):
                raise HTTPException(422, "المستلم غير متاح للتكليف في هذه المزرعة")
            await conn.execute(
                """INSERT INTO field_tasks
                    (tenant_id, field_id, task_type, source_scouting_pin_id, assigned_to,
                     recommended_date, inspection_due_at, inspection_assigned_by, inspection_initial_assignee, priority)
                   VALUES ($1::uuid,$2,'scouting',$3,$4::text,$5,$6,$7,$4::text,$8)""",
                user.tenant_id,
                field_id,
                pin_id,
                str(req.assigned_to),
                req.due_at.date(),
                req.due_at,
                str(user.user_id),
                req.priority,
            )
            row = await conn.fetchrow(_INSPECTION_QUERY, user.tenant_id, field_id, pin_id)
            await api_main._emit_domain_event(
                conn,
                user,
                "TASK_CREATED",
                "task",
                str(row["task_id"]),
                {"field_id": field_id, "pin_id": pin_id, "assigned_to": row["assigned_to"]},
            )
        return {"task": dict(row), "persisted": True}


# ── تسليم مهمّة التفتيش: القبول وإعادة التكليف (v248، سجلّ inspection_handoffs) ──


class InspectionRevision(BaseModel):
    expected_revision: int = Field(ge=0, le=2147483646)


class InspectionFinding(InspectionRevision):
    action: Literal["submit", "approve", "return"]
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_note(cls, value):
        return value.strip() if isinstance(value, str) else value


class Reassignment(InspectionRevision):
    assigned_to: int = Field(gt=0, le=2147483647)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


async def _load(conn, tenant, field, task, *, write):
    lock = "FOR UPDATE" if write else "FOR SHARE"
    row = await conn.fetchrow(
        f"""SELECT assigned_to, status, created_at, inspection_due_at, inspection_assigned_by
            FROM field_tasks WHERE tenant_id=$1::uuid AND field_id=$2 AND task_id=$3
            AND source_scouting_pin_id IS NOT NULL {lock}""",
        tenant,
        field,
        task,
    )
    if row is None:
        raise HTTPException(404, "لم توجد مهمة تفتيش لهذا الدبوس في الحقل")
    events = await conn.fetch(
        """SELECT revision, action, previous_assignee, assignee, actor, reason, occurred_at
           FROM inspection_handoffs WHERE tenant_id=$1::uuid AND field_id=$2 AND task_id=$3
           ORDER BY revision""",
        tenant,
        field,
        task,
    )
    return row, [dict(event) for event in events]


def _view(row, events, user):
    last = events[-1] if events else None
    accepted = bool(
        last
        and last["action"] not in ("reassign", "reopen")
        and last["assignee"] == row["assigned_to"]
    )
    open_task = row["status"] in ("pending", "in_progress")
    return {
        "review_state": last["action"] if last else "assigned",
        "can_submit": open_task
        and accepted
        and last["action"] in ("accept", "return")
        and row["assigned_to"] == str(user.user_id)
        and has_permission(user, Permission.OBSERVATION_RECORD),
        "can_review": open_task
        and bool(last and last["action"] == "submit")
        and row["assigned_to"] != str(user.user_id)
        and has_permission(user, Permission.INSPECTION_REVIEW),
        "revision": last["revision"] if last else 0,
        "assigned_to": row["assigned_to"],
        "accepted": accepted,
        "assigned_by": row["inspection_assigned_by"],
        "assigned_at": row["created_at"],
        "initial_assignee": events[0]["previous_assignee"] if events else row["assigned_to"],
        "due_at": row["inspection_due_at"],
        "events": events,
        "can_accept": open_task
        and not accepted
        and row["assigned_to"] == str(user.user_id)
        and has_permission(user, Permission.OBSERVATION_RECORD),
        "can_reassign": open_task and has_permission(user, Permission.FIELD_EDIT),
    }


@router.get("/api/v1/fields/{field_id}/tasks/{task_id}/handoff")
async def inspect_handoff(
    field_id: str,
    task_id: UUID,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    async with tenant_connection(user) as conn:
        row, events = await _load(conn, user.tenant_id, field_id, task_id, write=False)
        return _view(row, events, user)


async def _transition(field_id, task_id, req, user):
    actor = str(user.user_id)
    reassignment = isinstance(req, Reassignment)
    action = "reassign" if reassignment else "accept"
    new_assignee = str(req.assigned_to) if reassignment else actor
    reason = req.reason if reassignment else None
    async with tenant_connection(user) as conn:
        row, events = await _load(conn, user.tenant_id, field_id, task_id, write=True)
        current = _view(row, events, user)
        # A revision identifies the exact command slot, even after a later shift has taken over.
        if req.expected_revision < current["revision"]:
            event = events[req.expected_revision]
            if (event["actor"], event["action"], event["assignee"], event["reason"]) == (
                actor,
                action,
                new_assignee,
                reason,
            ):
                return current
        if req.expected_revision != current["revision"]:
            raise HTTPException(409, "تغيّر سجل التكليف. حدّث البيانات")
        if row["status"] not in ("pending", "in_progress"):
            raise HTTPException(409, "مهمة التفتيش مغلقة")
        if reassignment:
            if new_assignee == row["assigned_to"]:
                raise HTTPException(422, "اختر مستلماً مختلفاً")
            if not await conn.fetchval(
                "SELECT true " + _ELIGIBLE_INSPECTORS + " AND id=$2",
                user.tenant_id,
                req.assigned_to,
            ):
                raise HTTPException(422, "المستلم غير متاح في المزرعة")
            await conn.execute(
                """UPDATE field_tasks SET assigned_to=$4, updated_at=clock_timestamp()
                   WHERE tenant_id=$1::uuid AND field_id=$2 AND task_id=$3""",
                user.tenant_id,
                field_id,
                task_id,
                new_assignee,
            )
        elif row["assigned_to"] != actor:
            raise HTTPException(403, "قبول المهمة متاح للمستلم المعيّن")
        elif current["accepted"]:
            raise HTTPException(409, "سبق قبول هذا التكليف")
        elif not await conn.fetchval(
            "SELECT true " + _ELIGIBLE_INSPECTORS + " AND id::text=$2", user.tenant_id, actor
        ):
            raise HTTPException(403, "حساب المستلم غير نشط أو لم يعد مخولاً للتفتيش")
        await conn.execute(
            """INSERT INTO inspection_handoffs
                (tenant_id, field_id, task_id, revision, action, previous_assignee, assignee, actor, reason)
                VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9)""",
            user.tenant_id,
            field_id,
            task_id,
            current["revision"] + 1,
            action,
            row["assigned_to"],
            new_assignee,
            actor,
            reason,
        )
        row, events = await _load(conn, user.tenant_id, field_id, task_id, write=False)
        return _view(row, events, user)


@router.post("/api/v1/fields/{field_id}/tasks/{task_id}/handoff/accept")
async def accept_inspection(
    field_id: str,
    task_id: UUID,
    req: InspectionRevision,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    return await _transition(field_id, task_id, req, user)


@router.post("/api/v1/fields/{field_id}/tasks/{task_id}/handoff/reassign")
async def reassign_inspection(
    field_id: str,
    task_id: UUID,
    req: Reassignment,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    return await _transition(field_id, task_id, req, user)


_SUBMIT_ROLES = ("worker", "farmer", "agronomist", "expert", "manager", "owner", "admin")
_REVIEW_ROLES = ("agronomist", "expert", "manager", "owner", "admin")


@router.post("/api/v1/fields/{field_id}/tasks/{task_id}/handoff/finding")
async def record_inspection_finding(
    field_id: str,
    task_id: UUID,
    req: InspectionFinding,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """The assignee submits the finding; someone else approves it or returns it (v254)."""
    submit = req.action == "submit"
    required = Permission.OBSERVATION_RECORD if submit else Permission.INSPECTION_REVIEW
    actor = str(user.user_id)
    if not has_permission(user, required):
        raise HTTPException(403, "لا تملك صلاحية هذا الإجراء")
    async with tenant_connection(user) as conn:
        row, events = await _load(conn, user.tenant_id, field_id, task_id, write=True)
        if not await conn.fetchval(
            "SELECT true FROM users WHERE tenant_id=$1::uuid AND id::text=$2 AND active AND role=ANY($3::text[])",
            user.tenant_id,
            actor,
            list(_SUBMIT_ROLES if submit else _REVIEW_ROLES),
        ):
            raise HTTPException(403, "الحساب غير نشط أو تغيرت صلاحياته")
        current = _view(row, events, user)
        if req.expected_revision < current["revision"]:
            prior = events[req.expected_revision]
            if (prior["action"], prior["actor"], prior["reason"]) == (
                req.action,
                actor,
                req.reason,
            ):
                return current
        if (actor == row["assigned_to"]) != submit:
            raise HTTPException(403, "يرفع المستلم نتيجة الزيارة ويراجعها شخص آخر")
        if (
            req.expected_revision != current["revision"]
            or not current["can_submit" if submit else "can_review"]
        ):
            raise HTTPException(409, "تغيرت حالة الزيارة أو لم تجهز لهذا الإجراء")
        await conn.execute(
            """INSERT INTO inspection_handoffs
               (tenant_id,field_id,task_id,revision,action,previous_assignee,assignee,actor,reason)
               VALUES ($1::uuid,$2,$3,$4,$5,$6,$6,$7,$8)""",
            user.tenant_id,
            field_id,
            task_id,
            current["revision"] + 1,
            req.action,
            row["assigned_to"],
            actor,
            req.reason,
        )
        row, events = await _load(conn, user.tenant_id, field_id, task_id, write=False)
        return _view(row, events, user)
