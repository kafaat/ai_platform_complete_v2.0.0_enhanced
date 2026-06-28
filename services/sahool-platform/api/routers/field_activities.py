"""api/routers/field_activities.py — مسارات الأنشطة والتتبّع (Activities & Traceability) للحقل.

شريحة مُستخرَجة من ``api/routers/fields.py`` (تفكيك تدريجيّ محفوظ-السلوك للملفّ الأكبر):
نُقلت المعالِجات الأربع للأنشطة والتتبّع حرفيّاً — بنفس المسارات/الطلبات/المخرجات/الأذونات/
مخطّط OpenAPI — دون أيّ تغيير في السلوك:

  • ``POST   /api/v1/fields/{field_id}/activities``           → ``create_activity``
  • ``GET    /api/v1/fields/{field_id}/activities``           → ``list_field_activities``
  • ``GET    /api/v1/fields/{field_id}/input-traceability``   → ``field_input_traceability``
  • ``POST   /api/v1/fields/{field_id}/growth-narrative``     → ``field_growth_narrative``

التسجيل تلقائيّ عبر ``api.router_registry.register_routers`` (حلقة ``pkgutil`` على
``api/routers/`` — أيّ وحدة تُصدّر ``router`` تُضمّ). بما أنّ المسارات نُقلت (لا نُسخت)
من ``fields.py`` فلا تكرار (مسار، طريقة).

الاعتماديّات: الرموز المشتركة تُستورَد من مصادرها الأصليّة نفسها كما في ``fields.py``
(``api.main`` للتبعيات/النماذج/المساعِدات؛ والمحرّكات النقيّة تُستورَد محليّاً داخل
الدوال كما كانت). لتفادي الاستيراد الدائريّ: ``api.main`` يُستورَد هنا، وحلقة التسجيل
تُنفَّذ في نهاية ``main.py`` بعد اكتمال تعريف كلّ تلك الرموز.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.main import (
    _ACTIVITY_TYPES,
    ActivityCreateRequest,
    ActivitySummary,
    CommandStore,
    GrowthNarrativeRequest,
    Permission,
    UserSchema,
    _activity_event_type,
    _assert_field_in_tenant,
    _clamp_list_window,
    _db_unavailable,
    _emit_domain_event,
    _idem_key,
    _idempotent,
    _parse_date,
    _row_to_activity,
    get_pool,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.post(
    "/api/v1/fields/{field_id}/activities",
    status_code=201,
    response_model=ActivitySummary,
)
async def create_activity(
    field_id: str,
    req: ActivityCreateRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يسجّل عمليّة زراعيّة للحقل — تُخزَّن فعليّاً ضمن سياق المستأجِر (RLS).

    يتحقّق من نوع العمليّة (422)، ويحوّل التواريخ (400)، ويؤكّد أنّ الحقل
    يخصّ المستأجِر (404) قبل الإدراج، ثمّ يردّ العمليّة المُنشأة. idempotent:
    Idempotency-Key (UUID) يمنع تكرار التسجيل عند إعادة الموبايل (offline).
    """
    import json as _json
    import uuid as _uuid

    if req.activity_type not in _ACTIVITY_TYPES:
        raise HTTPException(status_code=422, detail="نوع عمليّة غير معروف")
    scheduled = _parse_date(req.scheduled_for, "التاريخ المُجدوَل")
    performed = _parse_date(req.performed_on, "تاريخ التنفيذ")
    activity_id = "act_" + _uuid.uuid4().hex[:12]
    status = "done" if performed else "planned"
    try:
        details_json = _json.dumps(req.details or {})
    except (TypeError, ValueError) as e:
        # محتوى details غير قابل للتسلسل ⇒ خطأ إدخال صريح (422) لا 500/503.
        raise HTTPException(
            status_code=422, detail="تفاصيل العمليّة غير قابلة للتسلسل (JSON)"
        ) from e
    try:
        async with tenant_connection(user) as conn:

            async def _work():
                await _assert_field_in_tenant(conn, field_id)
                if req.season_id is not None:
                    # الموسم اختياريّ، لكن إن مُرّر فيجب أن يوجد ويخصّ الحقل نفسه
                    # (لا FK صلب على القاعدة؛ تحقّق تطبيقيّ + فهرس داعم — v45).
                    season_ok = await conn.fetchval(
                        "SELECT 1 FROM seasons WHERE season_id = $1 AND field_id = $2",
                        req.season_id,
                        field_id,
                    )
                    if season_ok is None:
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "message_ar": "الموسم غير موجود لهذا الحقل",
                                "code": "invalid_season_for_field",
                            },
                        )
                await conn.execute(
                    """INSERT INTO activities
                        (activity_id, tenant_id, field_id, season_id, activity_type,
                         title_ar, details, scheduled_for, performed_on, status)
                       VALUES ($1, $2::uuid, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)""",
                    activity_id,
                    str(user.tenant_id),
                    field_id,
                    req.season_id,
                    req.activity_type,
                    req.title_ar,
                    details_json,
                    scheduled,
                    performed,
                    status,
                )
                # حدث domain ضمن نفس معاملة تسجيل العمليّة (نمط outbox) — بحدث عمليّة
                # محدَّد (operation.*) حسب النوع/الحالة، وإلّا ACTIVITY_RECORDED العامّ.
                await _emit_domain_event(
                    conn,
                    user,
                    _activity_event_type(req.activity_type, status),
                    "activity",
                    activity_id,
                    {
                        "field_id": field_id,
                        "season_id": req.season_id,
                        "activity_type": req.activity_type,
                        "status": status,
                    },
                )
                # Canonical Field State: تسجيل عمليّة يغيّر سياق القرار ⇒ أعِد حساب
                # الإسقاط، وأصدِر field.state_changed إن تبدّلت صلاحيّة القرار/التنفيذ
                # (داخل _work ⇒ نفس معاملة الكتابة ومشمول بالـidempotency — نمط outbox).
                from api.field_state_projection import recompute_field_state

                _fs = await recompute_field_state(conn, field_id)
                if _fs["changed"]:
                    await _emit_domain_event(
                        conn,
                        user,
                        "FIELD_STATE_CHANGED",
                        "field",
                        field_id,
                        {
                            "validity": _fs["state"]["validity"],
                            "execution_mode": _fs["state"]["execution_mode"],
                            "trigger": "activity.recorded",
                        },
                    )
                # نُعيد JSON (model_dump) ليُخزَّن كنتيجة أمر idempotent ويُعاد حرفيّاً
                # عند الإعادة (مع حفظ activity_id الأصليّ) — response_model يتحقّق منه.
                return ActivitySummary(
                    activity_id=activity_id,
                    field_id=field_id,
                    season_id=req.season_id,
                    activity_type=req.activity_type,
                    title_ar=req.title_ar,
                    details=req.details or {},
                    scheduled_for=scheduled.isoformat() if scheduled else None,
                    performed_on=performed.isoformat() if performed else None,
                    status=status,
                ).model_dump()

            # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="activity.create",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"field_id": field_id, "activity_id": activity_id},
                )
            else:
                result = await _work()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ العمليّة", e) from e
    return result


