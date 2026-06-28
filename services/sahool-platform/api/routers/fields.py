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
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

# validate_field_geometry يُستورَد من مصدره مباشرةً (كان main يعيد تصديره، لكنه صار
# يتيماً فيه بعد نقل _persist_field إلى هنا — تفكيك B1).
from api.alert_models import AlertEvaluateResponse

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
from api.geospatial_integrity import validate_field_geometry
from api.gis_geometry_guard import geometry_metadata, guard_field_geometry

# بقيّة التبعيّات/النماذج/المساعِدات المشتركة تبقى في api.main وتُستورَد من هناك.
from api.main import (
    CommandStore,
    GeometryValidateRequest,
    NitrogenRxRequest,
    Permission,
    RotationRequest,
    TrueUpRequest,
    UserSchema,
    YieldEstimateRequest,
    ZoningRequest,
    _assert_field_in_tenant,
    _build_versioned_update,
    _db_unavailable,
    _emit_domain_event,
    _evaluate_field_alerts_persist,
    _idem_key,
    _idempotent,
    _parse_date,
    _reverse_geocode,
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

# منطق نقيّ مُستخرَج من هذا الملف (تقليص الوحدة) — يُعاد استيراده كي يبقى متاحاً
# كسمة للوحدة (اختبارات tests_v9/test_field_conflict_payload تصل إليه عبر fields).
from api.routers.field_logic import (
    _conflict_changed_fields,  # noqa: F401 — يُصدَّر مجدّداً للاختبارات
    _field_merge_plan,
    _guard_merge_split_geometry,
)
from api.routers.field_request_models import (
    ChildField,
    FieldImageryBackfillRequest,
    FieldImageryRefreshRequest,
    FieldMergeRequest,
    FieldSplitRequest,
)

# ملاحظة: نماذج/مساعدات المواسم (api.season_models) لم تَعُد تُستورَد هنا بعد نقل
# معالِجات المواسم الثلاث إلى api/routers/field_seasons.py (تفكيك تدريجيّ للملفّ).
from api.spatial_sync import mark_raster_cache_stale, save_field_geometry_revision
from api.trueup import TrueUpInput, TrueUpStatus
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
        metadata=geometry_metadata(field_revision=1),
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


@router.post("/api/v1/fields/{field_id}/imagery/backfill")
async def field_imagery_backfill(
    field_id: str,
    req: FieldImageryBackfillRequest | None = None,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """Tenant-verified proxy for historical imagery backfill on raster-service.

    raster's ``/v1/fields/{id}/imagery/backfill`` is guarded by ``_require_service_token``
    and demands ``clip_polygon_geojson``. The browser cannot inject the agent token
    (nginx only forwards JWT to ``/api/raster``), so a direct call always 401s. This
    route authenticates the user, injects the authoritative field geometry as the clip
    polygon, attaches ``X-Agent-Token`` server-side, and forwards. No fabricated data:
    raster still searches real STAC scenes and only reports COGs it actually produced.
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

        import os as _os

        import httpx as _httpx

        body: dict[str, Any] = req.model_dump(exclude_none=True) if req else {}
        # الخادم مصدر الحقيقة للهندسة: نحقن حدود الحقل المُتحقَّقة (لا نثق بالعميل).
        body["clip_polygon_geojson"] = guarded.geometry
        if not body.get("indices"):
            body["indices"] = ["ndvi", "ndmi", "savi", "evi"]

        raster_url = _os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip(
            "/"
        )
        headers = {
            "X-Agent-Token": _os.getenv("SAHOOL_AGENT_TOKEN", ""),
            "X-Tenant-Id": str(user.tenant_id),
        }
        async with _httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{raster_url}/v1/fields/{field_id}/imagery/backfill",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("سحب الصور التاريخيّة للحقل", e) from e


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
