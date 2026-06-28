"""api/routers/field_seasons.py — مسارات المواسم الزراعيّة (Seasons) للحقل.

شريحة مُستخرَجة من ``api/routers/fields.py`` (تفكيك تدريجيّ محفوظ-السلوك للملفّ الأكبر):
نُقلت المعالِجات الثلاث للمواسم حرفيّاً — بنفس المسارات/الطلبات/المخرجات/الأذونات/مخطّط
OpenAPI — دون أيّ تغيير في السلوك:

  • ``POST   /api/v1/fields/{field_id}/seasons``                 → ``create_season``
  • ``GET    /api/v1/fields/{field_id}/seasons``                 → ``list_seasons``
  • ``PATCH  /api/v1/fields/{field_id}/seasons/{season_id}``     → ``update_season``

التسجيل تلقائيّ عبر ``api.router_registry.register_routers`` (حلقة ``pkgutil`` على
``api/routers/`` — أيّ وحدة تُصدّر ``router`` تُضمّ). بما أنّ المسارات نُقلت (لا نُسخت)
من ``fields.py`` فلا تكرار (مسار، طريقة).

الاعتماديّات: الرموز المشتركة تُستورَد من مصادرها الأصليّة نفسها كما في ``fields.py``
(``api.main`` للتبعيات/المساعِدات، ``api.season_models`` لنماذج/مساعِدات المواسم).
لتفادي الاستيراد الدائريّ: ``api.main`` يُستورَد هنا، وحلقة التسجيل تُنفَّذ في نهاية
``main.py`` بعد اكتمال تعريف كلّ تلك الرموز.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    CommandStore,
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    _emit_domain_event,
    _idem_key,
    _idempotent,
    _parse_date,
    get_pool,
    require_permission,
    tenant_connection,
)

# نماذج/مساعدات المواسم — من api.season_models مباشرةً (نفس مصدر fields.py).
from api.season_models import (
    _IRRIGATION_TYPES,
    _SEASON_SELECT_COLS,
    SeasonCreateRequest,
    SeasonSummary,
    SeasonUpdateRequest,
    _row_to_season,
)

router = APIRouter()


@router.post(
    "/api/v1/fields/{field_id}/seasons",
    status_code=201,
    response_model=SeasonSummary,
)
async def create_season(
    field_id: str,
    req: SeasonCreateRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """ينشئ موسماً زراعيّاً للحقل — يُخزَّن فعليّاً (بدل /seasons المُبتلَع).

    يتحقّق من نوع الريّ وترتيب التواريخ، ويربط الموسم بالحقل ضمن سياق المستأجِر
    (RLS) بعد تأكيد أنّ الحقل يخصّه (404)، ويردّ الموسم المُنشأ. idempotent:
    Idempotency-Key (UUID) يمنع تكرار الإنشاء عند إعادة الموبايل (offline).
    """
    import json as _json
    import uuid as _uuid

    if req.irrigation_type and req.irrigation_type not in _IRRIGATION_TYPES:
        raise HTTPException(status_code=422, detail="نوع ريّ غير معروف")
    # التواريخ: تُحوَّل/تُتحقَّق (400 على صيغة غير صالحة) قبل القاعدة.
    land = _parse_date(req.land_leveling_date, "تسوية الأرض")
    plow = _parse_date(req.plowing_date, "الحراثة")
    sow = _parse_date(req.sowing_date, "البذار")
    end = _parse_date(req.season_end, "نهاية الموسم")
    if plow and land and plow < land:
        raise HTTPException(status_code=422, detail="تاريخ الحراثة قبل تسوية الأرض")
    if sow and plow and sow < plow:
        raise HTTPException(status_code=422, detail="تاريخ البذار قبل الحراثة")
    if end and sow and end < sow:
        raise HTTPException(status_code=422, detail="نهاية الموسم قبل البذار")
    season_id = "ssn_" + _uuid.uuid4().hex[:12]
    # تصفية المراحل الفارغة كليّاً (name/date/notes فارغة) — لا تلوّث JSONB
    # بمدخلات غير مفيدة (مرحلة أُضيفت ثمّ تُركت فارغة في الواجهة).
    clean_stages = [
        s for s in req.custom_stages if (s.name.strip() or s.date.strip() or s.notes.strip())
    ]
    stages_json = _json.dumps([s.model_dump() for s in clean_stages])
    crops_json = _json.dumps(req.crops)

    import asyncpg as _asyncpg  # لالتقاط سباق الموسم النشط (UniqueViolation → 409)

    try:
        async with tenant_connection(user) as conn:

            async def _work():
                await _assert_field_in_tenant(conn, field_id)
                # ثابت v44: حقل واحد ⇒ موسم نشط واحد على الأكثر. بدل رفض الإنشاء (409)،
                # نُغلق آليّاً أيّ موسم نشط سابق لهذا الحقل ثمّ نُدرج الجديد ضمن نفس
                # المعاملة — فيكون «إنشاء موسم» انتقالاً نظيفاً للموسم النشط. الفهرس
                # الفريد الجزئي (uq_seasons_one_active) هو الضمانة النهائيّة للثابت.
                async with conn.transaction():
                    closed = await conn.fetch(
                        "UPDATE seasons SET status = 'closed' "
                        "WHERE field_id = $1 AND status = 'active' RETURNING season_id",
                        field_id,
                    )
                    # حدث SEASON_CLOSED لكلّ موسم نشط أُغلق آليّاً (توسيع تغطية الأحداث).
                    for cr in closed:
                        await _emit_domain_event(
                            conn,
                            user,
                            "SEASON_CLOSED",
                            "season",
                            cr["season_id"],
                            {
                                "field_id": field_id,
                                "reason": "superseded_by_new_season",
                                "superseded_by": season_id,
                            },
                        )
                    await conn.execute(
                        """INSERT INTO seasons
                        (season_id, tenant_id, field_id, crops, cultivar, irrigation_type,
                         seed_rate_kg_ha, land_leveling_date, plowing_date, sowing_date,
                         season_end, stages, status,
                         target_yield_kg_ha, plant_density, row_spacing_cm, seed_variety_source,
                         maturity, tillage_type, actual_yield_kg_ha, notes_ar)
                       VALUES ($1, $2::uuid, $3, $4::jsonb, $5, $6, $7,
                               $8, $9, $10, $11, $12::jsonb, 'active',
                               $13, $14, $15, $16,
                               $17, $18, $19, $20)""",
                        season_id,
                        str(user.tenant_id),
                        field_id,
                        crops_json,
                        req.cultivar,
                        req.irrigation_type,
                        req.seed_rate_kg_ha,
                        land,
                        plow,
                        sow,
                        end,
                        stages_json,
                        req.target_yield_kg_ha,
                        req.plant_density,
                        req.row_spacing_cm,
                        req.seed_variety_source,
                        req.maturity,
                        req.tillage_type,
                        req.actual_yield_kg_ha,
                        req.notes_ar,
                    )
                    # حدث domain ضمن نفس معاملة إنشاء الموسم (نمط outbox).
                    await _emit_domain_event(
                        conn,
                        user,
                        "SEASON_CREATED",
                        "season",
                        season_id,
                        {
                            "field_id": field_id,
                            "crops": req.crops,
                            "cultivar": req.cultivar,
                            "irrigation_type": req.irrigation_type,
                            "sowing_date": req.sowing_date,
                        },
                    )
                    # Canonical Field State: إنشاء موسم يغيّر سياق القرار ⇒ أعِد حساب
                    # الإسقاط، وأصدِر field.state_changed إن تبدّلت صلاحيّة القرار/التنفيذ
                    # (تغذية حيّة لوكيل الإشعارات، نفس معاملة الكتابة — نمط outbox).
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
                                "trigger": "season.created",
                            },
                        )
                # نُعيد JSON (model_dump) ليُخزَّن كنتيجة أمر idempotent ويُعاد حرفيّاً
                # عند الإعادة (مع حفظ season_id الأصليّ) — response_model يتحقّق منه.
                return SeasonSummary(
                    season_id=season_id,
                    field_id=field_id,
                    crops=req.crops,
                    cultivar=req.cultivar,
                    irrigation_type=req.irrigation_type,
                    seed_rate_kg_ha=req.seed_rate_kg_ha,
                    land_leveling_date=land.isoformat() if land else None,
                    plowing_date=plow.isoformat() if plow else None,
                    sowing_date=sow.isoformat() if sow else None,
                    season_end=end.isoformat() if end else None,
                    stages=[s.model_dump() for s in clean_stages],  # نفس ما خُزّن (لا بناء)
                    status="active",
                    target_yield_kg_ha=req.target_yield_kg_ha,
                    plant_density=req.plant_density,
                    row_spacing_cm=req.row_spacing_cm,
                    seed_variety_source=req.seed_variety_source,
                    maturity=req.maturity,
                    tillage_type=req.tillage_type,
                    actual_yield_kg_ha=req.actual_yield_kg_ha,
                    notes_ar=req.notes_ar,
                ).model_dump()

            # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="season.create",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"field_id": field_id, "season_id": season_id},
                )
            else:
                result = await _work()
    except HTTPException:
        raise
    except _asyncpg.UniqueViolationError as e:
        # 409 فقط لانتهاك uq_seasons_one_active (سباق الموسم النشط)؛ أيّ تفرّد آخر
        # (أو قيد مستقبليّ) يسلك مسار 503 الموثّق بدل إخفائه كـactive_season_conflict.
        if getattr(e, "constraint_name", None) != "uq_seasons_one_active":
            raise _db_unavailable("حفظ الموسم", e) from e
        raise HTTPException(
            status_code=409,
            detail={
                "message_ar": "يوجد موسم نشط لهذا الحقل بالفعل (محاولة متزامنة) — أعد المحاولة.",
                "code": "active_season_conflict",
            },
        ) from e
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ الموسم", e) from e
    return result


@router.get("/api/v1/fields/{field_id}/seasons", response_model=list[SeasonSummary])
async def list_seasons(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مواسم الحقل (الأحدث أولاً) — مُرشَّحة بالمستأجِر (RLS). 503 عند تعذّر القاعدة."""
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)  # 404 لو الحقل ليس للمستأجِر
            rows = await conn.fetch(
                "SELECT season_id, field_id, crops, cultivar, irrigation_type, "
                "seed_rate_kg_ha, land_leveling_date, plowing_date, sowing_date, "
                "season_end, stages, status, created_at, "
                "target_yield_kg_ha, plant_density, row_spacing_cm, seed_variety_source, "
                "maturity, tillage_type, actual_yield_kg_ha, notes_ar, "
                "sim_yield_kg_ha, sim_biomass_kg_ha, sim_gdd_total, sim_lai_max, "
                "sim_water_mm, sim_ran_at "
                "FROM seasons WHERE field_id = $1 ORDER BY created_at DESC",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة المواسم", e) from e
    return [_row_to_season(r) for r in rows]


@router.patch("/api/v1/fields/{field_id}/seasons/{season_id}", response_model=SeasonSummary)
async def update_season(
    field_id: str,
    season_id: str,
    req: SeasonUpdateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يحدّث موسماً قائماً (تحديث جزئيّ) — يُصدِر SEASON_UPDATED (+SEASON_CLOSED عند الإغلاق).

    حالة الموسم تتغيّر بانتقال محقَّق فقط (season_lifecycle): planned→active/closed،
    active→closed، والمُغلَق نهائيّ (422 لغيره). تأكيد ملكيّة الحقل (404)؛ والموسم
    يخصّ الحقل (404). انتقال planned→active وهناك نشط ⇒ 409. 503 عند تعذّر القاعدة.
    """
    import asyncpg as _asyncpg

    from api.season_lifecycle import SeasonTransitionError, validate_status_transition

    if req.irrigation_type is not None and req.irrigation_type not in _IRRIGATION_TYPES:
        raise HTTPException(status_code=422, detail="نوع ريّ غير معروف")
    sow = _parse_date(req.sowing_date, "البذار") if req.sowing_date is not None else None
    end = _parse_date(req.season_end, "نهاية الموسم") if req.season_end is not None else None
    if end and sow and end < sow:
        raise HTTPException(status_code=422, detail="نهاية الموسم قبل البذار")

    # أعمدة قابلة للتحديث (column, value) — الحقول الممرَّرة فقط، JSONB مُعلَّم.
    fields_set = req.model_fields_set
    updates: list[tuple[str, object, bool]] = []  # (col, value, is_jsonb)
    if "crops" in fields_set:
        import json as _json

        updates.append(("crops", _json.dumps(req.crops or []), True))
    if "cultivar" in fields_set:
        updates.append(("cultivar", req.cultivar, False))
    if req.irrigation_type is not None:
        updates.append(("irrigation_type", req.irrigation_type, False))
    if "seed_rate_kg_ha" in fields_set:
        updates.append(("seed_rate_kg_ha", req.seed_rate_kg_ha, False))
    if req.sowing_date is not None:
        updates.append(("sowing_date", sow, False))
    if req.season_end is not None:
        updates.append(("season_end", end, False))
    for kpi in (
        "target_yield_kg_ha",
        "plant_density",
        "row_spacing_cm",
        "seed_variety_source",
        # حقول v52 الأغرونوميّة
        "maturity",
        "tillage_type",
        "actual_yield_kg_ha",
        "notes_ar",
    ):
        if kpi in fields_set:
            updates.append((kpi, getattr(req, kpi), False))

    if not updates and req.status is None:
        raise HTTPException(status_code=422, detail="لا حقول للتحديث")

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            async with conn.transaction():
                current = await conn.fetchrow(
                    "SELECT status, row_version FROM seasons "
                    "WHERE season_id = $1 AND field_id = $2 FOR UPDATE",
                    season_id,
                    field_id,
                )
                if current is None:
                    raise HTTPException(status_code=404, detail="الموسم غير موجود لهذا الحقل")

                # تزامن تفاؤليّ (v64): إن مرّر العميل base_version ولم يطابق الإصدار
                # الحاليّ ⇒ عُدِّل الموسم من جلسة أخرى منذ قراءته ⇒ 409 (لا فقد صامت).
                # الصفّ مقفول (FOR UPDATE) فالفحص خالٍ من السباق. الرفض قبل أيّ كتابة
                # أو إصدار حدث ⇒ المعاملة تتراجع نظيفةً. trg_seasons_row_version يرفع
                # row_version آليّاً على كلّ UPDATE فلا رفعَ يدويّ هنا.
                if req.base_version is not None and current["row_version"] != req.base_version:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "version_conflict",
                            "message_ar": (
                                "عُدِّل الموسم من جلسة أخرى منذ قراءتك — أعد المزامنة ثمّ طبّق تعديلك."
                            ),
                            "current_version": current["row_version"],
                            "your_base_version": req.base_version,
                        },
                    )

                status_changed = False
                if req.status is not None:
                    try:
                        status_changed = validate_status_transition(current["status"], req.status)
                    except SeasonTransitionError as te:
                        raise HTTPException(
                            status_code=te.http_status, detail=te.message_ar
                        ) from te
                    if status_changed:
                        updates.append(("status", req.status, False))

                if updates:
                    set_parts, params = [], []
                    for col, value, is_jsonb in updates:
                        params.append(value)
                        cast = "::jsonb" if is_jsonb else ""
                        set_parts.append(f"{col} = ${len(params)}{cast}")
                    params.extend([season_id, field_id])
                    await conn.execute(
                        f"UPDATE seasons SET {', '.join(set_parts)} "
                        f"WHERE season_id = ${len(params) - 1} AND field_id = ${len(params)}",
                        *params,
                    )

                # حدث التحديث + حدث الإغلاق المخصَّص عند الانتقال إلى closed.
                changed_fields = [c for c, _, _ in updates]
                await _emit_domain_event(
                    conn,
                    user,
                    "SEASON_UPDATED",
                    "season",
                    season_id,
                    {"field_id": field_id, "changed_fields": changed_fields},
                )
                if status_changed and req.status == "closed":
                    await _emit_domain_event(
                        conn,
                        user,
                        "SEASON_CLOSED",
                        "season",
                        season_id,
                        {"field_id": field_id, "reason": "explicit_update"},
                    )

                row = await conn.fetchrow(
                    f"SELECT {_SEASON_SELECT_COLS} FROM seasons WHERE season_id = $1",
                    season_id,
                )
    except HTTPException:
        raise
    except _asyncpg.UniqueViolationError as e:
        if getattr(e, "constraint_name", None) != "uq_seasons_one_active":
            raise _db_unavailable("تحديث الموسم", e) from e
        raise HTTPException(
            status_code=409,
            detail={
                "message_ar": "يوجد موسم نشط لهذا الحقل بالفعل — أغلقه قبل تفعيل آخر.",
                "code": "active_season_conflict",
            },
        ) from e
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("تحديث الموسم", e) from e
    return _row_to_season(row)
