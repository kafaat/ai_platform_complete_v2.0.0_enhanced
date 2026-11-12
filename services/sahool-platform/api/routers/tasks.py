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
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.api_models import SatelliteSource, TerrainSource, task_allowed_sources
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
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
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
    if req.status is not None:
        vals.append(req.status)
        sets.append(f"status = ${len(vals)}")
        if req.status == "completed" and req.completed_at is not None:
            vals.append(req.completed_at)
            sets.append(f"completed_at = ${len(vals)}")
        elif req.status == "completed":
            # SET يقرأ القيمَ القديمة: إنجازٌ مكرَّر يُبقي الختمَ الأوّل.
            sets.append(
                "completed_at = CASE WHEN status = 'completed' AND completed_at IS NOT NULL "
                "THEN completed_at ELSE NOW() END"
            )
        elif req.status in ("pending", "in_progress"):
            sets.append("completed_at = NULL")
        if req.actual_cost_usd is not None:
            vals.append(req.actual_cost_usd)
            sets.append(f"actual_cost_usd = ${len(vals)}")
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
    where = f"task_id::TEXT = ${len(vals)}"
    if req.status is not None:
        vals.append(task_allowed_sources(req.status))
        where += f" AND COALESCE(status, 'pending') = ANY(${len(vals)}::text[])"
    query = f"UPDATE field_tasks SET {', '.join(sets)} WHERE {where} RETURNING {_TASK_COLS}"
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
                    return _row_to_task(row, user).model_dump(mode="json")
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
        raise _db_unavailable("تحديث المهمّة", e) from e


class SatelliteLinkRequest(BaseModel):
    asset_id: int = Field(gt=0, le=9223372036854775807)
    task_id: UUID | None = None


# The same predicate drives selection and writes. A superseded product cannot
# be attached by replaying a stale picker result.
_PRODUCT_QUERY = """
    SELECT id::text AS asset_id, scene_id, acquisition_date::text, index_name,
           satellite, algorithm_version, geometry_revision
    FROM raster_assets
    WHERE field_id=$1 AND tenant_id=$2::uuid AND asset_status='ready'
      AND NULLIF(cog_uri, '') IS NOT NULL AND NULLIF(scene_id, '') IS NOT NULL
      AND NULLIF(index_name, '') IS NOT NULL AND acquisition_date IS NOT NULL
      AND (valid_pixel_ratio IS NULL OR valid_pixel_ratio > 0)
"""


@router.get("/api/v1/fields/{field_id}/task-imagery", response_model=list[SatelliteSource])
async def task_imagery(
    field_id: str,
    index: Annotated[str | None, Query(max_length=64)] = None,
    before_id: Annotated[int | None, Query(gt=0, le=9223372036854775807)] = None,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            _PRODUCT_QUERY
            + " AND ($3::bigint IS NULL OR id < $3) AND ($4::text IS NULL OR lower(index_name)=$4) ORDER BY id DESC LIMIT 100",
            field_id,
            user.tenant_id,
            before_id,
            index.strip().lower() if index else None,
        )
        return [dict(row) for row in rows]


