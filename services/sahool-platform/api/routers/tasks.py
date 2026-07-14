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

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    _TASK_COLS,
    _TASK_STATUSES,
    Permission,
    TaskListResponse,
    TaskSummary,
    TaskUpdateRequest,
    UserSchema,
    _db_unavailable,
    _emit_domain_event,
    _row_to_task,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/tasks", response_model=TaskListResponse)
async def list_tasks(
    field_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مهامّ المستأجِر (مُرشَّحة بـRLS، واختياريّاً بحقل). الأعلى أولويّةً ثمّ الأقرب موعداً.

    ترقيم اختياريّ متوافق للخلف (F5-06): بلا ``limit`` يُرجِع كلّ الصفوف كما كان
    (total/next_cursor = None). بتمرير ``limit`` (يُقصَر إلى 1..500) يُرجِع صفحةً مع
    ``total`` و``next_cursor`` (الإزاحة التالية) فتُميّز الواجهة «كلّ السجلّات» عن «أوّل
    صفحة». يُرجِع {tasks:[...]} دائماً (عقد الواجهة). 503 عند تعذّر القاعدة.
    """
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
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """تحديث مهمّة (الحالة/صورة/ملاحظة) — مُرشَّح بالمستأجِر (RLS). 404 لو ليست
    للمستأجِر؛ 422 على حالة غير معروفة أو لا حقول للتحديث."""
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
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تحديث المهمّة", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="المهمّة غير موجودة ضمن هذا المستأجِر")
    return _row_to_task(row)
