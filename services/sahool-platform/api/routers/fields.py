"""api/routers/fields.py — نطاق الحقول (Fields)
===============================================================
الشريحة المتشابكة الأخيرة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/طلبات/مخرجات/أذونات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت معالِجات الحقول الثمان والثلاثون (CRUD + المواسم + العمليّات +
دورة الحياة + الدبابيس + التحقّق الهندسيّ …) حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات: ``_persist_field``،
``_emit_domain_event``، نماذج Pydantic للحقول/المواسم/العمليّات …) تبقى مُعرَّفة في
``api.main`` وتُستورَد من هنا — كي لا يُكسَر ``_rebuild_pydantic_models`` ولا ربط أوامر
FieldAggregate ولا استيرادات الاختبارات. الرموز التي صارت يتيمة في ``main`` بعد النقل
(لا مستخدِم لها هناك) تُستورَد هنا من وحداتها الحقيقيّة مباشرةً (إزالة F401).

لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد تعريف
كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

# validate_field_geometry يُستورَد من مصدره مباشرةً (كان main يعيد تصديره، لكنه صار
# يتيماً فيه بعد نقل _persist_field إلى هنا — تفكيك B1).
from api.alert_models import AlertEvaluateResponse
from api.field_geometry_save_guard import sanitize_boundary_metadata, validate_boundary_for_save

# نماذج/مساعدات الحقل نُقِلت إلى api.field_models (تفكيك B1 — نقل عنقوديّ) وتُستورَد
# من هناك مباشرةً؛ معالِج الحفظ _persist_field يُعرَّف محليّاً أدناه (مستهلِكه الوحيد).
from api.field_models import (
    _FIELD_DETAIL_SELECT,
    _MIN_FIELD_OVERLAP_M2,
    FieldCreateRequest,
    FieldDetail,
    FieldImportRequest,
    FieldSummary,
    FieldUpdateRequest,
    _build_field_update,
    _row_to_field_detail,
    _row_to_field_summary,
    _significant_overlaps,
)

# رموز صارت يتيمة في api.main بعد نقل المعالِجات — تُستورَد هنا من وحداتها الحقيقيّة
# مباشرةً (نفس الرموز التي كان main يستوردها) لإزالة تحذيرات F401 من main بعد النقل.
from api.field_timeline import assemble_timeline
from api.geospatial_integrity import validate_field_geometry
from api.gis_geometry_guard import geometry_metadata, guard_field_geometry

# بقيّة التبعيّات/النماذج/المساعِدات المشتركة تبقى في api.main وتُستورَد من هناك.
from api.main import (
    _ACTIVITY_TYPES,
    _DB_POOL,
    _SOIL_TEST_SELECT,
    ActivityCreateRequest,
    ActivitySummary,
    CommandStore,
    GeometryValidateRequest,
    GrowthNarrativeRequest,
    NitrogenRxRequest,
    Permission,
    PinCreateRequest,
    RotationRequest,
    SoilLabTestCreateRequest,
    SoilLabTestSummary,
    SoilLabTestUpdateRequest,
    TimelineRequest,
    TrueUpRequest,
    UserSchema,
    WalkPlanRequest,
    YieldEstimateRequest,
    ZoningRequest,
    _activity_event_type,
    _assert_field_in_tenant,
    _build_versioned_update,
    _build_walk_plan,
    _clamp_list_window,
    _db_unavailable,
    _emit_domain_event,
    _evaluate_field_alerts_persist,
    _field_season_context,
    _field_weather_context,
    _historical_rain_3d_mm,
    _idem_key,
    _idempotent,
    _issue_tags_from_event,
    _latest_soil_moisture,
    _load_recommendation_policy,
    _parse_date,
    _reverse_geocode,
    _row_to_activity,
    _row_to_soil_test,
    _rx_generator,
    _trueup_engine,
    get_current_user,
    get_pool,
    require_permission,
    tenant_connection,
)
from api.pivot_geometry import (
    PivotPolygonDriftError,
    maybe_canonicalize_pivot_geometry,
    resolve_pivot_update_geometry,
)
from api.prescriptions import ZoneCharacteristics, ZoneClass, prescription_to_dict
from api.scouting_pins import make_pin

# نماذج/مساعدات المواسم نُقِلت إلى api.season_models (تفكيك B1) وتُستورَد من هناك.
from api.season_models import (
    _IRRIGATION_TYPES,
    _SEASON_SELECT_COLS,
    SeasonCreateRequest,
    SeasonSummary,
    SeasonUpdateRequest,
    _row_to_season,
)
from api.spatial_sync import mark_raster_cache_stale, save_field_geometry_revision
from api.trueup import TrueUpInput, TrueUpStatus
from api.walk_plan_pdf import walk_plan_to_pdf_bytes
from api.yield_heuristics import LifecycleFeatures, detect_anomalies, estimate_yield
from api.zones_kmeans import ZoneCell, delineate_zones

router = APIRouter()


# ─── تفعيل الصور الحقيقيّة (Sentinel-2 عبر raster-service) ────────────────────
# عند إنشاء/تحديث حدّ حقل نُطلِق مساراً مُستهدَفاً للبيانات الحقيقيّة: بحث «أفضل مشهد»
# (raster GET /imagery/best عبر Element84) ثمّ معالجة COG لكلّ مؤشّر (raster POST
# /v1/fields/{id}/process-from-stac) → real_data=true في «المؤشّرات المكانيّة» فقط بعد
# قراءة COG حقيقيّ (لا محاكاة). نُشغّله عبر BackgroundTasks (بعد الالتزام، خارج معاملة
# المستأجِر) كي لا تُحبَس وصلة القاعدة طوال نداءات HTTP (حتى ٣٠ث). أفضل-جهد تامّ: فشل
# الأتمتة/raster لا يكسر إنشاء/تحديث الحقل (يُسجَّل تحذير، لا تلفيق).
async def _kick_imagery_processing(
    *, field_id: str, tenant_id: str, geometry: object, reason: str
) -> None:
    """يُطلِق المعالجة المُستهدَفة بعد إنشاء/تحديث حقل (BackgroundTasks، بعد الالتزام).

    يحسب bbox من الهندسة عبر حارس الهندسة ثمّ يستدعي trigger_field_imagery_processing
    (imagery/best + process-from-stac). معزول وأفضل-جهد: أيّ تعذّر يُبتلَع بصمت (لا يؤثّر
    على ردّ الكتابة). صدق: يعتمد raster-service الحقيقيّ؛ لا يُختلَق شيء عند تعذّره."""
    try:
        from api.imagery_automation import imagery_automation

        guarded = guard_field_geometry(geometry)
        res = await imagery_automation.trigger_field_imagery_processing(
            field_id=field_id,
            tenant_id=tenant_id,
            bbox=guarded.bbox,
            geometry=guarded.geometry,
            reason=reason,
        )
        # تشخيص: أظهِر نتيجة الإطلاق في docker logs بدل الصمت — يكشف سبب عدم ظهور NDVI
        # الحقيقيّ (queued / no_scene / missing_bands / error) دون الحاجة لتتبّع الراستر.
        status = (res or {}).get("status")
        if (res or {}).get("queued"):
            logging.info(
                "إطلاق معالجة صور الحقل %s (%s): %s · scene=%s",
                field_id,
                reason,
                status,
                (res or {}).get("scene_id"),
            )
        else:
            logging.warning(
                "لم تُطلَق معالجة صور الحقل %s (%s): %s · %s",
                field_id,
                reason,
                status,
                (res or {}).get("note_ar") or (res or {}).get("error"),
            )
    except Exception as e:  # noqa: BLE001 — أفضل-جهد
        logging.warning(
            "تعذّر إطلاق معالجة الصور المُستهدَفة للحقل %s (%s): %s",
            field_id,
            reason,
            type(e).__name__,
        )


# ─── جوهر إدراج حقل واحد ضمن معاملة قائمة (DRY) ───────────────────────────────
# مُستخرَج من _persist_field._work() ليُعاد استخدامه حرفيّاً في create_field
# (عبر _persist_field) وفي نقطتَي merge/split الذرّيّتين. يفترض أنّ المستدعي يُمرّر
# conn ضمن معاملة tenant_connection مفتوحة (RLS مضبوط)؛ يُدرج الصفّ ثمّ يُصدِر
# FIELD_CREATED + سجلّ الهندسة + إبطال الراستر + FIELD_GEOMETRY_CHANGED + إعادة حساب
# حالة الحقل + FIELD_STATE_CHANGED — نفس التسلسل والأعمدة تماماً (سلوك محفوظ). أيّ خطأ
# (مثلاً DELETE مصدر لاحق في الدمج) يُترَك ليتصاعد فتتراجع المعاملة كاملةً (لا ابتلاع).
async def _insert_field_within_tx(
    conn,
    user: UserSchema,
    *,
    field_id: str,
    name: str,
    crop: str | None,
    geometry: dict,
    area_ha: float,
    lat: float | None,
    lon: float | None,
    soil_type: str | None = None,
    manager: str | None = None,
    farm_id: str | None = None,
    gov: str | None = None,
    field_code: str | None = None,
    description: str | None = None,
    water_source: str | None = None,
    irrigation_type: str | None = None,
    ownership_type: str | None = None,
    country: str | None = None,
    region: str | None = None,
    reason: str = "field.created",
    extra_event_meta: dict | None = None,
    boundary_metadata: dict | None = None,
) -> dict:
    """يُدرج حقلاً واحداً ويُصدِر أحداثه ضمن معاملة قائمة، ويُرجِع FieldSummary (JSON).

    مصدر واحد للحقيقة لتسلسل «إدراج حقل»: يستدعيه _persist_field (المسار المرسوم/
    المستورَد) ونقطتا merge/split. لا I/O خارج conn (لا نداء HTTP، لا التزام/تراجع
    يدويّ) — المستدعي يملك معاملة tenant_connection. extra_event_meta يُدمَج في
    حمولة FIELD_CREATED (مثلاً merged_from / split_from) للتدقيق.
    """
    import json as _json

    await conn.execute(
        """INSERT INTO fields
            (field_id, tenant_id, farm_id, name, crop, soil_type, manager,
             area_ha, lat, lon, gov, geometry,
             field_code, description, water_source, irrigation_type, ownership_type,
             country, region)
           VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb,
             $13, $14, $15, $16, $17, $18, $19)""",
        field_id,
        str(user.tenant_id),
        farm_id,
        name,
        crop,
        soil_type,
        manager,
        area_ha,
        lat,
        lon,
        gov or region,  # المحافظة المكتشفة؛ خارج اليمن ⇒ NULL (لا تلفيق «البيضاء»)
        _json.dumps(geometry),
        field_code,
        description,
        water_source,
        irrigation_type,
        ownership_type,
        country,
        region,
    )
    # حدث domain ضمن نفس المعاملة (نمط outbox) — يُغلق فجوة «كتابة بلا حدث».
    _created_payload = {
        "name": name,
        "crop": crop,
        "area_ha": area_ha,
        "farm_id": farm_id,
        "soil_type": soil_type,
    }
    if boundary_metadata:
        _created_payload["boundary_metadata"] = boundary_metadata
    if extra_event_meta:
        _created_payload.update(extra_event_meta)
    await _emit_domain_event(
        conn,
        user,
        "FIELD_CREATED",
        "field",
        field_id,
        _created_payload,
    )
    # Geometry ledger + raster invalidation: أي حد جديد ينتج revision
    # ويعلّم طبقات raster/indicators أنها مبنية على هندسة محددة.
    rev = await save_field_geometry_revision(
        conn,
        tenant_id=str(user.tenant_id),
        field_id=field_id,
        geometry=geometry,
        changed_by=str(user.user_id),
        reason=reason,
        source="draw_or_import",
        metadata={
            **geometry_metadata(field_revision=1),
            **({"boundary_metadata": boundary_metadata} if boundary_metadata else {}),
        },
    )
    await mark_raster_cache_stale(
        conn,
        tenant_id=str(user.tenant_id),
        field_id=field_id,
        reason=reason,
        metadata={"geometry_revision": rev, "scope": ["tiles", "indices", "zones"]},
    )
    await _emit_domain_event(
        conn,
        user,
        "FIELD_GEOMETRY_CHANGED",
        "field",
        field_id,
        {"geometry_revision": rev, "reason": reason},
    )
    # Canonical Field State: إنشاء حقل يُنشئ سياق القرار ⇒ أعِد حساب الإسقاط،
    # وأصدِر field.state_changed إن تبدّلت صلاحيّة القرار/التنفيذ (نمط outbox).
    # Derived projection is best-effort during field creation: a field row is the
    # source of truth, while field_state is a read-model/projection.  Missing optional
    # projection columns or a partially-applied migration must not turn a valid field
    # INSERT into 503.  The projection is recomputed by later jobs/events once the
    # schema is complete.
    try:
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
                    "trigger": reason,
                },
            )
    except Exception as fs_err:  # noqa: BLE001 — projection must not break field create
        logging.warning(
            "تخطّي إسقاط حالة الحقل بعد إنشاء %s — سيُعاد حسابه لاحقاً: %s",
            field_id,
            type(fs_err).__name__,
        )
    # نُعيد JSON (model_dump mode=json) ليُخزَّن كنتيجة أمر idempotent ويُعاد حرفيّاً
    # عند الإعادة — response_model=FieldSummary يتحقّق منه.
    return FieldSummary(
        field_id=field_id,
        farm_id=farm_id or "",
        name_ar=name,
        crop=crop or "—",
        area_ha=area_ha,
        quality_grade="PENDING_LAB",
        health_summary_ar="حقل جديد — بانتظار قياسات",
        soil_type=soil_type,
        manager=manager,
        field_code=field_code,
        description=description,
        water_source=water_source,
        ownership_type=ownership_type,
        country=country,
        region=region,
        lat=lat,
        lon=lon,
        geometry=geometry,
    ).model_dump(mode="json")


# ─── معالِج حفظ الحقل المشترك (مرسوم/مستورَد) — نُقل من main.py (تفكيك B1) ──────
# مستهلِكه الوحيد هنا (create_field/import_field)؛ يستورد النماذج/المساعِدات النقيّة
# من api.field_models والبنية التحتيّة (الاتّصال/الحدث/الترميز الجغرافيّ) من api.main.
async def _persist_field(
    req: FieldCreateRequest, user: UserSchema, *, idem: str | None = None
) -> FieldSummary:
    """مسار التحقّق + الإدراج المشترك للحقل (مرسوم أو مستورَد).

    يتحقّق من الهندسة (CRS 4326، تقاطع ذاتي، مساحة معقولة، داخل اليمن) ويحسب
    المساحة + المركز منها، يكشف الدولة/الإقليم آليّاً إن لم يُرسَلا، ثمّ يُدرج
    ضمن سياق المستأجر (RLS). يردّ الحقل المُنشأ بهندسته. مصدر واحد للحقيقة
    يُعيد استخدامه create_field و import_field — لا تكرار للتحقّق/الإدراج.
    """
    import json as _json
    import uuid as _uuid

    import asyncpg  # لتضييق التقاط أخطاء PostGIS الغائب في فحص التداخل

    # Geometry Guard: كل حدود الحقول تدخل النظام كـPolygon canonical في EPSG:4326.
    # Pivot fields are canonicalized from center/radius/angles when the client sends
    # pivot metadata, so irrigation geometry and map polygon cannot drift apart.
    raw_payload = req.model_dump(mode="json")
    canonical_pivot = maybe_canonicalize_pivot_geometry(
        raw_payload, req.irrigation_type or req.water_source or None
    )
    raw_geometry = canonical_pivot or req.geometry
    try:
        guarded = guard_field_geometry(raw_geometry)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message_ar": "هندسة الحقل غير صالحة — صحّح الحدود وأعد المحاولة.",
                "code": "invalid_field_geometry",
                "issues": str(exc).split(","),
            },
        ) from exc
    geometry = guarded.geometry
    area_ha = round(guarded.area_ha, 2)
    try:
        boundary_quality = validate_boundary_for_save(geometry, area_ha=guarded.area_ha)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message_ar": "حدود الحقل غير قابلة للحفظ — بسّط الحدود أو صحّح الرسم.",
                "code": "field_boundary_save_guard",
                "issues": str(exc).split(","),
            },
        ) from exc
    boundary_metadata = sanitize_boundary_metadata(getattr(req, "boundary_metadata", None))
    if boundary_metadata:
        boundary_metadata.setdefault("vertices_after", boundary_quality["vertices"])
        boundary_metadata.setdefault("area_ha", boundary_quality["area_ha"])
    lat, lon = guarded.centroid
    # الكشف الآلي للدولة + الإقليم من مركز المضلّع (إن لم يُرسلهما العميل)
    country, region = req.country, req.region
    if country is None or region is None:
        auto_country, auto_region = _reverse_geocode(lat, lon)
        country = country or auto_country
        region = region or auto_region
    field_id = "fld_" + _uuid.uuid4().hex[:12]
    geom_json = _json.dumps(geometry)
    try:
        async with tenant_connection(user) as conn:

            async def _work():
                # التحقّق أنّ المزرعة المرتبطة موجودة وتخصّ المستأجِر الحالي (إن أُرسلت).
                # farm_id يبقى اختياريّاً (ملف تعريف تدريجي)؛ نتحقّق فقط عند توفّره.
                # RLS يحصر farms أصلاً — لكن نضيف الفحص الصريح (دفاع + خطأ واضح).
                if req.farm_id:
                    farm_ok = await conn.fetchrow(
                        "SELECT 1 FROM farms WHERE farm_id = $1 AND tenant_id = $2::uuid",
                        req.farm_id,
                        str(user.tenant_id),
                    )
                    if farm_ok is None:
                        raise HTTPException(
                            status_code=404,
                            detail={
                                "message_ar": "المزرعة غير موجودة أو ليست لك",
                                "code": "farm_not_found",
                            },
                        )
                # منع تكرار اسم الحقل داخل نفس المزرعة/المستأجر (تطبيع حالة الأحرف).
                dup = await conn.fetchrow(
                    "SELECT field_id FROM fields WHERE tenant_id = $1::uuid "
                    "AND farm_id IS NOT DISTINCT FROM $2 AND lower(name) = lower($3) LIMIT 1",
                    str(user.tenant_id),
                    req.farm_id,
                    req.name,
                )
                if dup is not None:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "message_ar": f"يوجد حقل بالاسم نفسه «{req.name}» في هذه المزرعة.",
                            "code": "duplicate_field_name",
                            "existing_field_id": dup["field_id"],
                        },
                    )
                # منع تداخل الهندسة مع حقول المستأجِر (ST_Intersects على عمود geom المفهرس
                # GiST — v43) — يكشف أيضاً «النسخ» الهندسيّة ولو اختلف الاسم. يتطلّب PostGIS؛
                # تدهور رشيق فقط عند غيابه (دالّة/نوع غير معرّف)؛ أيّ خطأ DB آخر ⇒ 503.
                try:
                    overlaps = await conn.fetch(
                        """
                        SELECT field_id, name,
                               ST_Area(ST_Intersection(
                                   ST_GeomFromGeoJSON($1), geom
                               )::geography) AS overlap_m2
                        FROM fields
                        WHERE tenant_id = $2::uuid AND geom IS NOT NULL
                          AND ST_Intersects(ST_GeomFromGeoJSON($1), geom)
                        ORDER BY overlap_m2 DESC NULLS LAST
                        LIMIT 5
                        """,
                        geom_json,
                        str(user.tenant_id),
                    )
                except (
                    asyncpg.UndefinedFunctionError,
                    asyncpg.UndefinedObjectError,
                    asyncpg.UndefinedColumnError,
                ) as ovl_err:
                    # PostGIS غير مُثبَّت (دوال/نوع geometry غير معرّفة) — تخطٍّ رشيق فقط هنا.
                    logging.warning("تخطّي فحص تداخل الحقول — PostGIS غير متاح: %s", ovl_err)
                    overlaps = []
                significant = _significant_overlaps(overlaps, _MIN_FIELD_OVERLAP_M2)
                if significant:
                    top = significant[0]
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "message_ar": (
                                f"حدود الحقل تتداخل مع «{top['name']}» "
                                f"(~{top['overlap_m2']:.0f} م²). صحّح الحدود."
                            ),
                            "code": "field_geometry_overlap",
                            "overlaps": [
                                {
                                    "field_id": o["field_id"],
                                    "name": o["name"],
                                    "overlap_m2": round(o["overlap_m2"] or 0.0, 1),
                                }
                                for o in significant
                            ],
                        },
                    )
                # جوهر الإدراج المشترك (INSERT + FIELD_CREATED + سجلّ الهندسة + إبطال
                # الراستر + FIELD_GEOMETRY_CHANGED + حالة الحقل) — مصدر واحد للحقيقة
                # يُعاد استخدامه في merge/split (سلوك محفوظ حرفيّاً).
                return await _insert_field_within_tx(
                    conn,
                    user,
                    field_id=field_id,
                    name=req.name,
                    crop=req.crop,
                    geometry=geometry,
                    area_ha=area_ha,
                    lat=lat,
                    lon=lon,
                    soil_type=req.soil_type,
                    manager=req.manager,
                    farm_id=req.farm_id,
                    gov=req.gov,
                    field_code=req.field_code,
                    description=req.description,
                    water_source=req.water_source,
                    irrigation_type=req.irrigation_type,
                    ownership_type=req.ownership_type,
                    country=country,
                    region=region,
                    reason="field.created",
                    boundary_metadata=boundary_metadata or None,
                )

            # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="field.create",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"field_id": field_id, "name": req.name},
                )
            else:
                result = await _work()
    except HTTPException:
        raise  # get_pool() يرفع 503 أصلاً
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 لا 500
        raise _db_unavailable("حفظ الحقل", e) from e

    # تفعيل الصور الحقيقيّة يُطلَق عبر BackgroundTasks من create_field/import_field (بعد
    # الالتزام، خارج معاملة المستأجِر) — لا نداء HTTP داخل هذه الدالّة (لا حبس وصلة DB).
    return result


@router.get("/api/v1/fields", response_model=list[FieldSummary])
async def list_fields(user: UserSchema = Depends(get_current_user)):
    """قائمة حقول المستأجر من القاعدة — للـHomeScreen/الخريطة.

    تُرشَّح بـtenant_id (دفاع عميق) + RLS، وتُرجع المركز + الهندسة (GeoJSON)
    لرسم المضلّع على الخريطة. عند تعذّر القاعدة ⇒ 503 صريح — لا بيانات وهميّة.
    """
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT field_id, farm_id, name, area_ha, crop, soil_type, manager, "
                "field_code, description, water_source, ownership_type, country, region, "
                "lat, lon, geometry "
                "FROM fields WHERE tenant_id = $1::uuid ORDER BY name",
                str(user.tenant_id),
            )
    except HTTPException:
        raise  # get_pool() يرفع 503 أصلاً — مرّره كما هو
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة الحقول", e) from e
    return [_row_to_field_summary(r) for r in rows]


@router.post("/api/v1/fields", status_code=201, response_model=FieldSummary)
async def create_field(
    req: FieldCreateRequest,
    background_tasks: BackgroundTasks,
    user: UserSchema = Depends(require_permission(Permission.FIELD_CREATE)),
    idem: str | None = Depends(_idem_key),
):
    """ينشئ حقلاً من مضلّع مرسوم — يُخزَّن فعليّاً في القاعدة (لا تلفيق).

    يتحقّق من الهندسة ويحسب المساحة + المركز، ثمّ يُدرج ضمن سياق المستأجر (RLS).
    يردّ الحقل المُنشأ بهندسته كي ترسمه الواجهة فوراً، ويُطلِق معالجة صور Sentinel المُستهدَفة
    (BackgroundTasks، بعد الردّ: imagery/best + process-from-stac) فتظهر بيانات NDVI الحقيقيّة.
    """
    result = await _persist_field(req, user, idem=idem)
    background_tasks.add_task(
        _kick_imagery_processing,
        field_id=result["field_id"],
        tenant_id=str(user.tenant_id),
        geometry=result["geometry"],
        reason="field.created",
    )
    return result


@router.post("/api/v1/fields/import", status_code=201, response_model=FieldSummary)
async def import_field(
    req: FieldImportRequest,
    background_tasks: BackgroundTasks,
    user: UserSchema = Depends(require_permission(Permission.FIELD_CREATE)),
    idem: str | None = Depends(_idem_key),
):
    """يستورد حدّ حقل من GeoJSON/KML/نقاط GPS → GeoJSON Polygon ثمّ يُخزّنه.

    يحلّل المصدر إلى Polygon (geo_import: نقيّ offline) ثمّ يعيد استخدام نفس
    مسار التحقّق + الإدراج كـcreate_field. خطأ التحليل ⇒ 400 (مدخل تالف)؛ هندسة
    غير صالحة ⇒ 422 (من المسار المشترك). لا تلفيق — الفشل يُعرَض بصدق.
    """
    from api import geo_import

    fmt = req.format
    try:
        if fmt == "geojson":
            if not req.content:
                raise ValueError("استيراد GeoJSON يتطلّب محتوى الملفّ (content).")
            geometry = geo_import.parse_geojson(req.content)
        elif fmt == "kml":
            if not req.content:
                raise ValueError("استيراد KML يتطلّب محتوى الملفّ (content).")
            geometry = geo_import.parse_kml(req.content)
        else:  # gps
            if not req.points:
                raise ValueError("استيراد GPS يتطلّب نقاطاً (points).")
            geometry = geo_import.points_to_polygon(req.points)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"message_ar": f"تعذّر تحليل ملفّ الاستيراد: {e}"},
        ) from e

    create_req = FieldCreateRequest(
        name=req.name,
        crop=req.crop,
        soil_type=req.soil_type,
        manager=req.manager,
        geometry=geometry,
        farm_id=req.farm_id,
        gov=req.gov,
        field_code=req.field_code,
        description=req.description,
        water_source=req.water_source,
        irrigation_type=req.irrigation_type,
        pivot=req.pivot,
        ownership_type=req.ownership_type,
        country=req.country,
        region=req.region,
        boundary_metadata=getattr(req, "boundary_metadata", None),
    )
    result = await _persist_field(create_req, user, idem=idem)
    background_tasks.add_task(
        _kick_imagery_processing,
        field_id=result["field_id"],
        tenant_id=str(user.tenant_id),
        geometry=result["geometry"],
        reason="field.created",
    )
    return result


class FieldImageryRefreshRequest(BaseModel):
    date: str | None = None


@router.post("/api/v1/fields/{field_id}/imagery/refresh")
async def refresh_field_imagery(
    field_id: str,
    req: FieldImageryRefreshRequest | None = None,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """Launch real Sentinel-2 imagery processing for a field on demand.

    No fabricated data: this endpoint only searches real STAC scenes and queues
    raster-service COG processing. If no scene/COG exists yet, it returns an honest
    queued=false/no_scene/missing_bands response; raster endpoints expose real_data=true
    only after reading a real generated COG.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT field_id, geometry FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                field_id,
                str(user.tenant_id),
            )
            if row is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            geometry = row["geometry"]
            if isinstance(geometry, str):
                import json as _json

                geometry = _json.loads(geometry)
            guarded = guard_field_geometry(geometry)
            from api.imagery_automation import imagery_automation

            result = await imagery_automation.trigger_field_imagery_processing(
                field_id=field_id,
                tenant_id=str(user.tenant_id),
                bbox=guarded.bbox,
                geometry=guarded.geometry,
                reason="manual.refresh",
                date=(req.date[:10] if req and req.date else None),
            )
            await _emit_domain_event(
                conn,
                user,
                "FIELD_IMAGERY_REFRESH_REQUESTED",
                "field",
                field_id,
                {"status": result.get("status"), "queued": result.get("queued")},
            )
            return result
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تحديث صور الأقمار للحقل", e) from e