@router.get("/api/v1/fields/{field_id}/activities", response_model=list[ActivitySummary])
async def list_field_activities(
    field_id: str,
    limit: int | None = Query(default=None, ge=1),
    offset: int | None = Query(default=None, ge=0),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """عمليّات الحقل (الأحدث أولاً) — مُرشَّحة بالمستأجِر (RLS). مُرقَّمة (limit/offset)
    بسقف أمان يمنع over-fetch على قائمة غير محدودة — الافتراضيّ أحدث 100. 503 عند تعذّر القاعدة."""
    lim, off = _clamp_list_window(limit, offset)
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)  # 404 لو الحقل ليس للمستأجِر
            rows = await conn.fetch(
                "SELECT activity_id, field_id, season_id, activity_type, title_ar, "
                "details, scheduled_for, performed_on, status, created_at "
                "FROM activities WHERE field_id = $1 ORDER BY created_at DESC "
                "LIMIT $2 OFFSET $3",
                field_id,
                lim,
                off,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة العمليّات", e) from e
    return [_row_to_activity(r) for r in rows]


@router.get("/api/v1/fields/{field_id}/input-traceability")
async def field_input_traceability(
    field_id: str,
    season_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تتبّع مدخلات الإنتاج (بذرة→حصاد) per حقل/موسم + الاقتصاد — يركّب القائم.

    يجمع تطبيقات المدخلات من activities (بذر/تسميد/رشّ/ريّ مع كلفة في details)
    ويربطها بناتج الحصاد من recommendation_outcomes ومساحة الحقل، فيبني دفتر
    مدخلات صادقاً: كلفة/هكتار، كلفة/طنّ، ومدى اكتمال النَسَب. الكلفة الغائبة
    تُعلَن لا تُؤلَّف. المخزون والشراء يبقيان في ERPNext (لا نقل WareMap).
    """
    from decimal import Decimal as _Decimal

    import asyncpg as _asyncpg
    from core.engines.input_traceability import (
        ACTIVITY_TO_INPUT,
        InputApplication,
        build_input_ledger,
    )

    _json = __import__("json")

    def _details(v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except (ValueError, TypeError):
                return {}
        return v or {}

    def _num(v):
        # يقبل int/float/Decimal (NUMERIC من asyncpg) — يرفض bool/None/نصّ.
        if isinstance(v, bool) or v is None:
            return None
        return float(v) if isinstance(v, (int, float, _Decimal)) else None

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)  # 404 لو ليس للمستأجِر
            area_ha = _num(
                await conn.fetchval("SELECT area_ha FROM fields WHERE field_id = $1", field_id)
            )

            q = (
                "SELECT activity_type, details, performed_on, scheduled_for FROM activities "
                "WHERE field_id = $1 AND activity_type = ANY($2::text[])"
            )
            params: list = [field_id, list(ACTIVITY_TO_INPUT.keys())]
            if season_id is not None:
                q += " AND season_id = $3"
                params.append(season_id)
            rows = await conn.fetch(q, *params)

            # ناتج الحصاد من recommendation_outcomes (savepoint — قد لا يكون مفعَّلاً).
            harvest_yield = None
            try:
                async with conn.transaction():
                    oq = (
                        "SELECT MAX(actual_yield_t_ha) AS y FROM recommendation_outcomes "
                        "WHERE field_id = $1 AND actual_yield_t_ha IS NOT NULL"
                    )
                    oparams: list = [field_id]
                    if season_id is not None:
                        oq += " AND season_id = $2"
                        oparams.append(season_id)
                    orow = await conn.fetchrow(oq, *oparams)
                    harvest_yield = _num(orow["y"]) if orow else None
            except (_asyncpg.UndefinedTableError, _asyncpg.UndefinedColumnError):
                harvest_yield = None
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تتبّع المدخلات", e) from e

    apps = []
    for r in rows:
        d = _details(r["details"])
        apps.append(
            InputApplication(
                activity_type=r["activity_type"],
                product_name=d.get("product_name") or d.get("product"),
                quantity=_num(d.get("quantity")),
                unit=d.get("unit"),
                cost=_num(d.get("cost")),
                applied_on=(
                    (r["performed_on"] or r["scheduled_for"]).isoformat()
                    if (r["performed_on"] or r["scheduled_for"])
                    else None
                ),
            )
        )
    return build_input_ledger(
        apps,
        field_id=field_id,
        season_id=season_id,
        area_ha=area_ha,
        harvest_yield_t_ha=harvest_yield,
    )


@router.post("/api/v1/fields/{field_id}/growth-narrative")
async def field_growth_narrative(
    field_id: str,
    req: GrowthNarrativeRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """سرد نموّ الحقل الفينولوجي من سلسلة NDVI القمريّة — بديل صادق للتايم‑لابس بلا عتاد.

    يصنّف الطور (إنبات/خضري/ذروة/شيخوخة) من شكل المنحنى، ويكشف شذوذ النموّ
    (ذروة ضعيفة/شيخوخة مبكّرة) **فقط مقابل مظروف متوقَّع مُمرَّر** — لا قيم أجنبيّة
    مُقحَمة. دون حدّ أدنى من المشاهد: لا سرد (لا لقطة تُقدَّم كمنحنى). 503 عند تعذّر
    القاعدة. السلسلة تُمرَّر في الطلب (من raster-service) — الجلب الحيّ بند تشغيليّ.
    """
    from core.engines.phenology_narrative import (
        NDVIObservation,
        build_growth_narrative,
    )

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)  # 404 لو ليس للمستأجِر
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("سرد النموّ", e) from e

    obs = [
        NDVIObservation(date=o.date, ndvi=o.ndvi, days_after_planting=o.days_after_planting)
        for o in req.observations
    ]
    result = build_growth_narrative(
        obs,
        crop=req.crop,
        peak_ndvi_floor=req.peak_ndvi_floor,
        expected_peak_dap_min=req.expected_peak_dap_min,
    )
    result["field_id"] = field_id
    return result