@router.post("/api/v1/fields/{field_id}/task-imagery", response_model=TaskSummary)
async def link_task_imagery(
    field_id: str,
    req: SatelliteLinkRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    async with tenant_connection(user) as conn:
        asset = await conn.fetchrow(
            _PRODUCT_QUERY + " AND id=$3 FOR SHARE", field_id, user.tenant_id, req.asset_id
        )
        if not asset:
            raise HTTPException(404, "الأصل غير متاح لهذا الحقل")
        return await _attach_source(conn, user, field_id, req.task_id, dict(asset), terrain=False)


async def _attach_source(conn, user, field_id, task_id, snapshot, *, terrain):
    column, key = (
        ("terrain_sources", "source_key") if terrain else ("satellite_sources", "asset_id")
    )
    identity = snapshot[key]
    source = json.dumps([snapshot])
    created = False
    if task_id is None:
        task_id = uuid5(NAMESPACE_URL, f"sahool:scouting:{user.tenant_id}:{field_id}:{identity}")
        created = await conn.fetchval(
            f"""INSERT INTO field_tasks(task_id, tenant_id, field_id, task_type, {column})
               VALUES ($1,$2,$3,'scouting',$4::jsonb)
               ON CONFLICT (task_id) DO NOTHING RETURNING true""",
            task_id,
            user.tenant_id,
            field_id,
            source,
        )
    row = await conn.fetchrow(
        f"SELECT {_TASK_COLS} FROM field_tasks WHERE task_id=$1 AND tenant_id=$2 "
        "AND field_id=$3 FOR UPDATE",
        task_id,
        user.tenant_id,
        field_id,
    )
    if not row:
        raise HTTPException(404, "المهمة غير موجودة في هذا الحقل")
    task = _row_to_task(row, user)
    if not any(getattr(s, key) == snapshot[key] for s in getattr(task, column)):
        row = await conn.fetchrow(
            f"UPDATE field_tasks SET {column}={column} || $2::jsonb, "
            f"updated_at=now() WHERE task_id=$1 RETURNING {_TASK_COLS}",
            task_id,
            source,
        )
        task = _row_to_task(row, user)
    elif not created:
        return task
    await _emit_domain_event(
        conn,
        user,
        "TASK_CREATED" if created else "TASK_UPDATED",
        "task",
        str(task_id),
        {"field_id": field_id, key: snapshot[key]},
    )
    return task


class TerrainLinkRequest(BaseModel):
    source_key: str = Field(pattern=r"^terrain-[0-9a-f]{64}$")
    task_id: UUID | None = None


async def _current_terrain(conn, user, field_id):
    # v162 soil products use a distinct RLS setting from the platform tables.
    await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)", str(user.tenant_id))
    field = await conn.fetchrow(
        "SELECT elevation_m::float8, slope_pct::float8, aspect FROM fields "
        "WHERE field_id=$1 AND tenant_id=$2::uuid",
        field_id,
        user.tenant_id,
    )
    if not field:
        raise HTTPException(404, "الحقل غير متاح")
    snapshots = []
    if any(v is not None and v != "" for v in field.values()):
        snapshots.append({"kind": "field_record", **dict(field)})
    dem = await conn.fetchrow(
        """
        SELECT terrain_product_id AS product_id, geometry_hash,
               payload->>'dem_version' AS dem_version, payload->>'generated_at' AS generated_at,
               payload->>'algorithm_version' AS algorithm_version,
               payload #>> '{provenance,cell_size_m}' AS cell_size_m,
               (payload->'summaries')::text AS summaries
        FROM soil_terrain_products WHERE tenant_id=$1 AND field_id=$2
            AND product_type='terrain_derivatives'
            AND jsonb_typeof(payload->'summaries')='object' AND payload->'summaries' <> '{}'::jsonb
        ORDER BY updated_at DESC, terrain_product_id DESC LIMIT 1
    """,
        str(user.tenant_id),
        field_id,
    )
    if dem:
        snapshots.append(
            {"kind": "dem_product", **dict(dem), "summaries": json.loads(dem["summaries"])}
        )
    for snap in snapshots:
        raw = json.dumps([str(user.tenant_id), field_id, snap], sort_keys=True).encode()
        snap["source_key"] = "terrain-" + hashlib.sha256(raw).hexdigest()
    return [TerrainSource(**snap) for snap in snapshots]


@router.get("/api/v1/fields/{field_id}/task-terrain", response_model=list[TerrainSource])
async def task_terrain(
    field_id: str, user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW))
):
    async with tenant_connection(user) as conn:
        return await _current_terrain(conn, user, field_id)


@router.post("/api/v1/fields/{field_id}/task-terrain", response_model=TaskSummary)
async def link_task_terrain(
    field_id: str,
    req: TerrainLinkRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    async with tenant_connection(user) as conn:
        for source in await _current_terrain(conn, user, field_id):
            if source.source_key == req.source_key:
                return await _attach_source(
                    conn, user, field_id, req.task_id, source.model_dump(), terrain=True
                )
        raise HTTPException(409, "تغيّر مصدر التضاريس أو لم يعد متاحاً. حدّث القائمة.")
