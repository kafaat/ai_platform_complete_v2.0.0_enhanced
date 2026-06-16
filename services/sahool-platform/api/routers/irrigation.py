"""api/routers/irrigation.py — الريّ (Valves / Schedules / Soil / Water Analysis)
==================================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ التسع حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
دوالّ ``api.soil_moisture_advisor`` تُستورَد مباشرةً من وحدتها (نُقل استيرادها هنا
لإزالة F401 من main بعد نقل دالّتيها). أحداث الصمّامات (_emit_domain_event) تُنقَل
حرفيّاً بأسماء EventType نفسها (لا تغيير). لتفادي الاستيراد الدائريّ: ``api.main``
يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.irrigation_models import (
    ScheduleRequest,
    ValveRequest,
    ValveStateRequest,
    _parse_time,
)
from api.main import (
    CommandStore,
    Permission,
    UserSchema,
    WaterAnalysisRequest,
    _emit_domain_event,
    _idem_key,
    _idempotent,
    get_current_user,
    get_pool,
    require_permission,
    tenant_connection,
)
from api.soil_moisture_advisor import (
    irrigation_guidance,
    list_soil_types,
)

router = APIRouter()


@router.post("/api/v1/irrigation/valves", status_code=201)
async def register_valve(
    req: ValveRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
):
    """يسجّل صمّام ريّ ضمن المستأجِر (RLS). idempotent: Idempotency-Key (UUID)
    يمنع تكرار التسجيل عند إعادة الموبايل (offline)."""
    import uuid as _uuid

    valve_id = "vlv_" + _uuid.uuid4().hex[:12]
    async with tenant_connection(user) as conn:

        async def _work():
            await conn.execute(
                """INSERT INTO irrigation_valves
                    (valve_id, tenant_id, name, field_id, device_id, valve_type, flow_rate_lpm)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7)""",
                valve_id,
                str(user.tenant_id),
                req.name,
                req.field_id,
                req.device_id,
                req.valve_type,
                req.flow_rate_lpm,
            )
            # حدث تسجيل الصمّام ضمن نفس المعاملة (نمط outbox) — يُغلق فجوة «كتابة بلا
            # حدث» فيصبح دورة حياة الصمّام مرئيّة لتيّار الأحداث/الوكلاء. داخل _work
            # كي يُحفظ ضمن حدود idempotent ويُعاد ذرّيّاً مع الكتابة.
            await _emit_domain_event(
                conn,
                user,
                "IRRIGATION_VALVE_REGISTERED",
                "irrigation_valve",
                valve_id,
                {"field_id": req.field_id, "valve_type": req.valve_type},
            )
            # نُعيد النتيجة لتُخزَّن كنتيجة أمر idempotent وتُعاد حرفيّاً عند الإعادة
            # (مع حفظ valve_id الأصليّ).
            return {"valve_id": valve_id, "name": req.name, "message_ar": "سُجّل الصمّام"}

        # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
        if idem:
            result = await _idempotent(
                CommandStore(get_pool(), conn=conn),
                idem,
                _work,
                command_type="valve.register",
                actor_id=str(user.user_id),
                tenant_id=str(user.tenant_id),
                payload={"valve_id": valve_id, "field_id": req.field_id},
            )
        else:
            result = await _work()
    return result


@router.get("/api/v1/irrigation/valves")
async def list_valves(user: UserSchema = Depends(require_permission(Permission.IRRIGATION_VIEW))):
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT valve_id, name, field_id, device_id, valve_type, status, flow_rate_lpm, "
            "last_changed_at FROM irrigation_valves ORDER BY name"
        )
    return [
        {
            "valve_id": r["valve_id"],
            "name": r["name"],
            "field_id": r["field_id"],
            "device_id": r["device_id"],
            "valve_type": r["valve_type"],
            "status": r["status"],
            "flow_rate_lpm": float(r["flow_rate_lpm"]) if r["flow_rate_lpm"] is not None else None,
            "last_changed_at": r["last_changed_at"].isoformat() if r["last_changed_at"] else None,
        }
        for r in rows
    ]


@router.post("/api/v1/irrigation/valves/{valve_id}/state")
async def set_valve_state(
    valve_id: str,
    req: ValveStateRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
):
    """يسجّل نيّة فتح/إغلاق الصمّام + الحالة. التشغيل الفيزيائي الفعلي يمرّ عبر
    actuator-service/automation مع موافقة بشريّة (HIL) — هذه النقطة لا تُشغّل
    العتاد مباشرةً (مبدأ: لا تشغيل آليّ بلا ضابط). idempotent: Idempotency-Key
    (UUID) يمنع تكرار أمر التشغيل عند إعادة الموبايل (offline)."""
    async with tenant_connection(user) as conn:

        async def _work():
            updated = await conn.fetchval(
                "UPDATE irrigation_valves SET status = $1, last_changed_at = NOW() "
                "WHERE valve_id = $2 RETURNING valve_id",
                req.status,
                valve_id,
            )
            if not updated:
                # 404 داخل _work ⇒ يرتدّ إدراج الأمر معه (لا أمر «ناجح» يتيم على صمّام
                # غير موجود)، فإعادة لاحقة بعد إنشاء الصمّام تُنفَّذ من جديد بأمان.
                raise HTTPException(status_code=404, detail="الصمّام غير موجود")
            # حدث تغيّر حالة الصمّام ضمن نفس المعاملة (نمط outbox) — يجعل دورة فتح/إغلاق
            # مرئيّة لتيّار الأحداث/الوكلاء (الحالة الجديدة في الحمولة، حقائق فقط). داخل
            # _work كي يُحفظ ضمن حدود idempotent ويُعاد ذرّيّاً مع الكتابة.
            await _emit_domain_event(
                conn,
                user,
                "IRRIGATION_VALVE_STATE_CHANGED",
                "irrigation_valve",
                valve_id,
                {"status": req.status},
            )
            return {"valve_id": valve_id, "status": req.status, "message_ar": "سُجّلت حالة الصمّام"}

        # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
        if idem:
            result = await _idempotent(
                CommandStore(get_pool(), conn=conn),
                idem,
                _work,
                command_type="valve.set_state",
                actor_id=str(user.user_id),
                tenant_id=str(user.tenant_id),
                payload={"valve_id": valve_id, "status": req.status},
            )
        else:
            result = await _work()
    return result


@router.post("/api/v1/irrigation/schedules", status_code=201)
async def create_schedule(
    req: ScheduleRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
):
    import uuid as _uuid

    schedule_id = "sch_" + _uuid.uuid4().hex[:12]
    start = _parse_time(req.start_time)
    dows = req.days_of_week
    if dows is not None and any(d < 0 or d > 6 for d in dows):
        raise HTTPException(status_code=400, detail="days_of_week يجب أن تكون 0..6")
    async with tenant_connection(user) as conn:
        await conn.execute(
            """INSERT INTO irrigation_schedules
                (schedule_id, tenant_id, field_id, valve_id, name, start_time,
                 duration_min, days_of_week, water_target_mm, enabled)
               VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10)""",
            schedule_id,
            str(user.tenant_id),
            req.field_id,
            req.valve_id,
            req.name,
            start,
            req.duration_min,
            dows,
            req.water_target_mm,
            req.enabled,
        )
        # حدث إنشاء جدول الريّ (تفاعليّ): يبثّه وكيل الإشعارات. نفس المعاملة (outbox)؛
        # _emit_domain_event آمن (يبتلع أخطاءه) فلا يكسر النقطة.
        await _emit_domain_event(
            conn,
            user,
            "IRRIGATION_SCHEDULE_CREATED",
            "irrigation_schedule",
            schedule_id,
            {"field_id": req.field_id, "valve_id": req.valve_id},
        )
    return {"schedule_id": schedule_id, "name": req.name, "message_ar": "أُنشئ جدول الريّ"}


@router.get("/api/v1/irrigation/schedules")
async def list_schedules(
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_VIEW)),
):
    async with tenant_connection(user) as conn:
        if field_id:
            rows = await conn.fetch(
                "SELECT schedule_id, field_id, valve_id, name, start_time, duration_min, "
                "days_of_week, water_target_mm, enabled, last_run_at FROM irrigation_schedules "
                "WHERE field_id = $1 ORDER BY start_time",
                field_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT schedule_id, field_id, valve_id, name, start_time, duration_min, "
                "days_of_week, water_target_mm, enabled, last_run_at FROM irrigation_schedules "
                "ORDER BY start_time"
            )
    return [
        {
            "schedule_id": r["schedule_id"],
            "field_id": r["field_id"],
            "valve_id": r["valve_id"],
            "name": r["name"],
            "start_time": r["start_time"].isoformat() if r["start_time"] else None,
            "duration_min": r["duration_min"],
            "days_of_week": (list(r["days_of_week"]) if r["days_of_week"] is not None else None),
            "water_target_mm": (
                float(r["water_target_mm"]) if r["water_target_mm"] is not None else None
            ),
            "enabled": r["enabled"],
            "last_run_at": r["last_run_at"].isoformat() if r["last_run_at"] else None,
        }
        for r in rows
    ]


@router.delete("/api/v1/irrigation/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
):
    async with tenant_connection(user) as conn:
        deleted = await conn.fetchval(
            "DELETE FROM irrigation_schedules WHERE schedule_id = $1 RETURNING schedule_id",
            schedule_id,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="جدول الريّ غير موجود")
    return {"schedule_id": schedule_id, "message_ar": "حُذف جدول الريّ"}


@router.get("/api/v1/irrigation/soil-types")
def irrigation_soil_types_endpoint():
    """أنواع التربة وقيمها المرجعيّة (سعة حقليّة/نقطة ذبول)."""
    return list_soil_types()


@router.get("/api/v1/irrigation/moisture-decision")
def irrigation_moisture_decision_endpoint(
    vwc: float,
    soil_type: str = "loam",
    crop: str | None = None,
    growth_stage: str | None = None,
    theta_fc: float | None = None,
    theta_wp: float | None = None,
    root_depth_m: float | None = None,
):
    """قرار ريّ ذكي من قراءة مستشعر الرطوبة (VWC → RWC → قرار + كمّيّة).

    vwc: الرطوبة الحجميّة من المستشعر (0-1). soil_type: sand/loam/clay.
    theta_fc/theta_wp: قيم مُعايَرة ميدانيّاً (اختياري، الأدقّ).
    root_depth_m: عمق منطقة الجذور لحساب كمّيّة الريّ (اختياري).
    """
    return irrigation_guidance(vwc, soil_type, crop, growth_stage, theta_fc, theta_wp, root_depth_m)


@router.post("/api/v1/irrigation/water-analysis")
def irrigation_water_analysis(
    req: WaterAnalysisRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحلّل عيّنة ماء ريّ: SAR/RSC + تصنيف الملوحة/الصوديوم/القلويّة.

    صدق: يُعلِن المؤشّر غير المحسوب (نقص أيونات) صراحةً — لا تقدير مفبرَك.
    حسابيّ بحت (لا قاعدة)؛ التفويض مطلوب (سيادة الوصول)."""
    from core.irrigation_water_analysis import WaterSample, analyze_water_sample

    sample = WaterSample(**req.model_dump())
    return analyze_water_sample(sample)