@router.get("/api/v1/fields/{field_id}/available-dates")
async def field_imagery_available_dates(
    field_id: str,
    index: str | None = Query(None),
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """Proxy tenant-verified imagery dates from raster-service for MapHub.

    The frontend already calls the platform API. Without this route, the scene
    selector silently stays empty and all map tiles keep using latest.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT field_id FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                field_id,
                str(user.tenant_id),
            )
            if row is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
        import os as _os

        import httpx as _httpx

        raster_url = _os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip(
            "/"
        )
        headers = {
            "X-Agent-Token": _os.getenv("SAHOOL_AGENT_TOKEN", ""),
            "X-Tenant-Id": str(user.tenant_id),
        }
        params = {"index": index} if index else {}
        async with _httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{raster_url}/v1/fields/{field_id}/available-dates",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تواريخ صور الأقمار للحقل", e) from e


class FieldImageryBackfillProxyRequest(BaseModel):
    """Tenant-scoped platform proxy contract for raster historical imagery backfill.

    The browser must not receive ``X-Agent-Token``. The platform verifies field
    ownership, injects service credentials, and forwards this bounded payload to
    raster-service.
    """

    preset: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    months: int | None = Field(default=None, ge=1, le=60)
    indices: list[str] | None = None
    max_cloud_pct: float | None = Field(default=None, ge=0, le=100)
    limit_per_month: int | None = Field(default=None, ge=1, le=10)
    apply_cloud_mask: bool | None = None
    clip_polygon_geojson: dict | None = None
    dry_run: bool | None = False


@router.post("/api/v1/fields/{field_id}/imagery/backfill")
async def field_imagery_backfill_proxy(
    field_id: str,
    req: FieldImageryBackfillProxyRequest,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """Start tenant-verified 24m/3y/5y imagery backfill through platform.

    This closes the security gap where MapHub called raster-service directly.
    The frontend remains bearer-authenticated against sahool-platform; only this
    server-side route injects ``X-Agent-Token`` and tenant headers for raster.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT field_id, geometry FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                field_id,
                str(user.tenant_id),
            )
            if row is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")

            # If the UI did not provide a clip polygon, use the canonical field boundary.
            payload = req.model_dump(exclude_none=True)
            if not payload.get("clip_polygon_geojson"):
                geometry = row["geometry"]
                if isinstance(geometry, str):
                    import json as _json

                    geometry = _json.loads(geometry)
                guarded = guard_field_geometry(geometry)
                payload["clip_polygon_geojson"] = guarded.geometry

            import os as _os

            import httpx as _httpx

            raster_url = _os.getenv(
                "RASTER_SERVICE_URL", "http://sahool-raster-service:8001"
            ).rstrip("/")
            headers = {
                "X-Agent-Token": _os.getenv("SAHOOL_AGENT_TOKEN", ""),
                "X-Tenant-Id": str(user.tenant_id),
            }
            try:
                async with _httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        f"{raster_url}/v1/fields/{field_id}/imagery/backfill",
                        json=payload,
                        headers=headers,
                    )
            except _httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502, detail=f"raster-service غير متاح: {exc}"
                ) from exc
            if resp.status_code >= 400:
                try:
                    detail = resp.json()
                except Exception:  # noqa: BLE001
                    detail = resp.text
                raise HTTPException(status_code=resp.status_code, detail=detail)

            result = resp.json()
            await _emit_domain_event(
                conn,
                user,
                "FIELD_IMAGERY_BACKFILL_REQUESTED",
                "field",
                field_id,
                {
                    "preset": payload.get("preset"),
                    "months": payload.get("months"),
                    "indices": payload.get("indices"),
                    "dry_run": bool(payload.get("dry_run")),
                    "jobs_scheduled": result.get("jobs_scheduled") or result.get("jobs_created"),
                },
            )
            return result
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تشغيل backfill التاريخي لصور الحقل", e) from e


