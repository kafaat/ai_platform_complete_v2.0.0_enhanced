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
                task = await _apply()
                # G3 (F-D09): الإغلاق يقول هل سُجِّلت نتيجة — ضمن المعاملة نفسها (409 يُرجِعها).
                if req.status == "completed":
                    task.update(await _record_task_outcome(conn, user, task_id, req))
                return task

            async def _apply():
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
                    k
                    for k in (
                        "completed_at",
                        "actual_cost_usd",
                        "outcome_result",
                        "outcome_evidence_ref",
                    )
                    if getattr(req, k) is None
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
# reads none of the inspection tables and only names the refusal (409, not a 503). The other
# v275-v277 refusals and 23505 (two writers taking the same hand-off revision, e.g. a reopen racing
# a hand-off) are conflicts with the stored state too, never an unavailable database.
_INSPECTION_CLOSE_REFUSALS = {
    "SH001": {
        "error": "inspection_review_required",
        "message": "تتطلب زيارة التفتيش اعتماد نتيجتها قبل الإغلاق",
    },
    "SH002": {
        "error": "inspection_evidence_changed",
        "message": "تغيرت صورة الزيارة بعد الاعتماد. يلزم اعتماد النسخة الجديدة",
    },
    "SH003": {
        "error": "inspection_pin_immutable",
        "message": "لا يمكن تغيير دبوس الرصد المرتبط بمهمة التفتيش",
    },
    "SH004": {
        "error": "inspection_revision_gap",
        "message": "تغيّر سجل التكليف. حدّث البيانات",
    },
    "SH005": {
        "error": "task_cost_history_trigger_only",
        "message": "سجل تكلفة المهمة يُكتب تلقائياً فقط",
    },
    "SH006": {
        "error": "inspection_handoff_chain_broken",
        "message": "لا يطابق سجل التكليف المستلم الحالي. حدّث البيانات",
    },
    "SH007": {
        "error": "inspection_self_review",
        "message": "لا يعتمد مقدّم النتيجة نتيجته",
    },
    "SH008": {
        "error": "inspection_task_closed",
        "message": "المهمة مغلقة. أعد فتحها قبل أي تكليف أو مراجعة",
    },
    "23505": {
        "error": "inspection_handoff_conflict",
        "message": "تغيّر سجل التكليف بالتزامن. حدّث البيانات",
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


# ── G3: أمر العمل ⇐ مهمّة الحقل ⇐ نتيجة منسوبة ──────────────────────────────────────
# راية واحدة مُطفأة افتراضاً تحكم الكتابتين الجديدتين: إنشاء المهمّة من أمر العمل (F-D06)
# وتسجيل النتيجة عند الإغلاق (F-D09). الرابط يُحفَظ في work_orders (جدول المنصّة):
# payload.field_task_id ثمّ payload.outcome — بجوار recommendation_id وpayload.decision_id.
# الاستيرادات كسولة داخل الدوالّ كي لا تنزاح مراسي أسطر النقاط أعلاه.
WORK_ORDER_FIELD_TASK_LINK_FLAG = "WORK_ORDER_FIELD_TASK_LINK_ENABLED"
_WORK_ORDER_COLS = (
    "work_order_id::text AS work_order_id, field_id, wo_type, status, recommendation_id, "
    "payload::text AS payload"
)


def work_order_field_task_link_enabled() -> bool:
    import os

    value = os.getenv(WORK_ORDER_FIELD_TASK_LINK_FLAG, "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _work_order_dict(row) -> dict:
    return {**dict(row), "payload": json.loads(row["payload"] or "{}")}


async def create_field_task_from_work_order(user: UserSchema, work_order_id: str) -> dict:
    """F-D06: مهمّة حقل واحدة لكلّ أمر عمل — صريحة، معزولة بالمستأجِر، لا تتكرّر.

    الراية مُطفأة ⇒ لا كتابة (``reason="disabled"``). أمر عمل لمستأجِر آخر أو غير موجود ⇒
    404 (RLS). أمر عمل مغلق (done/verified/cancelled) ⇒ 409. أمر عمل مربوط بمهمّة ⇒ تُعاد
    المهمّة نفسها (``replayed``). قفل الصفّ (FOR UPDATE) يُسلسِل الطلبين المتزامنين فلا
    تُنشأ مهمّتان. لا يُغيّر حالة أمر العمل ولا يُنفّذ شيئاً.
    """
    from core.work_order_from_recommendation import work_order_to_field_task

    from api.main import _assert_field_in_tenant

    answer = {"requested": True, "created": False, "replayed": False, "task_id": None}
    if not work_order_field_task_link_enabled():
        return {**answer, "reason": "disabled"}
    async with tenant_connection(user) as conn:
        row = await conn.fetchrow(
            f"SELECT {_WORK_ORDER_COLS} FROM work_orders WHERE work_order_id::text = $1 FOR UPDATE",
            str(work_order_id),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="أمر العمل غير موجود ضمن هذا المستأجِر")
        wo = _work_order_dict(row)
        linked = wo["payload"].get("field_task_id")
        if linked:
            return {**answer, "replayed": True, "task_id": str(linked), "reason": "already_linked"}
        draft = work_order_to_field_task(wo)
        if draft is None:
            raise HTTPException(
                status_code=409, detail={"error": "work_order_closed", "status": wo["status"]}
            )
        await _assert_field_in_tenant(conn, draft["field_id"])
        task_id = await conn.fetchval(
            """INSERT INTO field_tasks
                   (tenant_id, field_id, task_type, status, source_event_type, source_agent)
               VALUES ($1::uuid, $2, $3, $4, $5, $6)
               RETURNING task_id::text""",
            str(user.tenant_id),
            draft["field_id"],
            draft["task_type"],
            draft["status"],
            draft["source_event_type"],
            draft["source_agent"],
        )
        await conn.execute(
            "UPDATE work_orders SET payload = COALESCE(payload, '{}'::jsonb) "
            "|| jsonb_build_object('field_task_id', $2::text), updated_at = NOW() "
            "WHERE work_order_id::text = $1",
            wo["work_order_id"],
            task_id,
        )
        await _emit_domain_event(
            conn,
            user,
            "TASK_CREATED",
            "task",
            task_id,
            {
                "field_id": draft["field_id"],
                "source": "work_order",
                "work_order_id": wo["work_order_id"],
                "recommendation_id": wo["recommendation_id"],
                "decision_id": wo["payload"].get("decision_id"),
            },
        )
    return {**answer, "created": True, "task_id": task_id, "reason": "created"}


async def _record_task_outcome(conn, user: UserSchema, task_id: str, req) -> dict:
    """F-D09: نتيجة منسوبة عند الإغلاق — فقط من نتيجة صريحة ومرجع دليلها.

    الإغلاق الإداريّ (بلا نتيجة) لا يُسجّل شيئاً ولا يُقرأ تحقّقاً زراعيّاً. تُكتب النتيجة
    على أمر العمل الذي أنتج المهمّة (``payload.outcome``) حاملةً recommendation_id
    وdecision_id، و``verified=false``؛ حالة أمر العمل لا تُمسّ. الإعادة بالنتيجة نفسها ⇒
    ``already_recorded``؛ نتيجة مختلفة لنتيجة قائمة ⇒ 409 (لا كتابة فوقها).
    """
    from datetime import UTC, datetime

    from core.work_order_from_recommendation import build_work_order_outcome

    def answer(recorded: bool, reason: str) -> dict:
        return {"outcome_recorded": recorded, "outcome_reason": reason}

    if req.outcome_result is None:
        return answer(False, "no_result_supplied")
    if not work_order_field_task_link_enabled():
        return answer(False, "disabled")
    row = await conn.fetchrow(
        f"SELECT {_WORK_ORDER_COLS} FROM work_orders WHERE payload->>'field_task_id' = $1 "
        "ORDER BY created_at ASC LIMIT 1 FOR UPDATE",
        str(task_id),
    )
    if row is None:
        return answer(False, "no_linked_work_order")
    wo = _work_order_dict(row)
    outcome = build_work_order_outcome(
        wo,
        task_id=task_id,
        result=req.outcome_result,
        evidence_ref=req.outcome_evidence_ref,
        recorded_by=str(user.user_id),
    )
    if outcome is None:
        return answer(False, "no_result_supplied")
    existing = wo["payload"].get("outcome")
    if existing:
        same = all(existing.get(k) == outcome[k] for k in ("result", "evidence_ref", "task_id"))
        if same:
            return answer(True, "already_recorded")
        raise HTTPException(
            status_code=409,
            detail={"error": "outcome_already_recorded", "work_order_id": wo["work_order_id"]},
        )
    outcome["recorded_at"] = datetime.now(UTC).isoformat()
    await conn.execute(
        "UPDATE work_orders SET payload = COALESCE(payload, '{}'::jsonb) "
        "|| jsonb_build_object('outcome', $2::jsonb), updated_at = NOW() "
        "WHERE work_order_id::text = $1",
        wo["work_order_id"],
        json.dumps(outcome, ensure_ascii=False),
    )
    return answer(True, "recorded")
