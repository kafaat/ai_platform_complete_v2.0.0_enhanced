"""routers/fields.py — مسارات الحقل (Field-scoped)
======================================================================
شريحة من تفكيك ``py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
``X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``py``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from fastapi.responses import Response
from raster_field_runtime import (
    _REQ_TENANT,
    _TRANSPARENT_PNG,
    LANDSAT_DERIVED_INDICES,
    LANDSAT_DIRECT_RASTER_INDICES,
    LANDSAT_DUPLICATE_SENTINEL_INDICES,
    LANDSAT_UNIQUE_INDICES,
    NDVI_HIGH_QUALITY_CLEAR_PCT,
    NDVI_PULL_MIN_CLEAR_PCT,
    NDVI_PULL_MIN_SPACING_DAYS,
    NDVI_PULL_TARGET_SPACING_DAYS,
    SENTINEL_COLLECTION,
    TITILER_URL,
    BandMapping,
    FieldChangeRequest,
    GeoParquetExportRequest,
    HistoricalBackfillRequest,
    IndicatorKind,
    JobStatus,
    PrescriptionRequest,
    ProcessCdseRequest,
    ProcessFromStacRequest,
    ProcessRequest,
    SourceFormat,
    _backfill_date_range,
    _bbox_from_geojson,
    _display_index,
    _field_layers,
    _grid_from_cog,
    _jobs,
    _layers,
    _month_windows,
    _normalize_index,
    _obs_inc,
    _pixel_quality,
    _process_backfill_scene_cdse,
    _public_cog_url,
    _read_tile_cache,
    _real_field_grid,
    _require_field_tenant,
    _require_service_token,
    _resolve_field_layer,
    _run_cdse_processing,
    _run_processing,
    _safe_raster_source,
    _select_backfill_scenes_by_policy,
    _stac_search,
    _stac_search_landsat_unique,
    _tile_cache_key,
    _upload_dir,
    _write_tile_cache,
    logger,
    object_store,
)

router = APIRouter()


@router.get("/gis/admin-boundaries")
async def gis_admin_boundaries(
    level: int = Query(1, ge=1, le=2),
    bbox: str | None = Query(None, description="minx,miny,maxx,maxy (4326) — مقصوص، محدود المساحة"),
    x_agent_token: str = Header(None),
):
    """A6/A7: قراءة طبقة الحدود المشتركة (GeoJSON + ST_AsSVG) + مرجعيّتها — لخريطة الطباعة المتجهة.

    **استهلاك shared-reference معلَن** (لا تسلّل جدول غير مملوك — راجع gis_boundaries_read). توكن خدمة
    إلزاميّ؛ bbox مُطهَّر (أرقام + سقف مساحة — حارس ضدّ الوحشيّ يجرّ الطبقة). fail-closed: بلا قاعدة ⇒ 503.
    """
    _require_service_token(x_agent_token)  # نمط الشقيقات — منع كشف غير مصرّح
    import gis_boundaries_read as gbr

    try:
        clean_bbox = gbr.sanitize_bbox(bbox)
    except ValueError as e:
        raise HTTPException(400, f"bbox غير صالح: {e}") from None

    import db_persist as _dbp

    conn = await _dbp._connect()
    try:
        sql, params = gbr.admin_boundaries_query(level, clean_bbox)
        rows = await conn.fetch(sql, *params)
        prov = await conn.fetchrow(gbr.source_provenance_query(level), int(level))
    except Exception as e:  # noqa: BLE001 — قاعدة ⇒ 503 لا 500
        raise HTTPException(503, "تعذّرت قراءة الحدود الإداريّة") from e
    finally:
        await conn.close()
    return {
        "level": level,
        "features": [dict(r) for r in rows],
        "source": dict(prov) if prov else None,
        "count": len(rows),
    }


def _async_backfill_enabled() -> bool:
    """راية backfill اللاتزامنيّ (v5-F1/F2 · v6-F1/F2): يُنشئ تشغيلة ويعيد run_id فوراً
    ويُخرج مسح STAC الشهريّ من مسار الطلب إلى عامل الفحص. خامل حتّى التحقّق التكامليّ."""
    return str(os.getenv("RASTER_ASYNC_BACKFILL_ENABLED", "false")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@router.post("/v1/fields/{field_id}/process-from-stac")
async def process_from_stac(
    field_id: str,
    req: ProcessFromStacRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    """يجسر الاستيراد→المعالجة: يكدّس COGs المنفصلة لنطاقات STAC في VRT
    (عبر /vsicurl/ للبعيد) ثم يشغّل نفس مسار /process (قصّ→مؤشّر→COG→persist).

    مناسب للمزوّد بلا مفتاح (Element84): استدعِ /imagery/best لجلب band hrefs،
    ثمّ مرّرها هنا. خلفيّة — يُرجِع job_id.
    """
    _require_service_token(x_agent_token)
    import stac_vrt

    # كلّ href يُتحقَّق منه (traversal/SSRF) قبل بناء الـVRT.
    safe_hrefs = {k: _safe_raster_source(v) for k, v in (req.band_hrefs or {}).items()}
    try:
        # الـVRT يُكتَب تحت UPLOAD_DIR كي يقبله حارس المصدر (_safe_raster_source) —
        # كتابته في /tmp مباشرة كانت تُفشِل المعالجة بـ400 (خارج المجلّد المسموح).
        vrt_path, index_map = stac_vrt.build_band_vrt(safe_hrefs, out_dir=_upload_dir())
    except Exception as e:  # noqa: BLE001 — مدخل غير صالح/نطاق غير مقروء
        raise HTTPException(400, f"تعذّر بناء VRT من نطاقات STAC: {e}") from e

    band_kwargs = {k: v for k, v in index_map.items() if k in BandMapping.model_fields}
    preq = ProcessRequest(
        raster_url=vrt_path,
        indicator=req.indicator,
        bands=BandMapping(**band_kwargs),
        field_id=field_id,
        tenant_id=req.tenant_id,
        source_format=req.source_format,
        scene_id=req.scene_id,
        capture_datetime=req.capture_datetime,
        apply_cloud_mask=req.apply_cloud_mask,
        clip_polygon_geojson=req.clip_polygon_geojson,
        geometry_revision=req.geometry_revision,  # v143: نَسَب هندسة الحقل
    )
    job_id = f"stac_{uuid.uuid4().hex[:12]}"
    _jobs.set(
        job_id,
        {
            "job_id": job_id,
            "status": JobStatus.pending,
            "progress_pct": 0,
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    background_tasks.add_task(_run_processing, job_id, preq)
    return {
        "job_id": job_id,
        "status": JobStatus.pending,
        "bands": index_map,
        "raster_url": vrt_path,
    }


async def _persist_selected_stac_scenes(tenant_id: str, scenes: list[dict]) -> None:
    """FINDING-009: يستمرّ المشاهد المُختارة في stac_item_registry (كان بلا كاتب).

    best-effort في مهمّة خلفيّة — لا يؤخّر ردّ backfill ولا يُفشله عند غياب القاعدة."""
    import db_persist

    for scene in scenes:
        sid = scene.get("item_id")
        if not sid:
            continue
        await db_persist.insert_stac_item(
            tenant_id=tenant_id,
            scene_id=sid,
            collection=SENTINEL_COLLECTION,
            captured_at=scene.get("datetime"),
            bbox=scene.get("bbox"),
            cloud_pct=scene.get("cloud_cover_pct"),
            quality_score=scene.get("quality_score"),
            assets={
                "bands": scene.get("bands_urls"),
                "thumbnail": scene.get("thumbnail_url"),
                "preview": scene.get("preview_url"),
            },
            raw_item=scene,
        )


@router.post("/v1/fields/{field_id}/imagery/backfill")
async def field_historical_backfill(
    field_id: str,
    req: HistoricalBackfillRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    """Create a switchable historical imagery backfill plan/job for a field.

    Presets:
      • auto_12_months: run automatically after creating a field.
      • extended_3_years: user/admin toggle for season comparison.
      • research_5_years: enterprise/research toggle.
      • custom: explicit from/to or months.

    The endpoint searches Sentinel-2 scenes month-by-month, selects the least-cloudy
    scenes per month, and schedules one processing job per (scene × index). When
    dry_run=true it returns the plan only, which is useful for UI cost previews.
    """
    _require_service_token(x_agent_token)
    await _require_field_tenant(field_id)

    if not req.indices:
        raise HTTPException(400, "indices مطلوبة")
    source = (req.source or "sentinel-2").strip().lower().replace("_", "-")
    is_landsat_thermal = source in {
        "landsat",
        "landsat-thermal",
        "landsat-unique",
        "landsat-thermal-unique",
    }
    if is_landsat_thermal:
        unsupported = [i.value for i in req.indices if i.value not in LANDSAT_UNIQUE_INDICES]
        if unsupported:
            raise HTTPException(
                400,
                "Landsat في Sahool مخصّص للمؤشرات الحرارية الفريدة فقط؛ "
                f"المؤشرات المكررة مع Sentinel-2 مرفوضة: {unsupported}",
            )
        non_direct = [i.value for i in req.indices if i.value not in LANDSAT_DIRECT_RASTER_INDICES]
        if non_direct and not req.dry_run:
            raise HTTPException(
                422,
                "هذه مؤشرات مشتقة لا تُسحب كراستر مباشر من Landsat. اسحب lst أولاً، "
                f"ثم اشتقها محلياً مع الطقس/NDVI: {non_direct}",
            )
    else:
        unsupported = [
            i.value
            for i in req.indices
            if i
            not in {
                IndicatorKind.ndvi,
                IndicatorKind.ndmi,
                IndicatorKind.savi,
                IndicatorKind.evi,
                IndicatorKind.gndvi,
                IndicatorKind.ndre,
                IndicatorKind.reci,
                IndicatorKind.gci,
                IndicatorKind.arvi,
                IndicatorKind.sipi,
                IndicatorKind.nbr,
                IndicatorKind.ccci,
                IndicatorKind.vari,
                IndicatorKind.gli,
                IndicatorKind.bsi,
                IndicatorKind.msi,
                IndicatorKind.msavi,
                # طبقات مائيّة/ملوحة Sentinel-2 ظاهرة في MapHub ويجب أن تُحفظ تاريخياً عند طلبها.
                IndicatorKind.ndwi,
                IndicatorKind.ndsi,
                # الصورة الخام (truecolor) تُحفَظ الآن كـCOG RGBA (مسار precomputed مخصّص)
                # فتُقبَل في الـbackfill — فيخدمها /tiles المحفوظ للحقول المُجهَّزة.
                IndicatorKind.truecolor,
            }
        ]
        if unsupported:
            raise HTTPException(400, f"مؤشّرات غير مناسبة للـbackfill البصري: {unsupported}")

    clip = req.clip_polygon_geojson
    bbox = _bbox_from_geojson(clip)
    if bbox is None:
        raise HTTPException(400, "clip_polygon_geojson مطلوب لاشتقاق bbox وقصّ الصور على حدود الحقل")

    start, end, months = _backfill_date_range(req)

    # v5-F1/F2 · v6-F1/F2: المسار اللاتزامنيّ (خلف راية). أنشئ تشغيلة backfill وأعِد
    # run_id فوراً بلا مسح STAC في مسار الطلب (يتفادى مهلة proxy 60s على النوافذ
    # الطويلة). عامل الفحص يمسح ويجدول لاتزامنيّاً بمفتاح idempotency. dry_run يبقى
    # متزامناً (معاينة). فشل الإنشاء (لا جدول) ⇒ تدهور لطيف للمسار المتزامن أدناه.
    if _async_backfill_enabled() and not req.dry_run:
        import db_persist as _dbp

        _async_tenant = req.tenant_id or _REQ_TENANT.get()
        run_id = await _dbp.insert_backfill_run(
            tenant_id=str(_async_tenant) if _async_tenant else None,
            field_id=field_id,
            preset=req.preset.value,
            from_date=start.strftime("%Y-%m-%d"),
            to_date=end.strftime("%Y-%m-%d"),
            months=months,
            indices=[i.value for i in req.indices],
            max_cloud_pct=req.max_cloud_pct,
            geometry_revision=getattr(req, "geometry_revision", None),
            clip_polygon_geojson=clip,
            apply_cloud_mask=req.apply_cloud_mask,
            limit_per_month=req.limit_per_month,
            source="landsat-thermal" if is_landsat_thermal else "sentinel-2",
        )
        if run_id is not None:
            logger.info(
                "historical_backfill_run created field_id=%s run_id=%s months=%s (async)",
                field_id,
                run_id,
                months,
            )
            return {
                "field_id": field_id,
                "preset": req.preset.value,
                "mode": "async",
                "run_id": run_id,
                "status": "planned",
                "period": {
                    "from": start.strftime("%Y-%m-%d"),
                    "to": end.strftime("%Y-%m-%d"),
                    "months": months,
                },
                "indices": [i.value for i in req.indices],
                "source": "landsat-thermal" if is_landsat_thermal else "sentinel-2",
                "message": "تمّ إنشاء تشغيلة backfill؛ يُنفّذها عامل الفحص لاتزامنيّاً.",
            }
        # v7-#3: تحصين الاحتياطيّ — حين تكون الراية مُفعَّلة لكنّ إنشاء التشغيلة فشل (جدول
        # v144 مفقود/قاعدة متعذّرة) لا نرتدّ صامتاً للمسار المتزامن الحاجب للطلب (يُعيد
        # مشكلة v5-F1/F2). نفشل مُغلَقاً بـ503 صريح — التشخيص أوضح من مسح STAC بطيء.
        raise HTTPException(
            503,
            "تعذّر إنشاء تشغيلة backfill اللاتزامنيّة (تحقّق من ترحيل v144/القاعدة)؛ "
            "المسار المتزامن مُعطَّل تحت RASTER_ASYNC_BACKFILL_ENABLED.",
        )

    windows = _month_windows(start, end)
    selected_scenes: list[dict] = []
    monthly: list[dict] = []
    for w_start, w_end in windows:
        if is_landsat_thermal:
            search = await _stac_search_landsat_unique(
                bbox,
                w_start.strftime("%Y-%m-%dT00:00:00Z"),
                w_end.strftime("%Y-%m-%dT23:59:59Z"),
                req.max_cloud_pct,
                limit=max(24, req.limit_per_month * 6),
            )
        else:
            try:
                search = await _stac_search(
                    bbox,
                    w_start.strftime("%Y-%m-%dT00:00:00Z"),
                    w_end.strftime("%Y-%m-%dT23:59:59Z"),
                    req.max_cloud_pct,
                    limit=max(24, req.limit_per_month * 6),
                    geometry=clip,  # CDSE catalog يستعمل intersects للقصّ الدقيق على الحقل
                )
            except TypeError as e:
                if "unexpected keyword argument 'geometry'" not in str(e):
                    raise
                # توافق اختبارات/بدائل قديمة monkeypatch لا تقبل geometry. الإنتاج يستخدم
                # التوقيع الجديد، وهذا fallback لا يغيّر المسار الحقيقي.
                search = await _stac_search(
                    bbox,
                    w_start.strftime("%Y-%m-%dT00:00:00Z"),
                    w_end.strftime("%Y-%m-%dT23:59:59Z"),
                    req.max_cloud_pct,
                    limit=max(24, req.limit_per_month * 6),
                )
        items = _select_backfill_scenes_by_policy(
            search.get("items", []),
            indices=[i.value for i in req.indices],
            max_cloud_pct=req.max_cloud_pct,
            limit=req.limit_per_month,
        )
        selected_scenes.extend(items)
        monthly.append(
            {
                "month": w_start.strftime("%Y-%m"),
                "scenes_found": search.get("count", len(search.get("items", []))),
                "scenes_selected": len(items),
                "selected_scene_ids": [it.get("item_id") for it in items],
            }
        )

    job_ids: list[str] = []
    scheduled: list[dict] = []
    tenant_id = req.tenant_id or _REQ_TENANT.get()
    # FINDING-009: استمرار المشاهد المُختارة في stac_item_registry (خلفيّة، best-effort).
    if not req.dry_run and tenant_id and selected_scenes:
        background_tasks.add_task(
            _persist_selected_stac_scenes, str(tenant_id), list(selected_scenes)
        )
    for scene in selected_scenes:
        # For Element84 Sentinel-2 COGs, build a VRT lazily in the background via the
        # same processing core contract. The direct job stores enough provenance to re-run.
        for indicator in req.indices:
            job_id = f"backfill_{uuid.uuid4().hex[:12]}"
            scheduled_item = {
                "job_id": job_id,
                "field_id": field_id,
                "tenant_id": tenant_id,
                "index": indicator.value,
                "scene_id": scene.get("item_id"),
                "capture_datetime": scene.get("datetime"),
                "cloud_cover_pct_scene": scene.get("cloud_cover_pct"),
                "dry_run": req.dry_run,
            }
            scheduled.append(scheduled_item)
            if req.dry_run:
                continue
            _jobs.set(
                job_id,
                {
                    **scheduled_item,
                    "status": JobStatus.pending,
                    "progress_pct": 0,
                    "created_at": datetime.now(UTC).isoformat(),
                    "job_type": "historical_backfill",
                    "preset": req.preset.value,
                },
            )

            # Reuse the same VRT/process path without issuing an HTTP subrequest.
            # v6-audit F3: دالّة **متزامنة** عمداً — جسمها كلّه I/O ثقيل متزامن
            # (build_band_vrt + _run_processing، لا await). FastAPI يُشغّل مهامّ الخلفيّة
            # المتزامنة في threadpool، بينما `async def` كان يُنفَّذها على حلقة الأحداث
            # فيحجب باقي طلبات raster (tilejson/health) أثناء معالجة COG.
            def _run_scene_job(jid=job_id, sc=scene, ind=indicator):
                try:
                    import stac_vrt

                    ind_value = ind.value if hasattr(ind, "value") else str(ind)
                    if (sc.get("provider") or "").startswith("landsat") or sc.get("thermal_urls"):
                        if ind_value != "lst":
                            raise RuntimeError("landsat_derived_index_requires_lst_weather_ndvi")
                        thermal_url = (sc.get("thermal_urls") or {}).get("lst")
                        if not thermal_url:
                            raise RuntimeError("landsat_lst_asset_missing")
                        preq = ProcessRequest(
                            tenant_id=tenant_id,
                            field_id=field_id,
                            raster_url=_safe_raster_source(thermal_url),
                            indicator=IndicatorKind.lst,
                            source_format=SourceFormat.landsat8,
                            bands=BandMapping(),
                            precomputed_index=True,
                            clip_polygon_geojson=clip,
                            apply_cloud_mask=False,
                            scene_id=sc.get("item_id"),
                            capture_datetime=sc.get("datetime"),
                            provider="landsat-element84",
                            geometry_revision=getattr(req, "geometry_revision", None),
                        )
                        _run_processing(jid, preq)
                        return

                    # التحويل إلى CDSE: مشهد كتالوج Copernicus (بلا bands_urls) يُعالَج
                    # خادميّاً عبر Process API (لا VRT من نطاقات Element84).
                    if not (sc.get("bands_urls") or {}):
                        _process_backfill_scene_cdse(
                            sc,
                            ind_value,
                            field_id,
                            tenant_id,
                            clip,
                            getattr(req, "geometry_revision", None),
                            jid,
                        )
                        return

                    safe_hrefs = {
                        k: _safe_raster_source(v)
                        for k, v in (sc.get("bands_urls") or {}).items()
                        if v
                    }
                    # تحت UPLOAD_DIR كي يقبله _safe_raster_source — كتابة الـVRT في
                    # /tmp أسقطت كلّ مهامّ backfill بـHTTPException 400 (بلاغ 2026-07-04).
                    vrt_path, index_map = stac_vrt.build_band_vrt(safe_hrefs, out_dir=_upload_dir())
                    preq = ProcessRequest(
                        tenant_id=tenant_id,
                        field_id=field_id,
                        raster_url=vrt_path,
                        indicator=ind,
                        source_format=SourceFormat.sentinel2_l2a,
                        bands=BandMapping(
                            **{k: v for k, v in index_map.items() if k in BandMapping.model_fields}
                        ),
                        clip_polygon_geojson=clip,
                        apply_cloud_mask=req.apply_cloud_mask,
                        scene_id=sc.get("item_id"),
                        capture_datetime=sc.get("datetime"),
                        provider="element84",
                        # v8-F7: النَّسَب — مرّر مراجعة الهندسة في المسار المتزامن أيضاً
                        # (كان يغفلها ⇒ أصول backfill بـgeometry_revision=NULL تُضعِف
                        # كشف التقادم والتحليل الجنائيّ عند تغيّر حدود الحقل).
                        geometry_revision=getattr(req, "geometry_revision", None),
                    )
                    _run_processing(jid, preq)
                except Exception as e:  # noqa: BLE001
                    # توحيد main↔cert (#542): لا نُسرّب نصّ الاستثناء للعميل — رمز عامّ،
                    # والسجلّ الداخلي يحمل النوع (+ status/detail لـHTTPException —
                    # نصّنا المتحكَّم به؛ النوع وحده أخفى سبب فشل backfill 2026-07-04).
                    _http = f" [{e.status_code}] {e.detail}" if isinstance(e, HTTPException) else ""
                    logger.warning(
                        "scene job %s فشل أثناء معالجة المشهد: %s%s",
                        jid,
                        type(e).__name__,
                        _http,
                    )
                    j = _jobs.get(jid) or {"job_id": jid}
                    j.update(
                        {
                            "status": JobStatus.failed,
                            "error_message": "scene_processing_failed",
                            "finished_at": datetime.now(UTC).isoformat(),
                        }
                    )
                    _jobs.set(jid, j)

            background_tasks.add_task(_run_scene_job)
            job_ids.append(job_id)

    # v5-audit F8: ملخّص فحص backfill منظَّم — «job completed» الفرديّة لا تكشف نطاق
    # الفحص (كم شهراً مُسِح · كم مشهداً اختير · كم مهمّة جُدولت) للتشخيص/التدقيق.
    logger.info(
        "historical_backfill_scan completed field_id=%s months_requested=%s months_scanned=%s "
        "scenes_selected=%s jobs_scheduled=%s dry_run=%s",
        field_id,
        months,
        len(windows),
        len(selected_scenes),
        len(job_ids),
        req.dry_run,
    )

    return {
        "field_id": field_id,
        "preset": req.preset.value,
        "period": {
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "months": months,
        },
        "indices": [i.value for i in req.indices],
        "source": "landsat-thermal" if is_landsat_thermal else "sentinel-2",
        "landsat_policy": (
            {
                "direct_raster_indices": sorted(LANDSAT_DIRECT_RASTER_INDICES),
                "derived_indices": sorted(LANDSAT_DERIVED_INDICES),
                "excluded_duplicate_sentinel_indices": sorted(LANDSAT_DUPLICATE_SENTINEL_INDICES),
            }
            if is_landsat_thermal
            else None
        ),
        "max_cloud_pct": req.max_cloud_pct,
        "min_clear_scene_pct": 100 - req.max_cloud_pct,
        "high_quality_clear_pct": NDVI_HIGH_QUALITY_CLEAR_PCT,
        "min_scene_spacing_days": NDVI_PULL_MIN_SPACING_DAYS,
        "target_scene_spacing_days": NDVI_PULL_TARGET_SPACING_DAYS,
        "limit_per_month": req.limit_per_month,
        "dry_run": req.dry_run,
        "months_scanned": len(windows),
        "scenes_selected": len(selected_scenes),
        "jobs_scheduled": len(job_ids),
        "monthly": monthly,
        "jobs": scheduled,
        "policy": {
            "auto": "auto_12_months",
            "extended": "extended_3_years",
            "research": "research_5_years",
            "custom": "from_date/to_date or months",
        },
    }


@router.get("/v1/fields/{field_id}/imagery/backfill/{run_id}")
async def field_backfill_run_status(field_id: str, run_id: int):
    """حالة تشغيلة backfill اللاتزامنيّة + عدّاداتها (v10-F10).

    يُتيح للواجهة استطلاع التقدّم الحقيقيّ بدل «نجاح» أعمى: الحالة
    (planned/searching/processing/completed/completed_with_errors/failed) + عدّادات
    persisted/failed/skipped + تجميع حالات العناصر + آخر خطأ. مُصفّى بالمستأجِر."""
    await _require_field_tenant(field_id)
    import db_persist as _dbp

    status = await _dbp.get_backfill_run_status(run_id, tenant_id=_REQ_TENANT.get())
    if status is None:
        raise HTTPException(404, "تشغيلة backfill غير موجودة ضمن هذا المستأجِر/الحقل")
    if status.get("field_id") and status["field_id"] != field_id:
        raise HTTPException(404, "تشغيلة backfill لا تخصّ هذا الحقل")
    return status


@router.post("/v1/fields/{field_id}/geometry/versions")
async def create_field_geometry_version(
    field_id: str,
    geometry: dict,
    valid_from: str | None = Query(None),
    reason: str | None = Query("manual_snapshot"),
    x_agent_token: str = Header(None),
):
    """Persist a field geometry snapshot for reproducible historical analytics."""
    _require_service_token(x_agent_token)
    await _require_field_tenant(field_id)
    tenant_id = _REQ_TENANT.get()
    import db_persist

    version_id = await db_persist.insert_field_geometry_version(
        field_id=field_id,
        tenant_id=tenant_id,
        geometry=geometry,
        valid_from=valid_from,
        reason=reason,
    )
    return {
        "field_id": field_id,
        "tenant_id": tenant_id,
        "version_id": version_id,
        "persisted": bool(version_id),
    }


@router.post("/v1/fields/analytics/geoparquet/export")
async def export_field_analytics_geoparquet(
    req: GeoParquetExportRequest, x_agent_token: str = Header(None)
):
    """Export field analytics as GeoParquet when optional deps exist, else NDJSON.

    GeoParquet requires pyarrow/shapely/geopandas in the production image. The
    fallback writes an explicit NDJSON file instead of mislabeling a non-GeoParquet
    artifact.
    """
    _require_service_token(x_agent_token)
    tenant_id = req.tenant_id or _REQ_TENANT.get()
    import json as _json

    import db_persist

    rows = await db_persist.fetch_field_analytics_for_export(
        tenant_id=tenant_id, field_ids=req.field_ids
    )
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in req.output_name)
    out_dir = os.path.join(_upload_dir(), "exports", str(tenant_id or "unknown"))
    os.makedirs(out_dir, exist_ok=True)
    try:
        import geopandas as gpd  # type: ignore
        from shapely.geometry import shape  # type: ignore

        gdf = gpd.GeoDataFrame(
            [
                {k: v for k, v in row.items() if k != "geometry"}
                | {"geometry": shape(row["geometry"])}
                for row in rows
                if row.get("geometry")
            ],
            crs="EPSG:4326",
        )
        path = os.path.join(out_dir, f"{safe_name}.parquet")
        gdf.to_parquet(path, index=False)
        return {"format": "GeoParquet", "path": path, "rows": len(gdf), "crs": "EPSG:4326"}
    except Exception as e:  # noqa: BLE001
        path = os.path.join(out_dir, f"{safe_name}.ndjson")
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(_json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return {
            "format": "NDJSON",
            "path": path,
            "rows": len(rows),
            "geo_parquet_ready": False,
            "reason": type(e).__name__,
        }


@router.post("/v1/fields/{field_id}/process-cdse")
async def process_cdse(
    field_id: str,
    req: ProcessCdseRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    """يحسب مؤشّرات الحقل عبر CDSE (المزوّد الافتراضيّ الأقوى). خلفيّة، يُرجِع job_id.

    صدق: بلا اعتمادات CDSE (``CDSE_CLIENT_ID``/``SECRET`` أو ``CDSE_ENABLED=false``) ⇒
    ``available=false`` (200، لا خطأ) كي يسقط المنسّق إلى Element84 بصمت — لا توقّف ولا تلفيق.
    """
    _require_service_token(x_agent_token)
    import cdse_client
    import imagery_source_gate

    if not cdse_client.is_configured():
        return {
            "provider": "cdse",
            "available": False,
            "queued": False,
            "note_ar": "CDSE غير مُهيّأ (لا CDSE_CLIENT_ID/SECRET) — يسقط المنسّق إلى Element84.",
        }
    # satellite_cdse activation gate — the SINGLE authorization for running CDSE processing. When
    # enforced and the gate is not effectively enabled (disabled/degraded/revoked/evaluating, or
    # unreachable), refuse to queue CDSE work and report available=false so the orchestrator drops
    # to Element84 — identical contract to the unconfigured branch above. No side path to CDSE.
    gate_decision = None
    if imagery_source_gate.enforce_enabled():
        gate_decision = await imagery_source_gate.resolve_active_source()
        if not gate_decision.use_cdse:
            return {
                "provider": "cdse",
                "available": False,
                "queued": False,
                "gate": gate_decision.evidence(),
                "note_ar": "بوّابة satellite_cdse غير مُفعّلة لهذه البيئة — يسقط المنسّق إلى Element84.",
            }
    if not req.bbox or len(req.bbox) != 4:
        raise HTTPException(400, "bbox مطلوب [west,south,east,north] (EPSG:4326).")
    if not req.indicators:
        raise HTTPException(400, "indicators مطلوبة (مؤشّر واحد على الأقلّ).")
    job_id = f"cdse_{uuid.uuid4().hex[:12]}"
    job_record = {
        "job_id": job_id,
        "status": JobStatus.pending,
        "progress_pct": 0,
        "created_at": datetime.now(UTC).isoformat(),
        "indicators": list(req.indicators),
        "provider": "cdse",
    }
    if gate_decision is not None:
        # Bind the job to the exact activation generation it was authorized under (proof #4/#5):
        # a later revoke/expiry bumps the generation, so the persisted evidence is non-repudiable.
        job_record["gate"] = gate_decision.evidence()
    _jobs.set(job_id, job_record)
    background_tasks.add_task(_run_cdse_processing, job_id, field_id, req)
    return {
        "provider": "cdse",
        "available": True,
        "queued": True,
        "job_id": job_id,
        "status": JobStatus.pending,
        "indicators": list(req.indicators),
        "note": "معالجة CDSE خلفيّة — استعلم /jobs/{job_id} (cdse_results + cdse_failed).",
    }


@router.get("/v1/fields/{field_id}/indicator-grid")
async def field_indicator_grid(
    field_id: str,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    grid: int = Query(32, ge=2, le=256),
):
    """شبكة المؤشّر لكلّ بكسل (per-pixel) لخريطة الموبايل.

    يجب وجود COG حقيقي مقصوص للحقل. عند غياب المنتج المرصود أو تعذّر قراءته
    يفشل المسار مغلقاً بـ424؛ لا تُنشأ شبكة تركيبية في أي مسار serving إنتاجي.
    """
    await _require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (ذاكرة + جدول fields)

    # تطبيع اسم المؤشّر المعروض (salinity/NDVU aliases مقبولة للواجهة)
    out_index = _display_index(index)
    index = _normalize_index(index)

    layer = await _resolve_field_layer(field_id, index, date)
    if layer is not None:
        real = _grid_from_cog(layer, out_index, date, grid)
        if real is not None:
            return real

    raise HTTPException(
        424,
        detail={
            "code": "RASTER_INDICATOR_PRODUCT_UNAVAILABLE",
            "message": "لا توجد شبكة مؤشر حقيقية موثقة لهذا الحقل/التاريخ",
            "field_id": field_id,
            "index": out_index,
            "date": date,
            "real_data": False,
            "source": "raster-service",
        },
    )


@router.get("/v1/fields/{field_id}/indicator-observation-bundle")
async def field_indicator_observation_bundle(
    field_id: str,
    indices: str = Query("ndvi,evi,msavi,moisture,msi,ndwi,gndvi"),
    date: str = Query("latest"),
    grid: int = Query(16, ge=2, le=64),
    x_agent_token: str | None = Header(None),
):
    """Return multiple validated indicator observations in one tenant-scoped call.

    The bundle never fabricates products.  Every observation is read from a real COG.
    A mixed-scene bundle is reported explicitly so interpretation consumers can fail
    closed instead of combining observations from different acquisitions.
    """
    _require_service_token(x_agent_token)
    await _require_field_tenant(field_id)
    requested: list[str] = []
    for raw in indices.split(","):
        name = raw.strip().lower()
        if name and name not in requested:
            requested.append(name)
    if not requested:
        raise HTTPException(422, "at least one indicator is required")

    observations: dict[str, dict] = {}
    unavailable: dict[str, str] = {}
    scene_ids: set[str] = set()
    acquisition_dates: set[str] = set()
    # نَسَب الطبقة لمقارنة الحداثة الكاملة في الواجهة (sceneFreshness.ts): نجمع القيم
    # المتمايزة ونكشف المفرد **فقط عند عدم الالتباس** (قيمة واحدة) — لا نخترع حقلاً.
    field_revisions: set[int] = set()
    processing_versions: set[str] = set()
    for public_name in requested:
        internal = _normalize_index(public_name)
        layer = await _resolve_field_layer(field_id, internal, date)
        if layer is None:
            unavailable[public_name] = "product_unavailable"
            continue
        result = _grid_from_cog(layer, _display_index(public_name), date, grid)
        if result is None or not result.get("real_data"):
            unavailable[public_name] = "product_unreadable"
            continue
        observations[public_name] = result
        product = result.get("indicator_product") or {}
        provenance = product.get("provenance") or {}
        scene_id = provenance.get("scene_id") or layer.get("scene_id")
        acquisition = (
            provenance.get("acquisition_datetime")
            or provenance.get("capture_datetime")
            or result.get("date")
        )
        if scene_id:
            scene_ids.add(str(scene_id))
        if acquisition:
            acquisition_dates.add(str(acquisition))
        field_revision = provenance.get("geometry_revision")
        if field_revision is None:
            field_revision = layer.get("geometry_revision")
        if field_revision is not None:
            field_revisions.add(int(field_revision))
        processing_version = provenance.get("processing_version")
        if processing_version:
            processing_versions.add(str(processing_version))

    mixed_scene = len(scene_ids) > 1 or len(acquisition_dates) > 1

    def _single(values: set) -> object | None:
        return next(iter(values)) if len(values) == 1 else None

    return {
        "field_id": field_id,
        "requested": requested,
        "observations": observations,
        "unavailable": unavailable,
        "complete": not unavailable,
        "bundle_consistency": not mixed_scene,
        "mixed_scene": mixed_scene,
        "scene_ids": sorted(scene_ids),
        "acquisition_dates": sorted(acquisition_dates),
        # نَسَب مفرد للواجهة عند اتّساق الحزمة (قيمة واحدة) — وإلّا null بصدق.
        "scene_id": _single(scene_ids),
        "field_revision": _single(field_revisions),
        "processing_version": _single(processing_versions),
        "source": "raster-service",
        "real_data": bool(observations),
        "estimated": False,
    }


@router.get("/v1/fields/{field_id}/pixel")
async def field_pixel_value(
    field_id: str,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    v: str | None = Query(None),
):
    """قيمة المؤشّر عند نقطة واحدة داخل طبقة الحقل.

    لا يخترع قيماً: يجب وجود COG حقيقي للحقل/المؤشّر/التاريخ. يتحقق من ملكية
    الحقل، يرفض النقاط خارج حدود COG المقصوص، ويرجع value + metadata.
    """
    await _require_field_tenant(field_id, hide_existence=True)
    out_index = _display_index(index)
    index = _normalize_index(index)
    layer = await _resolve_field_layer(field_id, index, date)
    if layer is None:
        raise HTTPException(404, "لا توجد طبقة مؤشر حقيقية لهذا الحقل/التاريخ")
    bounds = layer.get("bounds_4326")
    if bounds:
        minx, miny, maxx, maxy = [float(v) for v in bounds]
        if not (minx <= lon <= maxx and miny <= lat <= maxy):
            raise HTTPException(400, "النقطة خارج حدود الحقل/الطبقة")
    try:
        import math as _math

        import rasterio
        from rasterio.warp import transform
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, "rasterio غير متوفر لقراءة قيمة البكسل") from e
    path = object_store.to_gdal_path(layer.get("cog_url") or layer.get("raster_url") or "")
    if not path:
        raise HTTPException(404, "مصدر COG غير موجود")
    try:
        with rasterio.open(path) as src:
            xs, ys = [lon], [lat]
            if src.crs and str(src.crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
                xs, ys = transform("EPSG:4326", src.crs, xs, ys)
            row, col = src.index(xs[0], ys[0])
            if row < 0 or col < 0 or row >= src.height or col >= src.width:
                raise HTTPException(400, "النقطة خارج حدود الحقل/الطبقة")
            value = next(src.sample([(xs[0], ys[0])]))[0]
            nodata = src.nodata
            if (nodata is not None and value == nodata) or not _math.isfinite(float(value)):
                return {
                    "field_id": field_id,
                    "index": out_index,
                    "date": layer.get("acquisition_date") or date,
                    "lat": lat,
                    "lon": lon,
                    "value": None,
                    "valid": False,
                    "reason": "nodata_or_masked",
                    "confidence": 0.0,
                    "quality": "nodata",
                }
            quality = _pixel_quality(layer, float(value))
            return {
                "field_id": field_id,
                "index": out_index,
                "date": layer.get("acquisition_date") or date,
                "lat": lat,
                "lon": lon,
                "value": float(value),
                "valid": True,
                "source": layer.get("source_format") or "raster",
                "confidence": quality["confidence"],
                "quality": quality["quality"],
                "quality_reason": quality["reason"],
                "cloud_pct": quality.get("cloud_pct"),
            }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, "تعذّرت قراءة قيمة البكسل") from e


@router.post("/v1/fields/{field_id}/prescription")
async def field_prescription(
    field_id: str, req: PrescriptionRequest, x_agent_token: str = Header(None)
):
    """وصفة مناطق الإدارة (VRT) من شبكة المؤشّر — سدّ Sprint 5b.

    يبني شبكة المؤشّر من COG حقيقي موثّق فقط، ثم يقسّمها بالكوانتايل إلى
    n_zones مناطق أداء، ويشتقّ معدّلاً
    موصى به لكلّ منطقة إن مُرّر base_rate. يُرجِع المناطق + إحصاء كلّ منطقة
    (pixel_count, pct, value_range) + متوسّط/تباين الحقل.

    يفشل مغلقاً عند غياب المنتج الحقيقي أو فشل بوابة الجودة. المعدّلات إرشاديّة
    وتمر لاحقاً عبر Decision-Service قبل أي أثر تشغيلي.
    """
    _require_service_token(x_agent_token)  # توكن خدمة إلزاميّ (مطابقة الشقيقات — منع كشف الحقول)
    import management_zones as mz

    layer = await _resolve_field_layer(field_id, req.index, req.date)
    if layer is None:
        raise HTTPException(
            424,
            detail={
                "code": "RASTER_INDICATOR_PRODUCT_UNAVAILABLE",
                "message": "لا يمكن إنشاء وصفة دون منتج مؤشر حقيقي",
                "field_id": field_id,
                "index": req.index,
                "date": req.date,
            },
        )
    grid_resp = _grid_from_cog(layer, req.index, req.date, req.grid)
    if grid_resp is None:
        raise HTTPException(
            424,
            detail={
                "code": "RASTER_GRID_READ_FAILED",
                "message": "تعذرت قراءة شبكة المؤشر الحقيقية",
                "field_id": field_id,
                "index": req.index,
                "date": req.date,
            },
        )
    product = grid_resp.get("indicator_product") or {}
    if not (
        grid_resp.get("real_data") is True
        and product.get("source") == "raster-service"
        and product.get("estimated") is False
        and product.get("quality_gate_passed") is True
        and product.get("provenance")
    ):
        raise HTTPException(
            424,
            detail={
                "code": "RASTER_PRODUCT_NOT_DECISION_ELIGIBLE",
                "message": "منتج المؤشر لا يستوفي الحقيقة والجودة والنسب المطلوبة",
                "field_id": field_id,
                "index": req.index,
                "date": req.date,
            },
        )

    pres = mz.prescription_from_grid(
        grid_resp["grid"],
        n_zones=req.n_zones,
        base_rate=req.base_rate,
        strategy=req.strategy,
    )
    return {
        "field_id": field_id,
        "index": req.index,
        "date": grid_resp.get("date", req.date),
        "bbox": grid_resp.get("bbox"),
        "rows": grid_resp.get("rows"),
        "cols": grid_resp.get("cols"),
        "real_data": grid_resp.get("real_data", False),
        "source": grid_resp.get("source", "raster"),
        **pres,
    }


@router.post("/v1/fields/{field_id}/change")
async def field_change(field_id: str, req: FieldChangeRequest, x_agent_token: str = Header(None)):
    """كشف التغيّر المكاني (per-pixel 2D) للحقل بين تاريخين — أين تدهور/تحسّن.

    يبني شبكتي المؤشّر الحقيقيّتين (من COG المقصوص لكلّ تاريخ، نفس مسار
    indicator-grid) ويُمرّرهما لـdetect_change. صدق: إن لم تتوفّر شبكة حقيقيّة
    لأحد التاريخين (لا COG / لا rasterio) يُرجِع real_data=False بلا تغيّر مُفبرَك.
    """
    _require_service_token(x_agent_token)  # توكن خدمة إلزاميّ (مطابقة الشقيقات — منع كشف الحقول)
    grid_a = await _real_field_grid(field_id, req.index, req.date_a, req.grid)
    grid_b = await _real_field_grid(field_id, req.index, req.date_b, req.grid)

    if grid_a is None or grid_b is None:
        missing = [d for d, g in ((req.date_a, grid_a), (req.date_b, grid_b)) if g is None]
        return {
            "field_id": field_id,
            "index": req.index,
            "date_a": req.date_a,
            "date_b": req.date_b,
            "real_data": False,
            "available": False,
            "missing_dates": missing,
            "note": "لا COG مقصوص للحقل لأحد التاريخين — شغّل /process أوّلاً "
            "(لا تغيّر مُفبرَك من بيانات غير متوفّرة)",
        }

    if grid_a["rows"] != grid_b["rows"] or grid_a["cols"] != grid_b["cols"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"أبعاد شبكتي التاريخين مختلفة: "
                f"{grid_a['rows']}×{grid_a['cols']} مقابل {grid_b['rows']}×{grid_b['cols']}"
            ),
        )

    import change_detection as cd

    result = cd.detect_change(
        grid_a["grid"],
        grid_b["grid"],
        index=req.index,
        slight_threshold=req.slight_threshold,
        severe_threshold=req.severe_threshold,
    )
    result.update(
        {
            "field_id": field_id,
            "date_a": grid_a.get("date", req.date_a),
            "date_b": grid_b.get("date", req.date_b),
            "bbox": grid_b.get("bbox") or grid_a.get("bbox"),
            "real_data": True,
            "available": True,
        }
    )
    return result


@router.get("/v1/fields/{field_id}/timeseries")
async def field_timeseries(
    field_id: str,
    index: str = Query("ndvi"),
    dates: str = Query(
        "",
        description="تواريخ مفصولة بفواصل (YYYY-MM-DD). فارغ ⇒ كلّ تواريخ COG المتاحة للحقل.",
    ),
    grid: int = Query(16, ge=2, le=64),
):
    """السلسلة الزمنيّة الحقيقيّة لمتوسّط المؤشّر للحقل عبر التواريخ المتاحة.

    لكلّ تاريخ يبني شبكة المؤشّر من COG الحقل المقصوص ويأخذ متوسّطها الحقيقي
    (real_data). يجمّعها شهريّاً ويحسب الاتّجاه/الشذوذ عبر time_series. صدق:
    لا COG ⇒ نقطة محذوفة (لا تُخترع قيمة)؛ لا نقاط حقيقيّة ⇒ available=False.

    أُزيل x_agent_token (كان مُعلَناً بلا فرض — مسار متصفّح). التفويض عبر ملكيّة الحقل.
    """
    await _require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (DB مصدر الحقيقة + ذاكرة)
    out_index = _display_index(index)
    index = _normalize_index(index)
    requested_dates = [d.strip() for d in dates.split(",") if d.strip()]
    if not requested_dates:
        # كلّ تواريخ الطبقات الحقيقيّة المتاحة للحقل+المؤشّر. نبدأ بالذاكرة، ثم
        # نقرأ raster_assets عند إعادة التشغيل/worker آخر؛ وإلّا يصبح الـtimeline
        # فارغاً رغم وجود COGs مخزّنة. لا نُنشئ نقاطاً، فقط نكتشف التواريخ.
        internal = _normalize_index(index)
        seen: set[str] = set()
        for lid in _field_layers.get(field_id, []):
            lyr = _layers.get(lid)
            if not lyr or not lyr.get("cog_url") or lyr.get("index") != internal:
                continue
            d = lyr.get("acquisition_date")
            if d:
                seen.add(str(d)[:10])
        if not seen:
            try:
                import db_persist

                seen.update(
                    await db_persist.list_asset_dates(
                        field_id, internal, tenant_id=_REQ_TENANT.get()
                    )
                )
            except Exception as e:  # noqa: BLE001 — لا نكسر السلسلة الزمنية عند غياب DB
                logger.warning("raster_assets dates rehydrate skipped (%s): %s", field_id, e)
        requested_dates = sorted(seen)

    points: list[dict] = []
    for date in requested_dates:
        real = await _real_field_grid(field_id, index, date, grid)
        if real is None:
            continue
        points.append(
            {
                "datetime": str(real.get("date") or date)[:10],
                "mean": real["stats"]["mean"],
                # Surface the real per-observation quality so canonical consumers
                # (RS-4 observation timeline) carry measured quality instead of a
                # fabricated 1.0. Keys may be None on legacy layers that predate
                # quality capture — consumers must treat None as "not reported".
                "valid_pixel_ratio": real.get("valid_pixel_ratio"),
                "coverage_ratio": real.get("coverage_ratio"),
                "cloud_pct": real.get("cloud_pct"),
            }
        )

    if not points:
        return {
            "field_id": field_id,
            "index": out_index,
            "available": False,
            "real_data": False,
            "points": [],
            "requested_dates": requested_dates,
            "note": "لا COG مقصوص للحقل في التواريخ المطلوبة — شغّل /process (لا قيم مؤشّر مخترعة)",
        }

    import time_series as ts

    analysis = ts.build_time_series(points, value_key="mean")
    return {
        "field_id": field_id,
        "index": out_index,
        "available": True,
        "real_data": True,
        "points": points,
        **analysis,
    }


@router.get("/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png")
async def field_tile(
    field_id: str,
    z: int,
    x: int,
    y: int,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    v: str | None = Query(None),
):
    """بلاطة slippy-map (XYZ) مصيَّرة فعليّاً من COG المؤشّر المقصوص للحقل.

    يجد أحدث COG للحقل+المؤشّر (نفس بحث الشبكة؛ salinity→ndsi)، يحسب حدود
    البلاطة في EPSG:3857، يعيد إسقاط COG (UTM غالباً) إلى 256×256 لتلك البقعة،
    يلوّنها بتدرّج المؤشّر، ويُرجِع PNG. البكسلات خارج الحقل/NaN → شفّافة.

    صدق + لا 500: عند غياب COG/rasterio/تقاطع البيانات → بلاطة شفّافة (الخريطة
    لا تُظهر شيئاً فوق الحقل) بدل خطأ خادم.
    """
    await _require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (DB مصدر الحقيقة + ذاكرة)
    index = _normalize_index(index)
    _obs_inc("tile_requests_total", index)
    tenant = _REQ_TENANT.get()
    cache_path = _tile_cache_key(field_id, index, date, z, x, y, tenant, v=v)
    cached_png = _read_tile_cache(cache_path)
    if cached_png:
        _obs_inc("tile_cache_hits_total", index)
        return Response(
            content=cached_png,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Sahool-Tile-Cache": "hit",
                "X-Sahool-Tile-Date": date,
                "X-Sahool-Tile-Version": v or "default",
            },
        )
    layer = await _resolve_field_layer(field_id, index, date)
    if layer is not None and layer.get("cog_url"):
        try:
            import tile_render

            cog_path = object_store.to_gdal_path(layer["cog_url"])
            internal = _normalize_index(index)
            png = tile_render.render_tile_png(cog_path, z, x, y, internal)
            if png:
                _obs_inc("tile_cache_misses_total", index)
                _write_tile_cache(cache_path, png)
                return Response(
                    content=png,
                    media_type="image/png",
                    headers={
                        "Cache-Control": "public, max-age=3600",
                        "X-Sahool-Tile-Cache": "miss",
                        "X-Sahool-Tile-Date": date,
                        "X-Sahool-Tile-Version": v or "default",
                    },
                )
        except Exception as e:  # noqa: BLE001 — لا نُفشل الخريطة، نخدم شفّافاً
            _obs_inc("tile_render_errors_total", index)
            logger.warning("field_tile render skipped (%s): %s", field_id, e)
    # لا COG/بيانات/rasterio → بلاطة شفّافة (لا 500)
    _obs_inc("tile_transparent_total", index)
    return Response(
        content=_TRANSPARENT_PNG,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-Sahool-Tile-Cache": "transparent",
            "X-Sahool-Tile-Date": date,
        },
    )


@router.get("/v1/fields/{field_id}/available-dates")
async def field_available_dates(
    field_id: str,
    index: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    include_provider: bool = Query(
        False,
        description="ادمج تواريخ التقاط المزوّد (STAC) للنافذة — غير المعالَج يظهر has_cog=false",
    ),
    months: int = Query(24, ge=1, le=24),
):
    """Return real imagery acquisition dates with ready/COG status for a field.

    This endpoint is used by MapHub's scene selector. It must be tenant-filtered
    and must report dates from actual persisted/generated COGs, not from the UI
    or a provider search alone.
    """
    await _require_field_tenant(field_id, hide_existence=True)
    wanted = [_normalize_index(index)] if index else []
    by_date: dict[str, dict] = {}

    def _add(
        date_value,
        *,
        idx=None,
        has_cog=True,
        cloud_pct=None,
        scene_id=None,
        acquisition_datetime=None,
    ):
        if not date_value:
            return
        d = str(date_value)[:10]
        if len(d) != 10:
            return
        rec = by_date.setdefault(
            d,
            {
                "date": d,
                "has_cog": False,
                "indices": set(),
                "cloud_pct": None,
                "clear_pct": None,
                "quality_label": None,
                "scene_id": None,
                # وقت الالتقاط الحقيقيّ (ISO8601 UTC) من كتالوج STAC حين توفّره؛ يبقى None
                # (فتعرض الواجهة التاريخ وحده) إن لم يُسجَّل مشهد — لا اختلاق ساعة.
                "acquisition_datetime": None,
            },
        )
        rec["has_cog"] = bool(rec["has_cog"] or has_cog)
        if idx:
            rec["indices"].add(_display_index(idx))
        if cloud_pct is not None and rec["cloud_pct"] is None:
            try:
                cloud = max(0.0, min(100.0, float(cloud_pct)))
                rec["cloud_pct"] = cloud
                rec["clear_pct"] = 100.0 - cloud
                rec["quality_label"] = (
                    "high"
                    if rec["clear_pct"] >= NDVI_HIGH_QUALITY_CLEAR_PCT
                    else "medium"
                    if rec["clear_pct"] >= NDVI_PULL_MIN_CLEAR_PCT
                    else "cloudy"
                )
            except (TypeError, ValueError):
                pass
        if scene_id and not rec["scene_id"]:
            rec["scene_id"] = str(scene_id)
        if acquisition_datetime and not rec["acquisition_datetime"]:
            rec["acquisition_datetime"] = str(acquisition_datetime)

    for lid in _field_layers.get(field_id, []):
        lyr = _layers.get(lid)
        if not lyr or not lyr.get("cog_url"):
            continue
        idx = lyr.get("index")
        if wanted and _normalize_index(idx) not in wanted:
            continue
        _add(
            lyr.get("acquisition_date"),
            idx=idx,
            has_cog=True,
            cloud_pct=lyr.get("cloud_pct"),
            scene_id=(lyr.get("provenance") or {}).get("scene_id")
            if isinstance(lyr.get("provenance"), dict)
            else None,
        )

    try:
        import db_persist

        rows = await db_persist.list_available_asset_dates(
            field_id,
            tenant_id=_REQ_TENANT.get(),
            indices=wanted or None,
            limit=limit,
        )
        for row in rows:
            _add(
                row.get("date"),
                idx=row.get("index_name"),
                has_cog=row.get("has_cog", True),
                cloud_pct=row.get("cloud_pct"),
                scene_id=row.get("scene_id"),
                acquisition_datetime=row.get("acquisition_datetime"),
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("available dates DB lookup skipped (%s): %s", field_id, e)

    # TIMELINE-PROVIDER-DATES: محور الزمن الحقيقيّ هو تواريخ التقاط المزوّد لا ما
    # عولج فقط — الشريط التاريخيّ يعرض كلّ مشاهد الكتالوج للنافذة، والجاهز منها
    # (COG موجود أعلاه) يحمل صورته بينما الباقي «ينتظر COG». فشل الكتالوج لا يُفشل
    # الردّ: تبقى التواريخ المعالَجة وتُعلَن العلّة في provider_dates_error (لا اختلاق).
    provider_error: str | None = None
    if include_provider:
        try:
            import datetime as _dt

            import db_persist

            geometry = await db_persist.fetch_field_geometry(field_id, _REQ_TENANT.get())
            bbox = _bbox_from_geojson(geometry) if geometry else None
            if bbox is None:
                provider_error = "field_geometry_unavailable"
            else:
                # _month_windows يقارن cursor (datetime بـUTC) بـend، فيجب أن يكونا
                # datetime بمنطقة زمنيّة — تمرير date خام يرفع
                # "can't compare datetime.datetime to datetime.date" ويُسقِط دمج المزوّد.
                end = _dt.datetime.now(_dt.UTC)
                start = end - _dt.timedelta(days=months * 31)
                for w_start, w_end in _month_windows(start, end):
                    search = await _stac_search(
                        bbox,
                        w_start.strftime("%Y-%m-%dT00:00:00Z"),
                        w_end.strftime("%Y-%m-%dT23:59:59Z"),
                        100,
                        limit=100,
                    )
                    for item in search.get("items", []):
                        _add(
                            (item.get("datetime") or "")[:10],
                            has_cog=False,
                            cloud_pct=item.get("cloud_cover_pct"),
                            scene_id=item.get("item_id"),
                            acquisition_datetime=item.get("datetime"),
                        )
        except Exception as e:  # noqa: BLE001 — الكتالوج best-effort للشريط، المعالَج يبقى
            provider_error = str(e)[:200]
            logger.warning("provider dates merge skipped (%s): %s", field_id, e)

    dates = []
    for rec in by_date.values():
        rec["indices"] = sorted(rec["indices"])
        dates.append(rec)
    dates.sort(key=lambda r: r["date"], reverse=True)
    out = {"field_id": field_id, "dates": dates[:limit], "provider_included": include_provider}
    if provider_error:
        out["provider_dates_error"] = provider_error
    return out


@router.get("/v1/fields/{field_id}/terrain")
async def field_terrain(
    field_id: str,
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat (EPSG:4326)"),
):
    """إحصاءات تضاريس الحقل (ارتفاع + انحدار/اتّجاه + حصاد المياه) من DEM حقيقيّ.

    الأساس الصادق لعرض التضاريس (سدّ فجوة TERRAIN): يقصّ نموذج الارتفاع المُهيّأ عبر
    ``FIELD_DEM_PATH`` على مربّع إحاطة الحقل ويحسب الإحصاءات عبر Horn. لا تلفيق:
    غياب DEM أو bbox ⇒ مظروف ``computed=false`` صريح بمصدره. تصيير 3D terrain-RGB
    يبقى TODO موثّقاً حتّى تُنتَج بلاطات DEM.
    """
    await _require_field_tenant(field_id, hide_existence=True)
    parsed_bbox: list[float] | None = None
    if bbox:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) == 4:
                parsed_bbox = parts
        except (TypeError, ValueError):
            parsed_bbox = None

    import terrain_analysis as ta

    # يعمل من ``field_id`` وحده: عند غياب bbox صريح نشتقّ المضلّع الفعليّ من قاعدة الحقول
    # (RLS-safe) ونقصّ **داخل حدّ الحقل** لا مستطيل bbox. تعذّر الجلب ⇒ يبقى المسار الصادق
    # ``computed=false`` (field-bbox-unavailable) — لا تلفيق.
    poly: list | None = None
    if parsed_bbox is None:
        try:
            import db_persist

            geom = await db_persist.fetch_field_geometry(field_id, _REQ_TENANT.get())
            parsed_bbox, poly = ta.field_terrain_extent(geom)
        except Exception as e:  # noqa: BLE001 — اشتقاق اختياريّ؛ فشله ⇒ computed=false صريح.
            logger.warning("terrain geometry derive skipped (%s): %s", field_id, e)

    dem_path = os.getenv("FIELD_DEM_PATH") or None
    result = ta.compute_field_terrain(dem_path, parsed_bbox, poly=poly)
    if result.get("computed") and (result.get("slope_deg") or {}).get("mean") is not None:
        result["water_harvesting"] = ta.classify_water_harvesting(result["slope_deg"]["mean"])
        # ربط الانحدار بقرارات زراعيّة (خطر تعرية/سيولة/إجراءات) — إرشاديّ، بلا تلفيق.
        agronomy = ta.interpret_terrain_for_agronomy(result)
        if agronomy:
            result["agronomy"] = agronomy
    result["field_id"] = field_id
    return result


@router.get("/v1/fields/{field_id}/tilejson")
async def field_tilejson(
    field_id: str,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    v: str | None = Query(None),
):
    """TileJSON 2.2.0 للحقل — يستهلكه Leaflet/MapLibre مباشرة.

    tiles[] يشير إلى مسار التصيير الذاتي (يعمل بلا TiTiler). bounds من حدود
    COG بـ4326. إن ضُبط TITILER_URL ووُجد cog_url نعرض رابط TiTiler إضافيّاً
    (اختياري)، لكنّ البلاطات الذاتيّة تعمل دائماً.
    """
    await _require_field_tenant(
        field_id, hide_existence=True
    )  # لا نكشف وجود حقل tenant آخر عبر tilejson
    out_index = _display_index(index)
    index = _normalize_index(index)
    _obs_inc("tilejson_requests_total", index)
    layer = await _resolve_field_layer(field_id, index, date)
    bounds = None
    if layer is not None and layer.get("bounds_4326"):
        b = layer["bounds_4326"]
        if b and len(b) == 4 and any(v != 0.0 for v in b):
            bounds = [round(float(v), 6) for v in b]
    # صدق: غياب COG ⇒ لا حدود حقيقيّة. لا نختلق حدوداً ضيّقة (الجوف) كأنّها بيانات
    # الحقل — نعلن available=False ونعطي حدوداً عالميّة محايدة (لا تُقفِز الخريطة لمكان
    # خاطئ)، فيستطيع المستهلِك (FieldIndicatorMap) أن يميّز "لا طبقة" من بيانات فعليّة.
    has_data = bounds is not None
    _obs_inc("tilejson_available_total" if has_data else "tilejson_unavailable_total", index)
    if bounds is None:
        bounds = [-180.0, -85.0, 180.0, 85.0]

    center = [
        round((bounds[0] + bounds[2]) / 2.0, 6),
        round((bounds[1] + bounds[3]) / 2.0, 6),
        14,
    ]
    resolved_date = (layer.get("acquisition_date") or date)[:10] if layer else date
    resolved_version = v or str(
        (layer or {}).get("created_at") or (layer or {}).get("cog_url") or "default"
    )
    # TileJSON is fetched by JS, but the returned tiles are loaded later as <img>
    # requests and cannot rely on axios headers. Propagate the tenant hint from the
    # already-validated request into the tile URL so restart/DB rehydration keeps
    # working for MapLibre/Leaflet consumers.
    # urlencode بدل التسلسل اليدويّ: ``v`` قد يُشتقّ من cog_url (قد يحوي & / مسافات)
    # فالتسلسل الخام يكسر سلسلة الاستعلام أو يحقن معاملات. urlencode يُرمِّز بأمان. v4-audit
    from urllib.parse import urlencode

    qs_params: dict[str, str] = {
        "index": out_index,
        "date": date,
        "resolved_date": resolved_date,
    }
    req_tenant = _REQ_TENANT.get()
    if req_tenant:
        qs_params["tid"] = req_tenant
    if resolved_version:
        qs_params["v"] = resolved_version
    qs = urlencode(qs_params)
    self_tiles = f"/v1/fields/{field_id}/tiles/{{z}}/{{x}}/{{y}}.png?{qs}"

    tj = {
        "tilejson": "2.2.0",
        "name": f"field-{field_id}-{out_index}",
        "description": "بلاطات مؤشّر مصيَّرة ذاتيّاً من COG الحقل المقصوص",
        "scheme": "xyz",
        "tiles": [self_tiles],
        "minzoom": 8,
        "maxzoom": 20,
        "bounds": bounds,
        "center": center,
        "source": "self-rendered",
        "available": has_data,
        "resolved_date": resolved_date,
        "cache_version": resolved_version,
        "legend": __import__("tile_render").index_legend(index),
        "reason": None if has_data else "no_field_cog_or_scene_available",
        "user_message": None
        if has_data
        else "لا توجد صورة مؤشر حقيقية متاحة لهذا الحقل والتاريخ. شغّل السحب التاريخي أو اختر تاريخاً آخر.",
        "recommended_action": None
        if has_data
        else "POST /v1/fields/{field_id}/imagery/backfill ثم أعد طلب TileJSON",
        "note": (
            None
            if has_data
            else "لا COG مقصوص للحقل — شغّل /process أو backfill أوّلاً (الحدود عالميّة محايدة لا بيانات حقل)"
        ),
    }
    # اختياري: رابط TiTiler الديناميكي إن توفّر (لا يُلغي الذاتي). cog_url للعميل:
    # عامّ http(s) فقط — لا نكشف مسارات التخزين الداخليّة (file://، s3://، مضيف داخليّ).
    cog_url = _public_cog_url(layer.get("cog_url") if layer else None)
    if TITILER_URL and cog_url:
        internal = _normalize_index(index)
        colormap = "RdYlGn_r" if internal in ("ndsi", "salinity") else "RdYlGn"
        tj["titiler_tiles"] = [
            f"{TITILER_URL}/cog/tiles/{{z}}/{{x}}/{{y}}.png?url={cog_url}&colormap_name={colormap}"
        ]
    return tj