@router.get("/api/v1/fields/{field_id}", response_model=FieldDetail)
async def get_field(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تفاصيل حقل كاملة (لوحة التفاصيل) — الأساسيّات + الأعمدة المتقدّمة (v37).

    مُرشَّحة بالمستأجِر (RLS). 404 لو الحقل ليس للمستأجِر، 503 عند تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                f"SELECT {_FIELD_DETAIL_SELECT} FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                field_id,
                str(user.tenant_id),
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة تفاصيل الحقل", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
    return _row_to_field_detail(row)


@router.get("/api/v1/fields/{field_id}/terrain")
async def get_field_terrain(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تفسير تضاريسيّ للحقل (ارتفاع/منحدر/اتّجاه → دلالة زراعيّة) — طبقة استرشاد/عرض.

    يقرأ أعمدة التضاريس (v37) ويُرجِع enrich_terrain: تدريج/انجراف/صقيع/تعرّض
    شمسي/صرف. يعمل فوراً على القيم المخزّنة (يدويّة أو من DEM). صادق عند غيابها.

    ⚠ التعبئة التلقائيّة من DEM (SRTM/Copernicus) بند مؤجَّل (POST_DEPLOYMENT_ROADMAP):
    تحتاج مزوّد DEM حيّاً غير مضبوط هنا — حتى ذلك تُملأ يدويّاً عبر
    PATCH /api/v1/fields/{field_id}.
    """
    from core.engines.dem_enrichment import enrich_terrain

    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT elevation_m, slope_pct, aspect FROM fields WHERE field_id = $1",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة تضاريس الحقل", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")

    result = enrich_terrain(
        elevation_m=float(row["elevation_m"]) if row["elevation_m"] is not None else None,
        slope_pct=float(row["slope_pct"]) if row["slope_pct"] is not None else None,
        aspect=row["aspect"],
    )
    result["field_id"] = field_id
    result["dem_auto_fill"] = {
        "available": False,
        "note_ar": (
            "التعبئة التلقائيّة من DEM مؤجَّلة (تحتاج مزوّد SRTM/Copernicus حيّاً). "
            "حتى ذلك: أدخِل elevation_m/slope_pct/aspect عبر "
            "PATCH /api/v1/fields/{field_id}، والتفسير أعلاه يعمل فوراً على القيم المخزّنة."
        ),
    }
    return result


@router.get("/api/v1/fields/{field_id}/workspace")
async def get_field_workspace(
    field_id: str,
    timeline_limit: int = 50,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مساحة عمل الحقل: ملخّص + طبقات قابلة للتبديل + خطّ زمنيّ (عرض صرف).

    مستلهَمة من نمط FieldView/John Deere (الخريطة محور + طبقات + خطّ زمنيّ) بنمط
    سهول الصادق: كلّ طبقة تُعلن توفّرها (متاحة/عند الطلب/غير متوفّرة)، والخطّ الزمنيّ
    من أحداث مسجّلة فقط (لا اختراع). 404 لو الحقل ليس للمستأجِر، 503 عند تعذّر القاعدة.
    """
    from core.engines.dem_enrichment import enrich_terrain
    from core.engines.field_workspace import assemble_workspace

    events: list[dict] = []
    try:
        async with tenant_connection(user) as conn:
            field = await conn.fetchrow(
                "SELECT field_id, name, crop, area_ha, soil_type, elevation_m, slope_pct, "
                "aspect, water_ec, irrigation_type FROM fields WHERE field_id = $1",
                field_id,
            )
            if field is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            rows = await conn.fetch(
                """SELECT event_type, occurred_at FROM events
                   WHERE entity_type = 'field' AND entity_id = $1
                   ORDER BY occurred_at DESC LIMIT $2""",
                field_id,
                max(1, min(timeline_limit, 500)),
            )
            events = [
                {
                    "event_type": r["event_type"],
                    "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else "",
                }
                for r in rows
            ]
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("مساحة عمل الحقل", e) from e

    field_d = dict(field)
    terrain = enrich_terrain(
        elevation_m=float(field_d["elevation_m"])
        if field_d.get("elevation_m") is not None
        else None,
        slope_pct=float(field_d["slope_pct"]) if field_d.get("slope_pct") is not None else None,
        aspect=field_d.get("aspect"),
    )
    return assemble_workspace(field_d, terrain, events)


def _conflict_changed_fields(client_changes: dict, server_record: dict) -> list[str]:
    """الحقول التي حاول العميل تغييرها وتختلف عن قيمة الخادم الحاليّة (لحلّ التعارض).

    دالّة نقيّة: تُقارن ما أرسله العميل بما في سجلّ الخادم — المفاتيح المشتركة فقط
    (تُقارَن في نفس وضع التسلسُل). تُغذّي Conflict Resolution Workflow في الواجهة.
    """
    return [k for k, v in client_changes.items() if k in server_record and server_record[k] != v]


def _field_merge_plan(
    client_changes: dict, server_record: dict, base_values: dict | None
) -> tuple[bool, list[str]]:
    """خطّة دمج 3-way لتعارض تحديث الحقل (دالّة نقيّة، Level 3).

    لكلّ عمود غيّره العميل: إن طابق الخادمُ نيّةَ العميل (server == new) ⇒ لا-عمل؛
    وإلّا إن طابق الخادمُ أساسَ العميل (server == base) ⇒ آمن للدمج (الطرف الآخر لم
    يمسّ العمود)؛ وإلّا ⇒ تعارض حقيقيّ (غيّر الطرفان العمود نفسه، أو لا أساس لتحديد
    الأمان ⇒ fail-closed). يُرجِع (can_auto_merge, conflict_fields). الدمج الآليّ
    ممكن فقط حين تُتاح base_values ولا تعارض حقيقيّ.
    """
    conflicts: list[str] = []
    for col, new_val in client_changes.items():
        if col not in server_record:
            continue
        srv = server_record[col]
        if srv == new_val:
            continue  # الخادم == نيّة العميل (لا-عمل)
        if base_values is not None and col in base_values and srv == base_values[col]:
            continue  # الخادم لم يتغيّر عن أساس العميل ⇒ آمن للدمج
        conflicts.append(col)
    return (bool(base_values) and not conflicts), conflicts


@router.put("/api/v1/fields/{field_id}", response_model=FieldDetail)
@router.patch("/api/v1/fields/{field_id}", response_model=FieldDetail)
async def update_field(
    field_id: str,
    req: FieldUpdateRequest,
    background_tasks: BackgroundTasks,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
    idem: str | None = Depends(_idem_key),
):
    """تحديث تفاصيل حقل عبر PATCH/PUT. PATCH جزئي، وPUT متاح كتعاقد API متوافق لعملاء الاستبدال/المزامنة؛ كلاهما يُحدِّث الأعمدة المُرسَلة فقط حفاظاً على التوافق وعدم مسح الحقول غير المرسلة.

    يتأكّد أنّ الحقل يخصّ المستأجِر (404) ضمن سياق المستأجِر (RLS)، يبني UPDATE
    من الحقول المُرسَلة فقط (دالّة نقيّة _build_field_update)، ويردّ الحقل المُحدَّث.
    422 لو لم تُرسَل أيّ حقول (لا UPDATE فارغ). 503 عند تعذّر القاعدة.

    idempotent عند توفّر Idempotency-Key (UUID): يُسجَّل الأمر مرّة واحدة في
    command_store (نوع `field.update`)؛ إعادة الموبايل (offline) تُعيد النتيجة
    المخزّنة بلا إعادة تحديث — موحِّداً مسار كتابة الحقل مع create_season/
    create_activity. بلا مفتاح ⇒ سلوك سابق حرفيّاً (توافق خلفيّ كامل).
    """
    # Geometry update path: forbid raw-polygon drift for pivot fields. We cannot decide
    # pivot-ness from the PATCH alone (irrigation_type may be omitted), so the geometry
    # guard/re-derive/reject is resolved INSIDE the tenant transaction, right after we read
    # the field's current irrigation_type from the DB (see _work below). Non-geometry-change
    # requests skip this entirely.
    geometry_changed = "geometry" in req.model_fields_set
    try:
        async with tenant_connection(user) as conn:

            async def _work():
                nonlocal req
                new_geometry_area_ha: float | None = None
                new_geometry_lat: float | None = None
                new_geometry_lon: float | None = None
                await _assert_field_in_tenant(conn, field_id)
                if geometry_changed and req.geometry is not None:
                    # نوع الريّ المخزَّن (قد لا يُرسله الـPATCH) لتحديد محوريّة الحقل.
                    irow = await conn.fetchrow(
                        "SELECT irrigation_type FROM fields WHERE field_id = $1",
                        field_id,
                    )
                    field_irrigation_type = irow["irrigation_type"] if irow else None
                    # حقل محوريّ: أعد اشتقاق المضلّع من البارامترات إن وُجدت، وإلّا ارفض
                    # (422) بدل تخزين مضلّع منحرف. حقل غير محوريّ: None ⇒ المسار العاديّ.
                    try:
                        canonical = resolve_pivot_update_geometry(
                            req.model_dump(mode="json"),
                            field_irrigation_type=field_irrigation_type,
                            request_irrigation_type=(
                                req.irrigation_type
                                if "irrigation_type" in req.model_fields_set
                                else None
                            ),
                        )
                    except PivotPolygonDriftError as exc:
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "message_ar": exc.message_ar,
                                "code": "pivot_polygon_drift_forbidden",
                            },
                        ) from exc
                    raw_geometry = canonical if canonical is not None else req.geometry
                    # حارس الهندسة (CRS/تقاطع ذاتي/مساحة) على الناتج (الخام أو المُشتقّ).
                    try:
                        guarded = guard_field_geometry(raw_geometry)
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "message_ar": "هندسة الحقل غير صالحة — صحّح الحدود وأعد المحاولة.",
                                "code": "invalid_field_geometry",
                                "issues": str(exc).split(","),
                            },
                        ) from exc
                    try:
                        validate_boundary_for_save(guarded.geometry, area_ha=guarded.area_ha)
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "message_ar": "حدود الحقل غير قابلة للحفظ — بسّط الحدود أو صحّح الرسم.",
                                "code": "field_boundary_save_guard",
                                "issues": str(exc).split(","),
                            },
                        ) from exc
                    req = req.model_copy(update={"geometry": guarded.geometry})
                    # حدود الحقل هي مصدر مساحة/مركز الحقل. تحديث geometry دون تحديث
                    # area_ha/lat/lon يترك القائمة والتوصيات والـbbox الاحتياطي على
                    # قيم قديمة؛ لذا نشتقّها من نفس Geometry Guard داخل المعاملة.
                    new_geometry_area_ha = round(guarded.area_ha, 2)
                    new_geometry_lat, new_geometry_lon = guarded.centroid
                try:
                    set_clause, values = _build_field_update(req)
                except ValueError as e:
                    raise HTTPException(status_code=422, detail="لا حقول للتحديث") from e
                if geometry_changed and req.geometry is not None:
                    idx = len(values) + 1
                    set_clause = (
                        f"{set_clause}, area_ha = ${idx}, lat = ${idx + 1}, lon = ${idx + 2}"
                    )
                    values.extend([new_geometry_area_ha, new_geometry_lat, new_geometry_lon])
                # رفع row_version دائماً + حارس تزامن تفاؤليّ إن مرّر base_version (v61).
                sql, exec_values = _build_versioned_update(
                    set_clause, values, field_id, req.base_version
                )
                upd = await conn.execute(sql, *exec_values)
                # تعارض تزامن تفاؤليّ: الحقل موجود (تأكّدنا) لكن UPDATE أصاب 0 صفّ ⇒
                # row_version لا يطابق base_version ⇒ عُدِّل من جلسة أخرى بين قراءة العميل
                # وكتابته. نرفض 409 (لا فقد صامت) قبل إصدار أيّ حدث — المعاملة تتراجع.
                if req.base_version is not None and upd.rsplit(" ", 1)[-1] == "0":
                    # تعارض إصدار: نقرأ سجلّ الخادم الحاليّ لتصنيف تغييرات العميل.
                    srow = await conn.fetchrow(
                        f"SELECT {_FIELD_DETAIL_SELECT} FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                        field_id,
                    )
                    if srow is None:
                        raise HTTPException(
                            status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر"
                        )
                    server_detail = _row_to_field_detail(srow)
                    server_py = server_detail.model_dump()
                    client_changes = req.model_dump(
                        exclude_unset=True, exclude={"base_version", "base_values"}
                    )
                    can_merge, conflicts = _field_merge_plan(
                        client_changes, server_py, req.base_values
                    )
                    if can_merge:
                        # Auto-merge (Level 3): لا تقاطع فعليّ ⇒ نُعيد تطبيق تغييرات
                        # العميل على النسخة الحاليّة بلا حارس الإصدار (دمج آمن، لا فقد).
                        merge_sql, merge_vals = _build_versioned_update(
                            set_clause, values, field_id, None
                        )
                        await conn.execute(merge_sql, *merge_vals)
                        mrow = await conn.fetchrow(
                            f"SELECT {_FIELD_DETAIL_SELECT} FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                            field_id,
                        )
                        _auto_payload = {**client_changes, "_auto_merged": True}
                        if geometry_changed and req.geometry is not None:
                            _auto_payload.update(
                                {
                                    "area_ha": new_geometry_area_ha,
                                    "lat": new_geometry_lat,
                                    "lon": new_geometry_lon,
                                }
                            )
                        await _emit_domain_event(
                            conn,
                            user,
                            "FIELD_UPDATED",
                            "field",
                            field_id,
                            _auto_payload,
                        )
                        # تدقيق صريح للدمج الآليّ (إضافةً لحدث تغيّر الحقل).
                        await _emit_domain_event(
                            conn,
                            user,
                            "OFFLINE_MERGE_AUTO",
                            "field",
                            field_id,
                            {
                                "merged_fields": sorted(client_changes),
                                "server_version_before": server_py.get("row_version"),
                            },
                        )
                        return _row_to_field_detail(mrow).model_dump()
                    # تعارض حقيقيّ (تقاطع أو بلا base_values) ⇒ 409 مُثرى (Workflow).
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "version_conflict",
                            "conflict": True,
                            "safe_to_retry": False,  # إعادة عمياء تدهس عمل الطرف الآخر
                            "message_ar": (
                                "عُدِّل الحقل من جلسة أخرى منذ قراءتك — راجع الفروق ثمّ احسم "
                                "(نسخة الخادم/نسختي/دمج)."
                            ),
                            "server_version": server_py.get("row_version"),
                            "client_version": req.base_version,
                            "base_version": req.base_version,
                            "server_record": server_detail.model_dump(mode="json"),
                            "client_record": client_changes,  # ما حاول العميل كتابته
                            "base_record": req.base_values,  # لقطة الأساس إن توفّرت
                            "conflicting_fields": conflicts,  # المتقاطعة فعليّاً (تحتاج حسماً)
                            "changed_fields": conflicts,  # اسم سابق (توافق خلفيّ)
                            # أسماء قديمة للتوافق الخلفيّ مع عملاء يقرؤونها:
                            "current_version": server_py.get("row_version"),
                            "your_base_version": req.base_version,
                        },
                    )
                row = await conn.fetchrow(
                    f"SELECT {_FIELD_DETAIL_SELECT} FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                    field_id,
                )
                if row is None:
                    # سُحب الحقل بين التأكيد والقراءة (نادر) ⇒ نرفع 404 **داخل** المعاملة
                    # قبل إصدار الحدث، فتتراجع المعاملة ولا يُكتب حدث لتحديث لم يقع فعلاً.
                    raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
                # حدث domain ضمن نفس المعاملة — الحقول المُرسَلة فقط في الـpayload.
                _updated_payload = req.model_dump(
                    exclude_unset=True, exclude={"base_version", "base_values"}
                )
                if geometry_changed and req.geometry is not None:
                    _updated_payload.update(
                        {
                            "area_ha": new_geometry_area_ha,
                            "lat": new_geometry_lat,
                            "lon": new_geometry_lon,
                        }
                    )
                await _emit_domain_event(
                    conn,
                    user,
                    "FIELD_UPDATED",
                    "field",
                    field_id,
                    # base_version عمّاد تزامن لا تغييرَ حقل ⇒ يُستثنى من حدث الـdomain.
                    _updated_payload,
                )
                if geometry_changed and req.geometry is not None:
                    updated_detail = _row_to_field_detail(row)
                    rev = await save_field_geometry_revision(
                        conn,
                        tenant_id=str(user.tenant_id),
                        field_id=field_id,
                        geometry=req.geometry,
                        changed_by=str(user.user_id),
                        reason="field.updated",
                        source="api.patch",
                        metadata=geometry_metadata(field_revision=updated_detail.row_version),
                    )
                    await mark_raster_cache_stale(
                        conn,
                        tenant_id=str(user.tenant_id),
                        field_id=field_id,
                        reason="field.geometry.updated",
                        metadata={
                            "geometry_revision": rev,
                            "scope": ["tiles", "indices", "zones", "statistics"],
                        },
                    )
                    await _emit_domain_event(
                        conn,
                        user,
                        "FIELD_GEOMETRY_CHANGED",
                        "field",
                        field_id,
                        {"geometry_revision": rev, "reason": "field.updated"},
                    )
                # نُعيد JSON (model_dump) ليُخزَّن كنتيجة أمر idempotent ويُعاد حرفيّاً
                # عند الإعادة — response_model=FieldDetail يتحقّق منه.
                return _row_to_field_detail(row).model_dump()

            # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="field.update",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"field_id": field_id},
                )
            else:
                result = await _work()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 لا 500
        raise _db_unavailable("تحديث تفاصيل الحقل", e) from e
    # تغيّر الحدّ ⇒ المؤشّرات/البلاطات القديمة أصبحت قديمة: أطلِق معالجة مُستهدَفة جديدة
    # (BackgroundTasks، بعد الالتزام — لا نداء HTTP داخل المعاملة فلا تُحبَس وصلة DB).
    if geometry_changed and isinstance(result, dict) and result.get("geometry"):
        background_tasks.add_task(
            _kick_imagery_processing,
            field_id=field_id,
            tenant_id=str(user.tenant_id),
            geometry=result["geometry"],
            reason="field.geometry.updated",
        )
    return result


