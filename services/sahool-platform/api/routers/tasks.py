"""api/routers/tasks.py — مهامّ الحقل (Tasks / field_tasks)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسارات/الأذونات/المخرجات/الأحداث المُصدَرة/مخطّط OpenAPI
مطابقة تماماً لما كان في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى
``@router`` (بما فيها إصدار TASK_UPDATED حرفيّاً عبر ``_emit_domain_event``).

النماذج/الثوابت/المساعِدات (TaskListResponse/TaskSummary/TaskUpdateRequest/_TASK_COLS/
_TASK_STATUSES/_row_to_task/_emit_domain_event …) تبقى مُعرَّفة في ``api.main`` وتُستورَد
من هنا. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    _TASK_COLS,
    _TASK_STATUSES,
    CommandStore,
    Permission,
    TaskListResponse,
    TaskSummary,
    TaskUpdateRequest,
    UserSchema,
    _db_unavailable,
    _emit_domain_event,
    _idem_key,
    _idempotent,
    _row_to_task,
    get_pool,
    require_permission,
    tenant_connection,
)
from api.task_irrigation_observations import list_observations

router = APIRouter()


@router.get("/api/v1/tasks", response_model=TaskListResponse)
async def list_tasks(
    field_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    irrigation_task_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مهامّ المستأجِر (مُرشَّحة بـRLS، واختياريّاً بحقل). الأعلى أولويّةً ثمّ الأقرب موعداً.

    ترقيم اختياريّ متوافق للخلف (F5-06): بلا ``limit`` يُرجِع كلّ الصفوف كما كان
    (total/next_cursor = None). بتمرير ``limit`` (يُقصَر إلى 1..500) يُرجِع صفحةً مع
    ``total`` و``next_cursor`` (الإزاحة التالية) فتُميّز الواجهة «كلّ السجلّات» عن «أوّل
    صفحة». irrigation_task_id يعيد آخر 200 إفادة في irrigation_observations وtasks فارغة.
    """
    if irrigation_task_id is not None:
        try:
            async with tenant_connection(user) as conn:
                result = await list_observations(conn, user, irrigation_task_id)
                return TaskListResponse(tasks=[], irrigation_observations=result["observations"])
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _db_unavailable("قراءة ملاحظات الري", exc) from exc
    order = "ORDER BY priority ASC, recommended_date ASC NULLS LAST, created_at DESC"
    where = "WHERE field_id = $1 " if field_id else ""
    base_args: list[object] = [field_id] if field_id else []
    paginate = limit is not None
    eff_limit = max(1, min(int(limit), 500)) if paginate else None
    eff_offset = max(0, int(offset))
    try:
        async with tenant_connection(user) as conn:
            total: int | None = None
            if paginate:
                total = await conn.fetchval(
                    f"SELECT COUNT(*) FROM field_tasks {where}".strip(), *base_args
                )
                page_args = [*base_args, eff_limit, eff_offset]
                rows = await conn.fetch(
                    f"SELECT {_TASK_COLS} FROM field_tasks {where}{order} "
                    f"LIMIT ${len(base_args) + 1} OFFSET ${len(base_args) + 2}",
                    *page_args,
                )
            else:
                rows = await conn.fetch(
                    f"SELECT {_TASK_COLS} FROM field_tasks {where}{order}", *base_args
                )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة المهامّ", e) from e
    next_cursor: str | None = None
    if paginate and total is not None and eff_offset + len(rows) < total:
        next_cursor = str(eff_offset + (eff_limit or 0))
    return TaskListResponse(
        tasks=[_row_to_task(r) for r in rows],
        total=total,
        limit=eff_limit,
        next_cursor=next_cursor,
    )


