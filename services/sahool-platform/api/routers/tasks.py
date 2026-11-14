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

from api.api_models import task_allowed_sources
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
        tasks=[_row_to_task(r, user) for r in rows],
        total=total,
        limit=eff_limit,
        next_cursor=next_cursor,
    )


@router.patch("/api/v1/tasks/{task_id}", response_model=TaskSummary)
async def update_task(
    task_id: str,
    req: TaskUpdateRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_EXECUTE)),
):
    """تحديث مهمّة (الحالة/صورة/ملاحظة) — مُرشَّح بالمستأجِر (RLS). 404 لو ليست
    للمستأجِر؛ 422 على حالة غير معروفة أو لا حقول للتحديث.

    idempotent عند وجود Idempotency-Key (UUID): إعادة صندوق الإرسال دون اتّصال تُعيد
    النتيجة الأولى بلا تحديثٍ ثانٍ ولا حدثِ تحديثٍ مكرَّر؛ والمفتاح نفسه بحمولة
    مختلفة ⇒ 409.

    انتقالُ الحالة مشروطٌ ذرّيّاً بجدول ``TASK_TRANSITIONS`` (شرط ``WHERE`` على الحالة
    الحاليّة)؛ الانتقالُ غيرُ المسموح ⇒ 409. ``completed_at`` من الجهاز (مزامنةٌ دون اتّصال)
    يُحفَظ كما هو، وبغيابه يُختَم بوقت الخادم مرّةً واحدة (إعادةُ الإنجاز لا تُزيحه)؛ وإعادةُ
    فتح مهمّةٍ منجَزة تمسحه."""
    if req.status is not None and req.status not in _TASK_STATUSES:
        raise HTTPException(status_code=422, detail="حالة مهمّة غير معروفة")
    sets: list[str] = []
    vals: list[object] = []
    # الأعمدة المُرسَلة وقيمها المربوطة: تُسمّى في الحدث، ويُقارَن بها الصفّ كي لا تُكتب
    # إعادةٌ لا تغيّر شيئاً (trigger يرفع updated_at على كلّ UPDATE، وهو هويّة الطفرة، C-14).
    changed: dict[str, int] = {}
    stamp_differs: list[str] = []
    if req.status is not None:
        vals.append(req.status)
        sets.append(f"status = ${len(vals)}")
        changed["status"] = len(vals)
        if req.status == "completed" and req.completed_at is not None:
            vals.append(req.completed_at)
            sets.append(f"completed_at = ${len(vals)}")
            changed["completed_at"] = len(vals)
        elif req.status == "completed":
            # SET يقرأ القيمَ القديمة: إنجازٌ مكرَّر يُبقي الختمَ الأوّل.
            sets.append(
                "completed_at = CASE WHEN status = 'completed' AND completed_at IS NOT NULL "
                "THEN completed_at ELSE NOW() END"
            )
            stamp_differs.append("completed_at IS NULL")
        elif req.status in ("pending", "in_progress"):
            sets.append("completed_at = NULL")
            stamp_differs.append("completed_at IS NOT NULL")
        if req.actual_cost_usd is not None:
            vals.append(req.actual_cost_usd)
            sets.append(f"actual_cost_usd = ${len(vals)}")
            changed["actual_cost_usd"] = len(vals)
    if req.photo_url is not None:
        vals.append(req.photo_url)
        sets.append(f"photo_url = ${len(vals)}")
        changed["photo_url"] = len(vals)
    if req.notes is not None:
        vals.append(req.notes)
        sets.append(f"notes = ${len(vals)}")
        changed["notes"] = len(vals)
    if not sets:
        raise HTTPException(status_code=422, detail="لا حقول للتحديث")
    sets.append("updated_at = NOW()")
    differs = " OR ".join(
        [f"{col} IS DISTINCT FROM ${i}" for col, i in changed.items()] + stamp_differs
    )
    vals.append(task_id)
    where = f"task_id::TEXT = ${len(vals)}"
    if req.status is not None:
        vals.append(task_allowed_sources(req.status))
        where += f" AND COALESCE(status, 'pending') = ANY(${len(vals)}::text[])"
    query = (
        f"UPDATE field_tasks SET {', '.join(sets)} WHERE {where} AND ({differs}) "
        f"RETURNING {_TASK_COLS}, updated_at"
    )
    # إعادةٌ لا تغيّر الصفّ: لا كتابة ولا حدث، والنتيجة هي الصفّ كما هو.
    unchanged_query = f"SELECT {_TASK_COLS} FROM field_tasks WHERE {where} AND NOT ({differs})"
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
                        # قد تكون None عند تحديث photo/notes فقط (ملاحظة Copilot). updated_at
                        # بعد التحديث يميّز طفرتين حقيقيّتين في اليوم نفسه عن مفتاح الـdedup
                        # اليوميّ (C-14).
                        _task_updated_payload(row, sorted(changed)),
                    )
                    return _row_to_task(row, user).model_dump(mode="json")
                unchanged = await conn.fetchrow(unchanged_query, *vals)
                if unchanged is not None:
                    return _row_to_task(unchanged, user).model_dump(mode="json")
                # داخل المعاملة ⇒ لا يُسجَّل أمرٌ لمهمّةٍ غير موجودة ولا لانتقالٍ مرفوض.
                current = None
                if req.status is not None:
                    current = await conn.fetchrow(
                        "SELECT status FROM field_tasks WHERE task_id::TEXT = $1", task_id
                    )
                if current is not None:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "illegal_task_transition",
                            "from": current["status"] or "pending",
                            "to": req.status,
                        },
                    )
                raise HTTPException(status_code=404, detail="المهمّة غير موجودة ضمن هذا المستأجِر")

            if idem:
                new_absent = {
                    k for k in ("completed_at", "actual_cost_usd") if getattr(req, k) is None
                }
                digest = hashlib.sha256(
                    json.dumps(
                        # الحقلان الجديدان يُستبعَدان غائبَين فتبقى بصمةُ الطلبات القديمة كما هي.
                        {"task_id": task_id, **req.model_dump(mode="json", exclude=new_absent)},
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
        refused = _INSPECTION_CLOSE_REFUSALS.get(getattr(e, "sqlstate", None))
        if refused is not None:
            raise HTTPException(status_code=409, detail=refused) from e
        raise _db_unavailable("تحديث المهمّة", e) from e


# v277 (field-management-service's trigger on field_tasks): a pin inspection task closes only on an
# approved review of the pin's current photo evidence. The trigger refuses the UPDATE; the platform
# reads none of the inspection tables and only names the refusal (409, not a 503).
_INSPECTION_CLOSE_REFUSALS = {
    "SH001": {
        "error": "inspection_review_required",
        "message": "تتطلب زيارة التفتيش اعتماد نتيجتها قبل الإغلاق",
    },
    "SH002": {
        "error": "inspection_evidence_changed",
        "message": "تغيرت صورة الزيارة بعد الاعتماد. يلزم اعتماد النسخة الجديدة",
    },
}


def _task_updated_payload(row, changed_fields: list[str]) -> dict:
    updated_at = row.get("updated_at")
    return {
        "status": row.get("status"),
        "field_id": row.get("field_id"),
        "changed_fields": changed_fields,
        "updated_at": updated_at.isoformat() if updated_at is not None else None,
    }