@router.get("/api/v1/fields/{field_id}/geometry/history")
async def field_geometry_history(
    field_id: str,
    limit: int = Query(20, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """Geometry revision ledger for map/raster alignment and rollback UI.

    Returns append-only geometry revisions written by Geometry Guard. The response
    includes revision metadata so the map can compare field_revision with raster
    products and warn on stale overlays.
    """
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                """
                SELECT revision, geometry, changed_by, changed_at, reason, source, metadata
                FROM field_geometry_history
                WHERE field_id = $1
                ORDER BY revision DESC
                LIMIT $2
                """,
                field_id,
                limit,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة سجل هندسة الحقل", e) from e
    return {
        "field_id": field_id,
        "revisions": [
            {
                "revision": int(r["revision"]),
                "geometry": r["geometry"],
                "changed_by": r["changed_by"],
                "changed_at": r["changed_at"].isoformat() if r["changed_at"] else None,
                "reason": r["reason"],
                "source": r["source"],
                "metadata": r["metadata"] or {},
            }
            for r in rows
        ],
    }


@router.post("/api/v1/fields/{field_id}/geometry/revert/{revision}", response_model=FieldDetail)
async def revert_field_geometry(
    field_id: str,
    revision: int,
    background_tasks: BackgroundTasks,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """Restore a previous field boundary revision and invalidate imagery products.

    This makes geometry versioning actionable from the UI: historical raster
    analysis can keep the correct boundary revision, and operators can safely
    roll back an accidental edit. The restored geometry passes the same
    Polygon/MultiPolygon guard as normal PATCH writes.
    """
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            hrow = await conn.fetchrow(
                """
                SELECT geometry, revision
                FROM field_geometry_history
                WHERE field_id = $1 AND tenant_id = $2::uuid AND revision = $3
                """,
                field_id,
                str(user.tenant_id),
                revision,
            )
            if hrow is None:
                raise HTTPException(status_code=404, detail="مراجعة الحدود غير موجودة لهذا الحقل")
            raw_geometry = hrow["geometry"]
            guarded = guard_field_geometry(raw_geometry)
            import json as _json

            await conn.execute(
                """
                UPDATE fields
                SET geometry = $1::jsonb,
                    area_ha = $2,
                    lat = $3,
                    lon = $4,
                    row_version = row_version + 1
                WHERE field_id = $5 AND tenant_id = $6::uuid
                """,
                _json.dumps(guarded.geometry),
                round(guarded.area_ha, 2),
                guarded.centroid[0],
                guarded.centroid[1],
                field_id,
                str(user.tenant_id),
            )
            row = await conn.fetchrow(
                f"SELECT {_FIELD_DETAIL_SELECT} FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                field_id,
                str(user.tenant_id),
            )
            if row is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            detail = _row_to_field_detail(row)
            new_rev = await save_field_geometry_revision(
                conn,
                tenant_id=str(user.tenant_id),
                field_id=field_id,
                geometry=guarded.geometry,
                changed_by=str(user.user_id),
                reason="field.geometry.reverted",
                source="api.geometry.revert",
                metadata=geometry_metadata(field_revision=detail.row_version)
                | {"reverted_from_revision": revision},
            )
            await mark_raster_cache_stale(
                conn,
                tenant_id=str(user.tenant_id),
                field_id=field_id,
                reason="field.geometry.reverted",
                metadata={"geometry_revision": new_rev, "reverted_from_revision": revision},
            )
            await _emit_domain_event(
                conn,
                user,
                "FIELD_GEOMETRY_REVERTED",
                "field",
                field_id,
                {"geometry_revision": new_rev, "reverted_from_revision": revision},
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("استرجاع حدود الحقل", e) from e
    background_tasks.add_task(
        _kick_imagery_processing,
        field_id=field_id,
        tenant_id=str(user.tenant_id),
        geometry=guarded.geometry,
        reason="field.geometry.reverted",
    )
    return detail


@router.delete("/api/v1/fields/{field_id}")
async def delete_field(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_DELETE)),
):
    """يحذف حقلاً ويُصدِر FIELD_DELETED — حذف متتالٍ لتبعيّاته (مواسم/عمليّات/تنبيهات).

    حارس صدق: يُرفض (409) إن كان للحقل موسم نشط — أغلِقه أوّلاً (يمنع محو حقل قيد
    الاستخدام بالخطأ). الحدث يُصدَر قبل الحذف ضمن المعاملة (نمط outbox)، وentity_id
    نصّيّ (events منذ v18) فيبقى الحدث بعد حذف الحقل (لا FK من events إلى fields).
    404 لو الحقل ليس للمستأجِر؛ 503 عند تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT field_id, name, crop, farm_id FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                field_id,
                str(user.tenant_id),
            )
            if row is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            active = await conn.fetchval(
                "SELECT COUNT(*) FROM seasons WHERE field_id = $1 AND status = 'active'",
                field_id,
            )
            if active and int(active) > 0:
                raise HTTPException(
                    status_code=409,
                    detail="للحقل موسم نشط — أغلِقه قبل الحذف (تفادي محو بيانات قيد الاستخدام).",
                )
            # الحدث قبل الحذف (يحفظ ما حُذف)؛ ثمّ DELETE المتتالي.
            await _emit_domain_event(
                conn,
                user,
                "FIELD_DELETED",
                "field",
                field_id,
                {"name": row["name"], "crop": row["crop"], "farm_id": row["farm_id"]},
            )
            await conn.execute("DELETE FROM fields WHERE field_id = $1", field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("حذف الحقل", e) from e
    return {"field_id": field_id, "deleted": True}


# ─── دمج/انقسام الحقول ذرّيّاً (نقطتان تستبدلان لاذرّيّة الواجهة) ───────────────
# الواجهة سابقاً كانت تُنفّذ الدمج/الانقسام بعمليّات HTTP منفصلة (POST جديد ثمّ حلقة
# DELETE) بلا معاملة — فشل الحذف بعد الإنشاء يُخلّف حقولاً يتيمة (فقد بيانات). هاتان
# النقطتان تُنفّذان الكلّ-أو-لا-شيء داخل معاملة tenant_connection واحدة: إنشاء
# المدموج/الأطفال أوّلاً (الهندسة لا تضيع) ثمّ FIELD_DELETED + DELETE للمصادر؛ أيّ
# خطأ يتصاعد فتتراجع المعاملة كاملةً (لا حقل مدموج يتيَّم، لا مصدر محذوف بلا بديل).
# الهندسة client-computed (@turf) ويتحقّق منها الخادم عبر guard_field_geometry (لا ثقة).


class FieldMergeRequest(BaseModel):
    """طلب دمج عدّة حقول مصدر في حقل واحد (الهندسة المدموجة محسوبة @turf في الواجهة)."""

    source_field_ids: list[str] = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    geometry: dict  # GeoJSON Polygon المدموج (اتّحاد @turf) — يتحقّق منه الخادم
    crop: str | None = None
    soil_type: str | None = None
    manager: str | None = Field(default=None, max_length=100)
    farm_id: str | None = None
    field_code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    water_source: str | None = Field(default=None, max_length=20)
    irrigation_type: str | None = Field(default=None, max_length=20)
    ownership_type: str | None = Field(default=None, max_length=20)
    gov: str | None = None
    country: str | None = Field(default=None, max_length=60)
    region: str | None = Field(default=None, max_length=80)

    @field_validator("source_field_ids")
    @classmethod
    def _dedupe_sources(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("معرّفات الحقول المصدر مكرّرة")
        return v


class ChildField(BaseModel):
    """حقل وليد ناتج عن انقسام (اسم + هندسة @turf؛ المحصول اختياريّ يُورَّث/يُحدَّد)."""

    name: str = Field(min_length=1, max_length=100)
    geometry: dict  # GeoJSON Polygon للجزء (محسوب @turf) — يتحقّق منه الخادم
    crop: str | None = None
    soil_type: str | None = None
    manager: str | None = Field(default=None, max_length=100)
    field_code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    water_source: str | None = Field(default=None, max_length=20)
    irrigation_type: str | None = Field(default=None, max_length=20)
    ownership_type: str | None = Field(default=None, max_length=20)


class FieldSplitRequest(BaseModel):
    """طلب انقسام حقل واحد إلى عدّة حقول وليدة (٢..١٠؛ كلّ وليد بهندسته @turf)."""

    source_field_id: str
    children: list[ChildField] = Field(min_length=2, max_length=10)


def _guard_merge_split_geometry(
    raw_geometry: object,
) -> tuple[dict, float, tuple[float | None, float | None]]:
    """حارس هندسة موحَّد للدمج/الانقسام — نفس شكل خطأ _persist_field (422) عند الفشل.

    يُرجِع (geometry, area_ha, (lat, lon)). لا I/O — منطق تحقّق صرف عبر guard_field_geometry.
    """
    try:
        guarded = guard_field_geometry(raw_geometry)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message_ar": "هندسة الحقل غير صالحة — صحّح الحدود وأعد المحاولة.",
                "code": "invalid_field_geometry",
                "issues": str(exc).split(","),
            },
        ) from exc
    return guarded.geometry, round(guarded.area_ha, 2), guarded.centroid


@router.post("/api/v1/fields/merge", status_code=201, response_model=FieldSummary)
async def merge_fields(
    req: FieldMergeRequest,
    background_tasks: BackgroundTasks,
    user: UserSchema = Depends(require_permission(Permission.FIELD_CREATE)),
    idem: str | None = Depends(_idem_key),
):
    """يدمج عدّة حقول مصدر في حقل واحد ذرّيّاً (معاملة واحدة: الكلّ أو لا شيء).

    يستبدل لاذرّيّة الواجهة (POST جديد + حلقة DELETE بلا معاملة) التي كانت تُخلّف
    حقولاً يتيمة عند فشل الحذف. داخل tenant_connection (معاملة واحدة): يتحقّق ملكيّة
    كلّ مصدر (404)، يرفض أيّ مصدر بموسم نشط (409)، يتحقّق الهندسة المدموجة (422)،
    يُنشئ المدموج (FIELD_CREATED + سجلّ هندسة + حالة)، ثمّ FIELD_DELETED + DELETE لكلّ
    مصدر. أيّ خطأ يتصاعد فتتراجع المعاملة كاملةً. بعد الالتزام: معالجة صور مُستهدَفة.
    idempotent عبر Idempotency-Key (إعادة الموبايل لا تُكرّر).
    """
    import uuid as _uuid

    field_id = "fld_" + _uuid.uuid4().hex[:12]
    geometry, area_ha, (lat, lon) = _guard_merge_split_geometry(req.geometry)
    country, region = req.country, req.region
    if country is None or region is None:
        auto_country, auto_region = _reverse_geocode(lat, lon)
        country = country or auto_country
        region = region or auto_region
    try:
        async with tenant_connection(user) as conn:

            async def _work():
                # 1) ملكيّة كلّ مصدر (404) + رفض الموسم النشط (409) — قبل أيّ كتابة.
                for src_id in req.source_field_ids:
                    src = await conn.fetchrow(
                        "SELECT field_id, name, crop FROM fields "
                        "WHERE field_id = $1 AND tenant_id = $2::uuid",
                        src_id,
                        str(user.tenant_id),
                    )
                    if src is None:
                        raise HTTPException(
                            status_code=404,
                            detail=f"الحقل المصدر {src_id} غير موجود ضمن هذا المستأجِر",
                        )
                    active = await conn.fetchval(
                        "SELECT COUNT(*) FROM seasons WHERE field_id = $1 AND status = 'active'",
                        src_id,
                    )
                    if active and int(active) > 0:
                        raise HTTPException(
                            status_code=409,
                            detail="لا يمكن الدمج: موسم نشط على حقل مصدر",
                        )
                # 2) أنشئ المدموج أوّلاً (الهندسة لا تضيع) ضمن نفس المعاملة.
                result = await _insert_field_within_tx(
                    conn,
                    user,
                    field_id=field_id,
                    name=req.name,
                    crop=req.crop,
                    geometry=geometry,
                    area_ha=area_ha,
                    lat=lat,
                    lon=lon,
                    soil_type=req.soil_type,
                    manager=req.manager,
                    farm_id=req.farm_id,
                    gov=req.gov,
                    field_code=req.field_code,
                    description=req.description,
                    water_source=req.water_source,
                    irrigation_type=req.irrigation_type,
                    ownership_type=req.ownership_type,
                    country=country,
                    region=region,
                    reason="field.merged",
                    extra_event_meta={"merged_from": req.source_field_ids},
                )
                # 3) احذف كلّ مصدر (FIELD_DELETED قبل الحذف — نمط outbox، نفس
                #    دلالات delete_field). أيّ فشل هنا يتصاعد ⇒ تتراجع المعاملة كاملةً
                #    (لا حقل مدموج يتيَّم، لا مصدر محذوف بلا بديل) — سدّ خطر اللاذرّيّة.
                for src_id in req.source_field_ids:
                    src = await conn.fetchrow(
                        "SELECT name, crop FROM fields WHERE field_id = $1",
                        src_id,
                    )
                    await _emit_domain_event(
                        conn,
                        user,
                        "FIELD_DELETED",
                        "field",
                        src_id,
                        {
                            "name": src["name"] if src else None,
                            "crop": src["crop"] if src else None,
                            "merged_into": field_id,
                        },
                    )
                    await conn.execute("DELETE FROM fields WHERE field_id = $1", src_id)
                return result

            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="field.merge",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"source_ids": req.source_field_ids, "name": req.name},
                )
            else:
                result = await _work()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 لا 500
        raise _db_unavailable("دمج الحقول", e) from e
    background_tasks.add_task(
        _kick_imagery_processing,
        field_id=result["field_id"],
        tenant_id=str(user.tenant_id),
        geometry=result["geometry"],
        reason="field.merged",
    )
    return result


@router.post("/api/v1/fields/split", status_code=201, response_model=list[FieldSummary])
async def split_field(
    req: FieldSplitRequest,
    background_tasks: BackgroundTasks,
    user: UserSchema = Depends(require_permission(Permission.FIELD_CREATE)),
    idem: str | None = Depends(_idem_key),
):
    """يقسّم حقلاً واحداً إلى عدّة حقول وليدة ذرّيّاً (معاملة واحدة: الكلّ أو لا شيء).

    يستبدل لاذرّيّة الواجهة (POST×n للأطفال + DELETE للأصل بلا معاملة). داخل
    tenant_connection (معاملة واحدة): يتحقّق ملكيّة المصدر (404) ورفض الموسم النشط
    (409)، يتحقّق هندسة كلّ وليد (422)، يُنشئ الأطفال (FIELD_CREATED + سجلّ + حالة)،
    ثمّ FIELD_DELETED + DELETE للأصل. أيّ خطأ يتصاعد فتتراجع المعاملة كاملةً. بعد
    الالتزام: معالجة صور مُستهدَفة لكلّ وليد. idempotent عبر Idempotency-Key.
    """
    import uuid as _uuid

    # تحقّق هندسة كلّ وليد + اشتقاق مساحته/مركزه قبل فتح المعاملة (422 مبكّر، لا I/O).
    prepared: list[dict] = []
    for child in req.children:
        geometry, area_ha, (lat, lon) = _guard_merge_split_geometry(child.geometry)
        c_country, c_region = _reverse_geocode(lat, lon)
        prepared.append(
            {
                "field_id": "fld_" + _uuid.uuid4().hex[:12],
                "child": child,
                "geometry": geometry,
                "area_ha": area_ha,
                "lat": lat,
                "lon": lon,
                "country": c_country,
                "region": c_region,
            }
        )
    try:
        async with tenant_connection(user) as conn:

            async def _work():
                # 1) ملكيّة المصدر (404) + رفض الموسم النشط (409) — قبل أيّ كتابة.
                src = await conn.fetchrow(
                    "SELECT field_id, name, crop FROM fields "
                    "WHERE field_id = $1 AND tenant_id = $2::uuid",
                    req.source_field_id,
                    str(user.tenant_id),
                )
                if src is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"الحقل المصدر {req.source_field_id} غير موجود ضمن هذا المستأجِر",
                    )
                active = await conn.fetchval(
                    "SELECT COUNT(*) FROM seasons WHERE field_id = $1 AND status = 'active'",
                    req.source_field_id,
                )
                if active and int(active) > 0:
                    raise HTTPException(
                        status_code=409,
                        detail="لا يمكن الانقسام: موسم نشط على الحقل المصدر",
                    )
                # 2) أنشئ كلّ وليد أوّلاً (الهندسة لا تضيع) ضمن نفس المعاملة.
                children_out: list[dict] = []
                for p in prepared:
                    child: ChildField = p["child"]
                    children_out.append(
                        await _insert_field_within_tx(
                            conn,
                            user,
                            field_id=p["field_id"],
                            name=child.name,
                            crop=child.crop,
                            geometry=p["geometry"],
                            area_ha=p["area_ha"],
                            lat=p["lat"],
                            lon=p["lon"],
                            soil_type=child.soil_type,
                            manager=child.manager,
                            field_code=child.field_code,
                            description=child.description,
                            water_source=child.water_source,
                            irrigation_type=child.irrigation_type,
                            ownership_type=child.ownership_type,
                            country=p["country"],
                            region=p["region"],
                            reason="field.split",
                            extra_event_meta={"split_from": req.source_field_id},
                        )
                    )
                # 3) احذف المصدر (FIELD_DELETED قبل الحذف — نفس دلالات delete_field).
                #    أيّ فشل يتصاعد ⇒ تتراجع المعاملة كاملةً (لا وليد يتيَّم، لا أصل
                #    محذوف بلا أطفال) — سدّ خطر اللاذرّيّة.
                await _emit_domain_event(
                    conn,
                    user,
                    "FIELD_DELETED",
                    "field",
                    req.source_field_id,
                    {
                        "name": src["name"],
                        "crop": src["crop"],
                        "split_into": [c["field_id"] for c in children_out],
                    },
                )
                await conn.execute("DELETE FROM fields WHERE field_id = $1", req.source_field_id)
                return children_out

            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="field.split",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={
                        "source_id": req.source_field_id,
                        "children": [c.name for c in req.children],
                    },
                )
            else:
                result = await _work()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 لا 500
        raise _db_unavailable("انقسام الحقل", e) from e
    # بعد الالتزام: معالجة صور مُستهدَفة لكلّ وليد (مهمّة خلفيّة لكلّ طفل).
    for child_result in result:
        background_tasks.add_task(
            _kick_imagery_processing,
            field_id=child_result["field_id"],
            tenant_id=str(user.tenant_id),
            geometry=child_result["geometry"],
            reason="field.split",
        )
    return result


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


@router.get("/api/v1/fields/{field_id}/soil-moisture")
async def field_soil_moisture(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """أحدث قراءة رطوبة تربة (٪) لأجهزة الحقل من telemetry الحيّ، أو null.

    يقرأ من device_telemetry (الأجهزة المرتبطة بالحقل عبر iot_devices.field_id)
    ضمن سياق المستأجِر (RLS) بعد تأكيد أنّ الحقل يخصّه (404). يردّ القراءة + زمنها
    + الجهاز المصدر، أو reading=null إن لا قراءة صالحة (لا بيانات وهميّة). 503 إن
    تعذّرت القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            reading = await _latest_soil_moisture(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة رطوبة التربة", e) from e
    return {
        "field_id": field_id,
        "reading": reading.as_dict() if reading is not None else None,
    }


@router.get("/api/v1/fields/{field_id}/weather/irrigation-advice")
async def field_irrigation_advice(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """توصية ريّ بنمط FAO-56 للحقل من الطقس الحيّ ومحصول الموسم النشط.

    يحسب ET₀ × Kc − المطر الفعّال (api.weather_advice، نقيّ ومُختبَر). يجلب ET₀
    والمطر من Open-Meteo (نفس مصدر /api/v1/weather). 404 إن غاب الحقل، 503 إن
    تعذّر الطقس (لا بيانات وهميّة).
    """
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.weather_advice import irrigation_advice

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage, _days = await _field_weather_context(conn, field_id)
            # رطوبة تربة حيّة من telemetry الأجهزة (إن وُجدت) — تُغذّي إلحاح التوصية.
            soil_reading = await _latest_soil_moisture(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياق الحقل", e) from e

    try:
        forecast = await fetch_daily_forecast(lat, lon, days=3)
        current = await fetch_current(lat, lon)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — تعذّر مصدر الطقس ⇒ 503 صريح
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس (مصدر Open-Meteo غير متاح). حاول لاحقاً.",
        ) from e

    today = forecast[0] if forecast else None
    et0 = today.et0_mm if today and today.et0_mm is not None else None
    if et0 is None:
        raise HTTPException(
            status_code=503,
            detail="بيانات ET₀ غير متوفّرة من مصدر الطقس حاليّاً. حاول لاحقاً.",
        )
    # المطر المتوقّع خلال ٤٨ ساعة القادمة (يومان قادمان من التوقّع).
    forecast_rain = sum(f.precipitation_mm or 0.0 for f in forecast[1:3])
    soil_pct = soil_reading.value_pct if soil_reading is not None else None
    advice = irrigation_advice(
        et0_mm=et0,
        crop=crop,
        stage=stage,
        rain_recent_mm=current.precipitation_mm or 0.0,
        forecast_rain_mm=forecast_rain,
        soil_moisture_pct=soil_pct,
    )
    advice.update(
        {
            "field_id": field_id,
            "crop": crop,
            "stage": stage,
            "source": "open-meteo",
            "soil_moisture_pct": soil_pct,
            "soil_moisture_at": (
                soil_reading.recorded_at.isoformat() if soil_reading is not None else None
            ),
        }
    )
    return advice


@router.get("/api/v1/fields/{field_id}/weather/disease-risk")
async def field_disease_risk(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مخاطر أمراض فطريّة (agro-met) للحقل من الرطوبة/الحرارة/المطر.

    منطق التهديف نقيّ (api.weather_advice، مُختبَر offline). يجلب الطقس الحالي +
    مطر آخر ٣ أيّام من Open-Meteo. 404 إن غاب الحقل، 503 إن تعذّر الطقس.
    """
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.weather_advice import disease_risk

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, _stage, _days = await _field_weather_context(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياق الحقل", e) from e

    try:
        current = await fetch_current(lat, lon)
        forecast = await fetch_daily_forecast(lat, lon, days=3)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — تعذّر مصدر الطقس ⇒ 503 صريح
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس (مصدر Open-Meteo غير متاح). حاول لاحقاً.",
        ) from e

    rain_3d = sum(f.precipitation_mm or 0.0 for f in forecast[:3])
    risk = disease_risk(
        temp_c=current.temperature_c,
        humidity_pct=current.humidity_pct,
        rain_mm_3d=rain_3d,
        crop=crop,
    )
    risk.update(
        {
            "field_id": field_id,
            "crop": crop,
            "temperature_c": round(current.temperature_c, 1),
            "humidity_pct": round(current.humidity_pct, 1),
            "rain_mm_3d": round(rain_3d, 1),
            "source": "open-meteo",
        }
    )
    return risk


@router.get("/api/v1/fields/{field_id}/recommendations")
async def field_recommendations(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """عمود التوصيات الموحَّد للحقل: ريّ + تسميد + أمراض + حصاد، مفروز بالأولويّة.

    التجميع نقيّ (api.recommendations_hub، مُختبَر offline). يجمع سياق الموسم من
    القاعدة (404 إن غاب الحقل، 503 إن تعذّرت القاعدة) والطقس من Open-Meteo. تدهور
    رشيق: عند تعذّر الطقس (أو غياب إحداثيّات الحقل) نُرجع توصيات التسميد/الحصاد
    فقط — لا بيانات وهميّة. 503 فقط إن لم تتوفّر أيّة توصية.
    """
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.field_state_projection import recompute_field_state
    from api.recommendations_hub import RecommendationContext, build_recommendations

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage, sowing_date = await _field_season_context(conn, field_id)
            # Canonical Field State: التوصيات تمرّ عبر الحالة القانونيّة الموحّدة —
            # نُحدِّث الإسقاط ونرفق صلاحيّة القرار + نمط التنفيذ بالاستجابة (مصدر حقيقة
            # واحد يحكم: تلقائيّ أم مراجعة بشريّة)، بدل قرار متفرّق لكلّ توصية.
            field_state = (await recompute_field_state(conn, field_id))["state"]
            # سياسة محرّكات التوصيات لكلّ مستأجِر — قراءة صغيرة عبر نفس الاتّصال
            # المنطاقيّ (RLS). None ⇒ لا سياسة ⇒ السلوك مطابق لليوم تماماً.
            enabled_ids = await _load_recommendation_policy(conn)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياق الحقل للتوصيات", e) from e

    ctx = RecommendationContext(
        field_id=field_id,
        crop=crop,
        stage=stage,
        today=date.today(),
        sowing_date=sowing_date,
    )
    # Stage F (تغذية آمنة): مرّر مرجعيّة النواة الزراعيّة الموحّدة للمُجمِّع — تصعيد/
    # تنبيه فقط (تنبيه ملوحة حرجة) لا استبدال أرقام. صدق: غياب الحقائق ⇒ لا تصعيد.
    _agro_truths = (field_state.get("agronomic") or {}).get("operational_truths") or {}
    ctx.salinity_class = _agro_truths.get("salinity_class")
    ctx.crop_vigor = _agro_truths.get("crop_vigor")

    # الطقس اختياريّ: نملأ سياقه إن توفّرت الإحداثيّات والمصدر. تعذّره لا يُسقط
    # الطلب — نكتفي بالتوصيات التي لا تحتاجه (تدهور رشيق، لا تلفيق).
    weather_available = False
    if lat is not None and lon is not None:
        try:
            forecast = await fetch_daily_forecast(lat, lon, days=3)
            current = await fetch_current(lat, lon)
            today = forecast[0] if forecast else None
            et0 = today.et0_mm if today and today.et0_mm is not None else None
            ctx.et0_mm = et0
            ctx.rain_recent_mm = current.precipitation_mm or 0.0
            ctx.forecast_rain_mm = sum(f.precipitation_mm or 0.0 for f in forecast[1:3])
            ctx.temp_c = current.temperature_c
            ctx.humidity_pct = current.humidity_pct
            ctx.rain_mm_3d = await _historical_rain_3d_mm(
                lat, lon, sum(f.precipitation_mm or 0.0 for f in forecast[:3])
            )
            weather_available = True
        except Exception:  # noqa: BLE001 — تعذّر الطقس ⇒ تدهور رشيق لا فشل
            logging.exception("recommendations: weather unavailable for %s", field_id)

    # enabled_ids=None ⇒ تُفعَّل كلّ المحرّكات بحسب default_enabled (سلوك مطابق لليوم).
    recs = build_recommendations(ctx, enabled_ids=enabled_ids)
    if not recs:
        # لا توصية أمكن توليدها (لا طقس، لا محصول، لا بذار) — فشل صادق.
        raise HTTPException(
            status_code=503,
            detail="تعذّر توليد توصيات (لا طقس ولا سياق موسم كافٍ). حدّد موقع الحقل وموسمه.",
        )

    return {
        "field_id": field_id,
        "crop": crop,
        "stage": stage,
        "weather_available": weather_available,
        # الحالة القانونيّة الموحّدة تحكم تطبيق التوصيات (مصدر حقيقة واحد): نمط
        # التنفيذ != auto ⇒ requires_review (تحتاج تأكيد المهندس/المزارع قبل التنفيذ).
        "field_state": {
            "validity": field_state["validity"],
            "execution_mode": field_state["execution_mode"],
            "confidence_level": field_state.get("confidence_level"),
            "reasons_ar": field_state.get("reasons_ar", []),
        },
        "requires_review": field_state["execution_mode"] != "auto",
        "recommendations": [r.to_dict() for r in recs],
    }


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


@router.post(
    "/api/v1/fields/{field_id}/soil-lab-tests",
    status_code=201,
    response_model=SoilLabTestSummary,
)
async def create_soil_lab_test(
    field_id: str,
    req: SoilLabTestCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """ينشئ فحص تربة (حالة requested) — بداية دورة الحياة المخبريّة. يُصدِر SOIL_SAMPLE_RECORDED."""
    import json as _json
    import uuid as _uuid

    sampled = _parse_date(req.sampled_on, "تاريخ العيّنة")
    test_id = "soil_" + _uuid.uuid4().hex[:12]
    try:
        result_json = _json.dumps(req.result or {})
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail="نتيجة الفحص غير قابلة للتسلسل (JSON)") from e
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO soil_lab_tests "
                    "(test_id, tenant_id, field_id, status, lab_name, sampled_on, result, notes_ar) "
                    "VALUES ($1, $2::uuid, $3, 'requested', $4, $5, $6::jsonb, $7)",
                    test_id,
                    str(user.tenant_id),
                    field_id,
                    req.lab_name,
                    sampled,
                    result_json,
                    req.notes_ar,
                )
                await _emit_domain_event(
                    conn,
                    user,
                    "SOIL_SAMPLE_RECORDED",
                    "soil_lab_test",
                    test_id,
                    {"field_id": field_id, "status": "requested"},
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إنشاء فحص التربة", e) from e
    return SoilLabTestSummary(
        test_id=test_id,
        field_id=field_id,
        status="requested",
        lab_name=req.lab_name,
        sampled_on=sampled.isoformat() if sampled else None,
        result=req.result or {},
        notes_ar=req.notes_ar,
    )


@router.get(
    "/api/v1/fields/{field_id}/soil-lab-tests",
    response_model=list[SoilLabTestSummary],
)
async def list_soil_lab_tests(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """فحوص تربة الحقل (الأحدث أولاً) — مُرشَّحة بالمستأجِر (RLS). 503 عند تعذّر القاعدة."""
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                f"SELECT {_SOIL_TEST_SELECT} FROM soil_lab_tests "
                "WHERE field_id = $1 ORDER BY created_at DESC",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة فحوص التربة", e) from e
    return [_row_to_soil_test(r) for r in rows]


@router.patch(
    "/api/v1/fields/{field_id}/soil-lab-tests/{test_id}",
    response_model=SoilLabTestSummary,
)
async def update_soil_lab_test(
    field_id: str,
    test_id: str,
    req: SoilLabTestUpdateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يحدّث فحص تربة (انتقال حالة محقَّق + بيانات) — يُصدِر SOIL_LAB_RESULT_PUBLISHED عند النشر.

    الانتقال عبر `soil_lab_workflow` (عيّنة→مختبر→نتيجة→اعتماد→نشر؛ المنشور/الملغى
    نهائيّان؛ لا اعتماد/نشر بلا نتيجة — 422). تأكيد ملكيّة الحقل (404)؛ الفحص يخصّ
    الحقل (404). 503 عند تعذّر القاعدة.
    """
    import json as _json

    from core.engines.soil_lab_workflow import SoilWorkflowError, validate_soil_transition

    sampled = _parse_date(req.sampled_on, "تاريخ العيّنة") if req.sampled_on is not None else None
    if req.result is not None:
        try:
            result_json = _json.dumps(req.result)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=422, detail="نتيجة الفحص غير قابلة للتسلسل") from e

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            async with conn.transaction():
                cur = await conn.fetchrow(
                    "SELECT status, result FROM soil_lab_tests "
                    "WHERE test_id = $1 AND field_id = $2 FOR UPDATE",
                    test_id,
                    field_id,
                )
                if cur is None:
                    raise HTTPException(status_code=404, detail="فحص التربة غير موجود لهذا الحقل")

                set_parts, params = [], []

                def _add(col, value, cast=""):
                    params.append(value)
                    set_parts.append(f"{col} = ${len(params)}{cast}")

                if req.lab_name is not None:
                    _add("lab_name", req.lab_name)
                if req.sampled_on is not None:
                    _add("sampled_on", sampled)
                if req.notes_ar is not None:
                    _add("notes_ar", req.notes_ar)
                if req.result is not None:
                    _add("result", result_json, "::jsonb")

                status_changed = False
                if req.status is not None:
                    # توفّر نتيجة = نتيجة موجودة سابقاً (JSONB غير فارغ) أو ممرَّرة الآن.
                    existing = cur["result"]
                    existing_obj = (
                        _json.loads(existing) if isinstance(existing, str) else (existing or {})
                    )
                    has_result = bool(req.result) or bool(existing_obj)
                    try:
                        status_changed = validate_soil_transition(
                            cur["status"], req.status, has_result=has_result
                        )
                    except SoilWorkflowError as se:
                        raise HTTPException(
                            status_code=se.http_status, detail=se.message_ar
                        ) from se
                    if status_changed:
                        _add("status", req.status)
                        if req.status == "approved":
                            _add("approved_by", str(user.user_id))
                        if req.status == "published":
                            set_parts.append("published_at = now()")  # وقت القاعدة (لا param)

                if not set_parts:
                    raise HTTPException(status_code=422, detail="لا حقول للتحديث")

                params.extend([test_id, field_id])
                await conn.execute(
                    f"UPDATE soil_lab_tests SET {', '.join(set_parts)} "
                    f"WHERE test_id = ${len(params) - 1} AND field_id = ${len(params)}",
                    *params,
                )
                if status_changed and req.status == "published":
                    await _emit_domain_event(
                        conn,
                        user,
                        "SOIL_LAB_RESULT_PUBLISHED",
                        "soil_lab_test",
                        test_id,
                        {"field_id": field_id},
                    )
                    # نشر نتيجة التربة يُدخِل EC جديداً (تقرؤه gather_field_freshness من
                    # soil_lab_tests المنشورة) ⇒ قد تتبدّل الملوحة فالحالة القانونيّة
                    # (نمط التنفيذ/الصلاحيّة). أعِد حساب الإسقاط وأصدِر field.state_changed
                    # إن تبدّل — تغذية حيّة لمستهلكي الحالة، نفس معاملة الكتابة (outbox).
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
                                "trigger": "soil_lab.published",
                            },
                        )
                row = await conn.fetchrow(
                    f"SELECT {_SOIL_TEST_SELECT} FROM soil_lab_tests WHERE test_id = $1",
                    test_id,
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تحديث فحص التربة", e) from e
    return _row_to_soil_test(row)


@router.post(
    "/api/v1/fields/{field_id}/alerts/evaluate",
    response_model=AlertEvaluateResponse,
)
async def evaluate_field_alerts_endpoint(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يُقيّم ظروف الحقل الحاليّة ويُنشئ تنبيهات مُصنَّفة في جدول alerts (v36).

    يؤكّد أنّ الحقل يخصّ المستأجِر (404)، يبني السياق من الطقس الحيّ (Open-Meteo،
    نفس مصدر /api/v1/weather) ومحصول/مرحلة الموسم النشط، يُشغّل قواعد التنبيه
    النقيّة (api.alert_rules)، ثمّ يُدرِج النتائج — مع تجاوز أيّ نوع تنبيه له
    تنبيه 'active' قائم لهذا الحقل (dedupe). 503 إن تعذّر الطقس/القاعدة.
    """
    created, skipped = await _evaluate_field_alerts_persist(user, field_id)
    return AlertEvaluateResponse(created=created, skipped_existing=skipped)


@router.post("/api/v1/fields/{field_id}/rotations", status_code=201)
async def add_crop_rotation(
    field_id: str,
    req: RotationRequest,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_PLAN)),
):
    """يسجّل محصولاً في تعاقب الحقل (الدورة الزراعيّة + التتبّع)."""
    import uuid as _uuid

    rotation_id = "rot_" + _uuid.uuid4().hex[:12]
    planted = _parse_date(req.planted_at, "planted_at")
    harvested = _parse_date(req.harvested_at, "harvested_at")
    async with tenant_connection(user) as conn:
        exists = await conn.fetchval("SELECT 1 FROM fields WHERE field_id = $1", field_id)
        if not exists:
            raise HTTPException(status_code=404, detail="الحقل غير موجود")
        await conn.execute(
            """INSERT INTO crop_rotations
                (rotation_id, tenant_id, field_id, crop, season_label,
                 sequence_order, planted_at, harvested_at, notes)
               VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9)""",
            rotation_id,
            str(user.tenant_id),
            field_id,
            req.crop,
            req.season_label,
            req.sequence_order,
            planted,
            harvested,
            req.notes,
        )
        await _emit_domain_event(
            conn,
            user,
            "CROP_ROTATION_ADDED",
            "crop_rotation",
            rotation_id,
            {"field_id": field_id, "crop": req.crop},
        )
    return {"rotation_id": rotation_id, "message_ar": "سُجّل تعاقب المحصول"}


@router.get("/api/v1/fields/{field_id}/rotations")
async def list_crop_rotations(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تاريخ تعاقب المحاصيل للحقل (للدورة الزراعيّة وتتبّع المحصول)."""
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT rotation_id, crop, season_label, sequence_order, planted_at, harvested_at, notes "
            "FROM crop_rotations WHERE field_id = $1 "
            "ORDER BY sequence_order NULLS LAST, planted_at",
            field_id,
        )
    return [
        {
            "rotation_id": r["rotation_id"],
            "crop": r["crop"],
            "season_label": r["season_label"],
            "sequence_order": r["sequence_order"],
            "planted_at": r["planted_at"].isoformat() if r["planted_at"] else None,
            "harvested_at": r["harvested_at"].isoformat() if r["harvested_at"] else None,
            "notes": r["notes"],
        }
        for r in rows
    ]


@router.post("/api/v1/fields/{field_id}/trueup")
def apply_trueup(
    field_id: str,
    req: TrueUpRequest,
    user: UserSchema = Depends(require_permission(Permission.CALIBRATION_RUN)),
):
    """معايرة الإنتاج (TrueUp) — يحسب k_new + الإنتاج المُعدَّل.

    المرجع: المستند ٩ (FieldView TrueUp).
    الرياضيّات في trueup.py (pure، مُختبَرة). هذا الـendpoint يوصّلها.
    """
    if req.field_id != field_id:
        raise HTTPException(status_code=400, detail="field_id mismatch بين المسار والجسم")

    inp = TrueUpInput(
        field_id=req.field_id,
        operation_id=req.operation_id,
        actual_weight_kg=req.actual_weight_kg,
        actual_moisture_pct=req.actual_moisture_pct,
        measured_weight_kg=req.measured_weight_kg,
        sample_area_ha=req.sample_area_ha,
        notes_ar=req.notes_ar,
    )

    result = _trueup_engine.compute(
        input_data=inp,
        crop=req.crop,
        measured_yield_kg_ha=req.measured_yield_kg_ha,
        k_old=1.0,
    )

    if result.status == TrueUpStatus.REJECTED:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "rejected",
                "rationale_ar": result.rationale_ar,
                "warnings": result.warnings,
            },
        )

    return {
        "status": result.status.value,
        "field_id": result.field_id,
        "operation_id": result.operation_id,
        "k_new": result.k_new,
        "k_change_pct": result.k_change_pct,
        "measured_yield_kg_ha": result.measured_yield_kg_ha,
        "adjusted_yield_kg_ha": result.adjusted_yield_kg_ha,
        "error_pct": result.error_pct,
        "moisture_correction_applied": result.moisture_correction_applied,
        "standard_moisture_pct": result.standard_moisture_pct,
        "rationale_ar": result.rationale_ar,
        "warnings": result.warnings,
        "applied_at": result.applied_at,
        "persisted": False,
    }