@router.patch("/api/v1/tasks/{task_id}", response_model=TaskSummary)
async def update_task(
    task_id: str,
    req: TaskUpdateRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """تحديث مهمّة (الحالة/صورة/ملاحظة) — مُرشَّح بالمستأجِر (RLS). 404 لو ليست
    للمستأجِر؛ 422 على حالة غير معروفة أو لا حقول للتحديث.

    idempotent عند وجود Idempotency-Key (UUID): إعادة صندوق الإرسال دون اتّصال تُعيد
    النتيجة الأولى بلا تحديثٍ ثانٍ ولا حدثِ تحديثٍ مكرَّر؛ والمفتاح نفسه بحمولة
    مختلفة ⇒ 409."""
    if req.status is not None and req.status not in _TASK_STATUSES:
        raise HTTPException(status_code=422, detail="حالة مهمّة غير معروفة")
    sets: list[str] = []
    vals: list[object] = []
    if req.status is not None:
        vals.append(req.status)
        sets.append(f"status = ${len(vals)}")
        if req.status == "completed":
            sets.append("completed_at = NOW()")
    if req.photo_url is not None:
        vals.append(req.photo_url)
        sets.append(f"photo_url = ${len(vals)}")
    if req.notes is not None:
        vals.append(req.notes)
        sets.append(f"notes = ${len(vals)}")
    if not sets:
        raise HTTPException(status_code=422, detail="لا حقول للتحديث")
    sets.append("updated_at = NOW()")
    vals.append(task_id)
    query = (
        f"UPDATE field_tasks SET {', '.join(sets)} "
        f"WHERE task_id::TEXT = ${len(vals)} RETURNING {_TASK_COLS}"
    )
    try:
        async with tenant_connection(user) as conn:

            async def _work():
                row = await conn.fetchrow(query, *vals)
                # حدث تحديث المهمّة (تفاعليّ): يبثّه وكيل الإشعارات للواجهة حيّاً. داخل
                # المعاملة وفقط عند وجود الصفّ (مرشَّح بالمستأجِر عبر RLS).
                if row is not None:
                    await _emit_domain_event(
                        conn,
                        user,
                        "TASK_UPDATED",
                        "task",
                        task_id,
                        # القيم الفعليّة من الصفّ المُحدَّث (RETURNING) لا من req — req.status
                        # قد تكون None عند تحديث photo/notes فقط (ملاحظة Copilot).
                        {"status": row.get("status"), "field_id": row.get("field_id")},
                    )
                    return _row_to_task(row).model_dump(mode="json")
                # داخل المعاملة ⇒ لا يُسجَّل أمرٌ لمهمّةٍ غير موجودة.
                raise HTTPException(status_code=404, detail="المهمّة غير موجودة ضمن هذا المستأجِر")

            if idem:
                digest = hashlib.sha256(
                    json.dumps(
                        {"task_id": task_id, **req.model_dump(mode="json")},
                        sort_keys=True,
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest()
                return await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="task.update",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"task_id": task_id},
                    request_digest=digest,
                )
            return await _work()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تحديث المهمّة", e) from e


# ─── دورة حياة النشاط الحقليّ: انتقال حالة صفّ قائم (لا صفّ جديد) ────────────────
# كانت العمليّات إنشاءً فقط: «أنجزتُ» من الموبايل تُدرِج صفّاً جديداً فيبقى المُخطَّط
# planned للأبد وتتكرّر العمليّة ولا يُبلَغ skipped. هنا (لا في routers/fields — عند سقف
# حجمه) انتقالٌ واحد محروس: planned→done | planned→skipped؛ غيرهما 409؛ الحالة نفسها
# إعادةٌ بلا كتابة ولا حدث. تنفيذٌ في المستقبل مرفوض (reject_future_performed_on).
from api.api_models import ActivitySummary  # noqa: E402
from api.field_models import ActivityTransitionRequest  # noqa: E402 — مَراسي المسارات أعلاه
from api.idempotency import model_digest  # noqa: E402

_ACTIVITY_COLS = (
    "activity_id, field_id, season_id, activity_type, title_ar, details, "
    "scheduled_for, performed_on, status, created_at"
)


@router.patch(
    "/api/v1/fields/{field_id}/activities/{activity_id}",
    response_model=ActivitySummary,
)
async def transition_activity(
    field_id: str,
    activity_id: str,
    req: ActivityTransitionRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """ينقل نشاطاً قائماً إلى done (تاريخ تنفيذ ≤ اليوم+١ + قيم فعليّة اختياريّة تُدمَج في
    details) أو skipped — ضمن المستأجِر (RLS). 404 حقل/نشاط ليس له؛ 409 انتقال غير مسموح؛
    422 done بلا تاريخ أو بتاريخ مستقبليّ. idempotent بالحالة الهدف وبـIdempotency-Key."""
    from api.field_aggregate import (
        FieldInvariantError,
        activity_event_payload,
        check_activity_transition,
        merge_activity_actuals,
    )
    from api.field_state_projection import recompute_field_state
    from api.main import (
        _activity_event_type,
        _assert_field_in_tenant,
        _parse_date,
        _row_to_activity,
    )

    performed = _parse_date(req.performed_on, "تاريخ التنفيذ")
    req.validate_for_transition(performed)
    try:
        async with tenant_connection(user) as conn:

            async def _work():
                await _assert_field_in_tenant(conn, field_id)
                row = await conn.fetchrow(
                    f"SELECT {_ACTIVITY_COLS} FROM activities "
                    "WHERE activity_id = $1 AND field_id = $2 FOR UPDATE",
                    activity_id,
                    field_id,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="العمليّة غير موجودة لهذا الحقل")
                current = _row_to_activity(row)
                try:
                    changed = check_activity_transition(current.status, req.status)
                except FieldInvariantError as e:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "message_ar": e.message_ar,
                            "code": "invalid_activity_transition",
                            "from": current.status,
                            "to": req.status,
                        },
                    ) from e
                if not changed:
                    return current.model_dump()
                details = (
                    merge_activity_actuals(current.details, req.actuals())
                    if req.status == "done"
                    else current.details
                )
                updated = await conn.fetchrow(
                    "UPDATE activities SET status = $3, performed_on = $4, details = $5::jsonb "
                    "WHERE activity_id = $1 AND field_id = $2 AND status = 'planned' "
                    f"RETURNING {_ACTIVITY_COLS}",
                    activity_id,
                    field_id,
                    req.status,
                    performed,
                    json.dumps(details),
                )
                if updated is None:  # سباق: انتقل الصفّ بين القراءة والكتابة
                    raise HTTPException(
                        status_code=409,
                        detail={"message_ar": "تغيّرت حالة العمليّة", "code": "activity_changed"},
                    )
                payload = activity_event_payload(
                    field_id,
                    current.season_id,
                    current.activity_type,
                    req.status,
                    current.scheduled_for,
                    performed,
                )
                payload["previous_status"] = current.status
                await _emit_domain_event(
                    conn,
                    user,
                    _activity_event_type(current.activity_type, req.status),
                    "activity",
                    activity_id,
                    payload,
                )
                fs = await recompute_field_state(conn, field_id)
                if fs["changed"]:
                    await _emit_domain_event(
                        conn,
                        user,
                        "FIELD_STATE_CHANGED",
                        "field",
                        field_id,
                        {
                            "validity": fs["state"]["validity"],
                            "execution_mode": fs["state"]["execution_mode"],
                            "trigger": "activity.transitioned",
                        },
                    )
                return _row_to_activity(updated).model_dump()

            if idem:
                return await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="activity.transition",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"field_id": field_id, "activity_id": activity_id},
                    request_digest=model_digest(req, f"{field_id}/{activity_id}"),
                )
            return await _work()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("انتقال حالة العمليّة", e) from e