@router.post("/api/v1/fields/validate-geometry")
def validate_geometry(
    req: GeometryValidateRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتحقّق من صلاحيّة حدود حقل قبل الحفظ.

    يكشف: CRS غير 4326، تقاطع ذاتي، مساحة غير معقولة، إحداثيّات خارج اليمن،
    ترتيب lng/lat معكوس. يُرجع المساحة المحسوبة + الـbbox عند النجاح.
    """
    result = validate_field_geometry(req.geojson, declared_crs=req.declared_crs)

    issues = [
        {
            "severity": i.severity.value,
            "code": i.code,
            "message_ar": i.message_ar,
            "hint": i.hint,
        }
        for i in result.issues
    ]

    return {
        "valid": result.valid,
        "canonical_crs": result.canonical_crs,
        "computed_area_ha": result.computed_area_ha,
        "computed_bbox": result.computed_bbox,
        "issues": issues,
        "has_errors": result.has_errors,
        "has_warnings": result.has_warnings,
    }


@router.post("/api/v1/fields/{field_id}/prescriptions/nitrogen")
def prescribe_nitrogen(
    field_id: str,
    req: NitrogenRxRequest,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_PLAN)),
):
    """توصية تسميد نيتروجيني متغيّر المعدّل (Variable-Rate N) حسب الزون."""
    try:
        zones = [
            ZoneCharacteristics(
                zone_id=z.zone_id,
                zone_class=ZoneClass(z.zone_class),
                area_ha=z.area_ha,
                ndvi_mean=z.ndvi_mean,
                soil_ph=z.soil_ph,
                soil_ec=z.soil_ec,
                soil_om=z.soil_om,
                soil_n_ppm=z.soil_n_ppm,
                soil_texture=z.soil_texture,
                soil_depth_cm=z.soil_depth_cm,
            )
            for z in req.zones
        ]
        rx = _rx_generator.generate_nitrogen(field_id, req.season_id, req.crop, zones)
        return prescription_to_dict(rx)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/api/v1/fields/{field_id}/yield-estimate")
async def estimate_field_yield(
    field_id: str,
    req: YieldEstimateRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تقدير الإنتاج (heuristic — ليس AI) + كشف الشذوذ."""
    features = LifecycleFeatures(
        field_id=field_id,
        crop=req.crop,
        days_in_growing=req.days_in_growing,
        irrigation_count=req.irrigation_count,
        moisture_stress_events=req.moisture_stress_events,
        pest_alerts=req.pest_alerts,
        fertilizer_applications=req.fertilizer_applications,
        avg_ndvi_growing=req.avg_ndvi_growing,
        drought_streak_days=req.drought_streak_days,
        rain_events=req.rain_events,
    )
    est = estimate_yield(features)
    anomalies = detect_anomalies(features)
    result = {
        "field_id": est.field_id,
        "crop": est.crop,
        "estimated_yield_kg_ha": est.estimated_yield_kg_ha,
        "yield_score": est.yield_score,
        "confidence": est.confidence,
        "stress_level": est.stress_level.value,
        "rationale_ar": est.rationale_ar,
        "contributors": est.contributors,
        "warnings": est.warnings,
        "anomalies": [
            {
                "type": a.type,
                "severity": a.severity,
                "message_ar": a.message_ar,
                "action_ar": a.suggested_action_ar,
            }
            for a in anomalies
        ],
    }

    # Stage F (تغذية آمنة): نرفق الحالة القانونيّة الموحّدة (Canonical Field State)
    # كمرجعيّة/ثقة فقط — **لا نغيّر رقم التقدير إطلاقاً** (تغيير أرقام زراعيّة يحتاج
    # تحقّقاً ميدانيّاً). نمط التنفيذ != auto ⇒ requires_review (يحتاج تأكيد المهندس
    # قبل الاعتماد على التقدير). صدق + fail-safe: أيّ تعذّر في جلب الحالة لا يكسر
    # التقدير (نتابع بلا الحالة)؛ غياب الحالة ⇒ لا تُرفَق كتلة field_state.
    try:
        # الاستيراد ضمن try أيضاً: أيّ ImportError يُعامَل كتعذّر جلب الحالة (لا
        # يكسر التقدير) — تحقيقاً للـfail-safe المعلن (مراجعة Copilot).
        from api.field_state_projection import recompute_field_state

        async with tenant_connection(user) as conn:
            field_state = (await recompute_field_state(conn, field_id))["state"]
    except Exception:  # noqa: BLE001 — تعذّر جلب الحالة لا يكسر التقدير (تابع بلا الحالة)
        logging.exception("yield-estimate: field_state unavailable for %s", field_id)
        field_state = None

    if field_state is not None:
        _agronomic = field_state.get("agronomic") or {}
        _truths = _agronomic.get("operational_truths") or {}
        # نوع ثابت: operational_truths كائن دائماً (وإن فارغاً) لا null (مراجعة Copilot).
        result["field_state"] = {
            "validity": field_state.get("validity"),
            "execution_mode": field_state.get("execution_mode"),
            "confidence_level": field_state.get("confidence_level"),
            "agronomic": {"operational_truths": _truths},
        }
        result["requires_review"] = field_state.get("execution_mode") != "auto"

    return result


@router.post("/api/v1/fields/{field_id}/timeline")
def field_timeline(
    field_id: str,
    req: TimelineRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يبني الخطّ الزمني للحقل (مُصنّف + مرتّب + بإحصاءات الفئات).

    ملاحظة: يأخذ الأحداث في الـrequest. النسخة التي تجلب من events table
    تحتاج PostgreSQL — غير مُفعَّلة بعد.
    """
    tl = assemble_timeline(
        field_id,
        req.events,
        newest_first=req.newest_first,
        category_filter=req.category_filter,
    )
    return tl.to_dict()


@router.get("/api/v1/fields/{field_id}/history")
async def field_history(
    field_id: str,
    limit: int = 200,
    user: UserSchema = Depends(get_current_user),
):
    """السياق التاريخي للحقل: أحداثه + القضايا المتكرّرة (farm memory).

    يجلب من events table عبر tenant_connection (RLS — كلّ مستأجر أحداثه فقط).
    يُغذّي memory_adapter في حلقة القرار (Runtime Cohesion). صدق: عند تعطّل
    القاعدة يُرجِع events فارغة (لا تاريخ مخترَع) ويُعلن السبب.
    """
    if _DB_POOL is None:
        return {
            "field_id": field_id,
            "events": [],
            "total_events": 0,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا تاريخ حيّ",
        }
    out_events: list[dict] = []
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, event_type, payload, occurred_at
                FROM events
                WHERE entity_type = 'field' AND entity_id = $1
                ORDER BY occurred_at DESC
                LIMIT $2
                """,
                field_id,
                max(1, min(limit, 1000)),  # قصّ [1..1000]: limit≤0 يرمي/يُفرغ بلا داعٍ
            )
        for r in rows:
            payload = r["payload"] if isinstance(r["payload"], dict) else {}
            out_events.append(
                {
                    "event_id": str(r["event_id"]),
                    "event_type": r["event_type"],
                    "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else "",
                    "issue_tags": _issue_tags_from_event(r["event_type"], payload),
                }
            )
    except Exception as e:  # noqa: BLE001 — صدق: نُعلن الفشل لا نخترع تاريخاً
        return {
            "field_id": field_id,
            "events": [],
            "total_events": 0,
            "error": f"تعذّر جلب التاريخ: {e}",
        }
    return {"field_id": field_id, "events": out_events, "total_events": len(out_events)}


@router.get("/api/v1/fields/{field_id}/unified-timeline")
async def field_unified_timeline(
    field_id: str,
    limit: int = 200,
    newest_first: bool = True,
    category: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """الخطّ الزمنيّ الموحّد للحقل: يدمج أحداثه عبر كلّ أنواع الكيانات.

    على عكس ``/history`` (يجلب ``entity_type='field'`` فقط)، يجمع هنا دورة الحياة
    والأنشطة والتنبيهات والتوصيات لحقلٍ واحد — سواء كان ``field_id`` هو ``entity_id``
    أو داخل ``payload->>'field_id'`` — ويمرّ بـ``assemble_timeline`` (تصنيف+فرز+إحصاءات)
    عبر ``tenant_connection`` (RLS — كلّ مستأجر أحداثه فقط). صدق: عند تعطّل القاعدة
    يُرجِع خطّاً فارغاً ويُعلن السبب (لا تاريخ مخترَع).
    """
    if _DB_POOL is None:
        return {
            "field_id": field_id,
            "events": [],
            "total_events": 0,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا تاريخ حيّ",
        }
    raw: list[dict] = []
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, event_type, payload, actor_id, occurred_at
                FROM events
                WHERE entity_id = $1 OR payload->>'field_id' = $1
                ORDER BY occurred_at DESC
                LIMIT $2
                """,
                field_id,
                max(1, min(limit, 1000)),
            )
        for r in rows:
            payload = r["payload"] if isinstance(r["payload"], dict) else {}
            raw.append(
                {
                    "event_id": str(r["event_id"]),
                    "event_type": r["event_type"],
                    "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else "",
                    "payload": payload,
                    "actor_id": r["actor_id"],
                }
            )
    except Exception as e:  # noqa: BLE001 — صدق: نُعلن الفشل لا نخترع تاريخاً
        return {
            "field_id": field_id,
            "events": [],
            "total_events": 0,
            "error": f"تعذّر جلب الخطّ الزمنيّ: {e}",
        }
    tl = assemble_timeline(
        field_id,
        raw,
        newest_first=newest_first,
        category_filter=[category] if category else None,
    )
    return tl.to_dict()


@router.post("/api/v1/fields/{field_id}/pins")
async def create_pin(
    field_id: str,
    req: PinCreateRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتحقّق من مشاهدة ميدانيّة ثمّ يُديمها (RLS) ويُرجعها مُطبَّعة.

    سابقاً: تحقّق + إرجاع فقط (الحفظ كان على الموبايل offline-first) — فلا قراءة
    خادميّة. الآن يُثبَّت الدبّوس في ``scouting_pins`` (v94، معزول بالمستأجِر) ليُقرأ
    عبر ``GET /api/v1/scouting/pins?field_id=…`` (نظير FieldView). صدق: التحقّق هو
    مصدر الحقيقة؛ الإدامة best-effort — لو تعذّرت القاعدة يبقى الدبّوس صالحاً ويُعلَن
    ``persisted=false`` (لا اختراع نجاح، يبقى المسار offline-first سليماً). idempotent
    عبر ``ON CONFLICT (pin_id) DO NOTHING`` (إعادة المزامنة لا تُكرّر).
    """
    try:
        pin = make_pin(
            req.pin_id,
            field_id,
            req.lat,
            req.lng,
            req.issue_category,
            req.severity,
            req.status,
            req.persistence,
            crop=req.crop,
            issue_code=req.issue_code,
            note_ar=req.note_ar,
            photo_uri=req.photo_uri,
            color=req.color,
            created_by=req.created_by or user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    out = pin.to_dict()
    persisted = await _persist_scouting_pin(user, pin)
    out["persisted"] = persisted
    return out


async def _persist_scouting_pin(user: UserSchema, pin) -> bool:
    """يُثبّت دبّوس مشاهدة في ``scouting_pins`` تحت سياق المستأجِر (RLS) — best-effort.

    يُرجِع ``True`` لو ثُبِّت (أو كان موجوداً مسبقاً idempotent)، و``False`` لو تعذّرت
    القاعدة (لا استثناء يصعد — المسار offline-first يبقى سليماً). SQL بارامتريّ
    بالكامل (لا حقن). ``created_at`` يُمرَّر كنصّ ISO من النواة ويُحوَّل بـ``::timestamptz``.
    """
    if _DB_POOL is None:
        return False
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                "INSERT INTO scouting_pins "
                "(pin_id, tenant_id, field_id, lat, lng, issue_category, severity, "
                " status, persistence, crop, issue_code, note_ar, photo_uri, color, "
                " created_by, created_at) "
                "VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, "
                " $13, $14, $15, $16::timestamptz) "
                "ON CONFLICT (pin_id) DO NOTHING",
                pin.pin_id,
                str(user.tenant_id),
                pin.field_id,
                pin.lat,
                pin.lng,
                pin.issue_category.value,
                pin.severity.value,
                pin.status.value,
                pin.persistence.value,
                pin.crop,
                pin.issue_code,
                pin.note_ar,
                pin.photo_uri,
                pin.color,
                pin.created_by,
                pin.created_at or None,
            )
        return True
    except Exception:  # noqa: BLE001 — إدامة best-effort: تعذّر القاعدة ⇒ persisted=false
        logging.warning("scouting pin persistence failed for pin %s", pin.pin_id)
        return False


@router.post("/api/v1/fields/{field_id}/walk-plan")
def field_walk_plan(
    field_id: str,
    req: WalkPlanRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحوّل وصفة الحقل إلى خطة مشي يدويّة قابلة للتنفيذ."""
    return _build_walk_plan(req).to_dict()


@router.post("/api/v1/fields/{field_id}/walk-plan/pdf")
def field_walk_plan_pdf(
    field_id: str,
    req: WalkPlanRequest,
    user: UserSchema = Depends(get_current_user),
):
    """نفس خطة المشي لكن كـPDF عربي للطباعة وأخذها للحقل."""
    plan = _build_walk_plan(req)
    try:
        pdf_bytes = walk_plan_to_pdf_bytes(plan.to_dict())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="walk_plan_{field_id}.pdf"'},
    )


@router.post("/api/v1/fields/{field_id}/zones")
def field_zones(
    field_id: str,
    req: ZoningRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقترح مناطق إدارة من قيم NDVI عبر k-means."""
    cells = [ZoneCell(c.cell_id, c.value, c.confidence) for c in req.cells]
    try:
        return delineate_zones(cells, n_zones=req.n_zones).to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/api/v1/fields/{field_id}/water-stress-spectral")
async def field_water_stress_spectral(
    field_id: str,
    ndmi: float | None = None,
    msi: float | None = None,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """الإجهاد المائي من مؤشّرات الرطوبة الطيفيّة (ndmi/msi) — جسر للقرار.

    يربط المؤشّرات المحسوبة (كانت بلا ربط) بكشف الإجهاد المائي. إشارة استرشاديّة
    تُدمَج مع ميزان الماء — القياس الأرضي يبقى المرجّح. صدق: لا مؤشّر → unknown.

    field-scoped: يتحقّق أنّ الحقل يخصّ المستأجِر (404 وإلّا) عبر RLS. المؤشّرات
    تُمرَّر كمعاملات حاليّاً (جلبها من الراستر لكلّ حقل بند لاحق).
    """
    from core.engines.spectral_stress_bridge import fuse_water_stress

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("التحقّق من الحقل", e) from e

    return {
        "field_id": field_id,
        "indices_source": "query_params",  # صدق: لم تُجلَب من الراستر بعد
        **fuse_water_stress(ndmi=ndmi, msi=msi),
    }


@router.get("/api/v1/fields/{field_id}/state")
async def field_canonical_state(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """الحالة القانونيّة الموحّدة للحقل — مصدر حقيقة واحد للقرار/التنبيه/التوصية.

    يجمع نضارة NDVI (imagery_automation_fields) + التربة (soil_lab_tests) + الطقس
    (weather_automation_cache) من قاعدة المنصّة، يشتقّ الثقة من نضارة NDVI، يركّبها
    في validity (valid/degraded/conflicted/insufficient) + نمط التنفيذ، **ويحفظ
    النتيجة في إسقاط field_state (read model)** كي يقرأها بقيّة المستهلكين.
    صدق: غياب مصدر ⇒ عمره None ⇒ حالة «بيانات ناقصة» لا نضارة مُلفَّقة. 503 عند
    تعذّر القاعدة. يُرجِع inputs المستخدَمة للتدقيق.
    """
    from api.field_state_projection import recompute_field_state

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            result = await recompute_field_state(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة الحالة القانونيّة للحقل", e) from e

    return result["state"]


@router.get("/api/v1/fields/{field_id}/alerts/derived")
async def field_alerts_derived(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تنبيهات الحقل المُشتقّة من الحالة القانونيّة الموحّدة (للعرض فقط).

    tenant-scoped (FIELD_VIEW): يستدعي recompute_field_state ثمّ يشتقّ تنبيهات صادقة
    من الحقائق الزراعيّة (ملوحة تربة حرجة) ونمط التنفيذ (blocked/human_review ⇒
    «القرار يحتاج مراجعة بشريّة»). لا يكتب في جدول alerts (اشتقاق للعرض). صدق: غياب
    الحقائق ⇒ {"alerts": []} لا تنبيه مُلفَّق. 404 إن غاب الحقل، 503 إن تعذّرت القاعدة.
    """
    from api.field_state_projection import _derive_alerts_from_state, recompute_field_state

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            state = (await recompute_field_state(conn, field_id))["state"]
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("اشتقاق تنبيهات الحقل من الحالة القانونيّة", e) from e

    return {"field_id": field_id, "alerts": _derive_alerts_from_state(state)}
