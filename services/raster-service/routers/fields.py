"""routers/fields.py — مسارات الحقل (Field-scoped)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import main
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from fastapi.responses import Response

router = APIRouter()


@router.post("/v1/fields/{field_id}/process-from-stac")
async def process_from_stac(
    field_id: str,
    req: main.ProcessFromStacRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    """يجسر الاستيراد→المعالجة: يكدّس COGs المنفصلة لنطاقات STAC في VRT
    (عبر /vsicurl/ للبعيد) ثم يشغّل نفس مسار /process (قصّ→مؤشّر→COG→persist).

    مناسب للمزوّد بلا مفتاح (Element84): استدعِ /imagery/best لجلب band hrefs،
    ثمّ مرّرها هنا. خلفيّة — يُرجِع job_id.
    """
    main._require_service_token(x_agent_token)
    import stac_vrt

    # كلّ href يُتحقَّق منه (traversal/SSRF) قبل بناء الـVRT.
    safe_hrefs = {k: main._safe_raster_source(v) for k, v in (req.band_hrefs or {}).items()}
    try:
        # الـVRT يُكتَب تحت UPLOAD_DIR كي يقبله حارس المصدر (_safe_raster_source) —
        # كتابته في /tmp مباشرة كانت تُفشِل المعالجة بـ400 (خارج المجلّد المسموح).
        vrt_path, index_map = stac_vrt.build_band_vrt(safe_hrefs, out_dir=main.UPLOAD_DIR)
    except Exception as e:  # noqa: BLE001 — مدخل غير صالح/نطاق غير مقروء
        raise HTTPException(400, f"تعذّر بناء VRT من نطاقات STAC: {e}") from e

    band_kwargs = {k: v for k, v in index_map.items() if k in main.BandMapping.model_fields}
    preq = main.ProcessRequest(
        raster_url=vrt_path,
        indicator=req.indicator,
        bands=main.BandMapping(**band_kwargs),
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
    main._jobs.set(
        job_id,
        {
            "job_id": job_id,
            "status": main.JobStatus.pending,
            "progress_pct": 0,
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    background_tasks.add_task(main._run_processing, job_id, preq)
    return {
        "job_id": job_id,
        "status": main.JobStatus.pending,
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
            collection=main.SENTINEL_COLLECTION,
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
    req: main.HistoricalBackfillRequest,
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
    main._require_service_token(x_agent_token)
    await main._require_field_tenant(field_id)

    if not req.indices:
        raise HTTPException(400, "indices مطلوبة")
    unsupported = [
        i.value
        for i in req.indices
        if i
        not in {
            main.IndicatorKind.ndvi,
            main.IndicatorKind.ndmi,
            main.IndicatorKind.savi,
            main.IndicatorKind.evi,
            main.IndicatorKind.gndvi,
            main.IndicatorKind.ndre,
            main.IndicatorKind.msi,
            main.IndicatorKind.msavi,
        }
    ]
    if unsupported:
        raise HTTPException(400, f"مؤشّرات غير مناسبة للـbackfill البصري: {unsupported}")

    clip = req.clip_polygon_geojson
    bbox = main._bbox_from_geojson(clip)
    if bbox is None:
        raise HTTPException(400, "clip_polygon_geojson مطلوب لاشتقاق bbox وقصّ الصور على حدود الحقل")

    start, end, months = main._backfill_date_range(req)
    windows = main._month_windows(start, end)
    selected_scenes: list[dict] = []
    monthly: list[dict] = []
    for w_start, w_end in windows:
        search = await main._stac_search(
            bbox,
            w_start.strftime("%Y-%m-%dT00:00:00Z"),
            w_end.strftime("%Y-%m-%dT23:59:59Z"),
            req.max_cloud_pct,
            limit=max(10, req.limit_per_month * 4),
        )
        items = main._rank_scenes(search.get("items", []), max_cloud_pct=req.max_cloud_pct)[
            : req.limit_per_month
        ]
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
    tenant_id = req.tenant_id or main._REQ_TENANT.get()
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
            main._jobs.set(
                job_id,
                {
                    **scheduled_item,
                    "status": main.JobStatus.pending,
                    "progress_pct": 0,
                    "created_at": datetime.now(UTC).isoformat(),
                    "job_type": "historical_backfill",
                    "preset": req.preset.value,
                },
            )

            # Reuse the same VRT/process path without issuing an HTTP subrequest.
            async def _run_scene_job(jid=job_id, sc=scene, ind=indicator):
                try:
                    import stac_vrt

                    safe_hrefs = {
                        k: main._safe_raster_source(v)
                        for k, v in (sc.get("bands_urls") or {}).items()
                        if v
                    }
                    # تحت UPLOAD_DIR كي يقبله _safe_raster_source — كتابة الـVRT في
                    # /tmp أسقطت كلّ مهامّ backfill بـHTTPException 400 (بلاغ 2026-07-04).
                    vrt_path, index_map = stac_vrt.build_band_vrt(
                        safe_hrefs, out_dir=main.UPLOAD_DIR
                    )
                    preq = main.ProcessRequest(
                        tenant_id=tenant_id,
                        field_id=field_id,
                        raster_url=vrt_path,
                        indicator=ind,
                        source_format=main.SourceFormat.sentinel2_l2a,
                        bands=main.BandMapping(
                            **{
                                k: v
                                for k, v in index_map.items()
                                if k in main.BandMapping.model_fields
                            }
                        ),
                        clip_polygon_geojson=clip,
                        apply_cloud_mask=req.apply_cloud_mask,
                        scene_id=sc.get("item_id"),
                        capture_datetime=sc.get("datetime"),
                        provider="element84",
                    )
                    main._run_processing(jid, preq)
                except Exception as e:  # noqa: BLE001
                    # توحيد main↔cert (#542): لا نُسرّب نصّ الاستثناء للعميل — رمز عامّ،
                    # والسجلّ الداخلي يحمل النوع (+ status/detail لـHTTPException —
                    # نصّنا المتحكَّم به؛ النوع وحده أخفى سبب فشل backfill 2026-07-04).
                    _http = f" [{e.status_code}] {e.detail}" if isinstance(e, HTTPException) else ""
                    main.logger.warning(
                        "scene job %s فشل أثناء معالجة المشهد: %s%s",
                        jid,
                        type(e).__name__,
                        _http,
                    )
                    j = main._jobs.get(jid) or {"job_id": jid}
                    j.update(
                        {
                            "status": main.JobStatus.failed,
                            "error_message": "scene_processing_failed",
                            "finished_at": datetime.now(UTC).isoformat(),
                        }
                    )
                    main._jobs.set(jid, j)

            background_tasks.add_task(_run_scene_job)
            job_ids.append(job_id)

    return {
        "field_id": field_id,
        "preset": req.preset.value,
        "period": {
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "months": months,
        },
        "indices": [i.value for i in req.indices],
        "max_cloud_pct": req.max_cloud_pct,
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


@router.post("/v1/fields/{field_id}/geometry/versions")
async def create_field_geometry_version(
    field_id: str,
    geometry: dict,
    valid_from: str | None = Query(None),
    reason: str | None = Query("manual_snapshot"),
    x_agent_token: str = Header(None),
):
    """Persist a field geometry snapshot for reproducible historical analytics."""
    main._require_service_token(x_agent_token)
    await main._require_field_tenant(field_id)
    tenant_id = main._REQ_TENANT.get()
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
    req: main.GeoParquetExportRequest, x_agent_token: str = Header(None)
):
    """Export field analytics as GeoParquet when optional deps exist, else NDJSON.

    GeoParquet requires pyarrow/shapely/geopandas in the production image. The
    fallback writes an explicit NDJSON file instead of mislabeling a non-GeoParquet
    artifact.
    """
    main._require_service_token(x_agent_token)
    tenant_id = req.tenant_id or main._REQ_TENANT.get()
    import json as _json

    import db_persist

    rows = await db_persist.fetch_field_analytics_for_export(
        tenant_id=tenant_id, field_ids=req.field_ids
    )
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in req.output_name)
    out_dir = os.path.join(main.UPLOAD_DIR, "exports", str(tenant_id or "unknown"))
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
    req: main.ProcessCdseRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    """يحسب مؤشّرات الحقل عبر CDSE (المزوّد الافتراضيّ الأقوى). خلفيّة، يُرجِع job_id.

    صدق: بلا اعتمادات CDSE (``CDSE_CLIENT_ID``/``SECRET`` أو ``CDSE_ENABLED=false``) ⇒
    ``available=false`` (200، لا خطأ) كي يسقط المنسّق إلى Element84 بصمت — لا توقّف ولا تلفيق.
    """
    main._require_service_token(x_agent_token)
    import cdse_client

    if not cdse_client.is_configured():
        return {
            "provider": "cdse",
            "available": False,
            "queued": False,
            "note_ar": "CDSE غير مُهيّأ (لا CDSE_CLIENT_ID/SECRET) — يسقط المنسّق إلى Element84.",
        }
    if not req.bbox or len(req.bbox) != 4:
        raise HTTPException(400, "bbox مطلوب [west,south,east,north] (EPSG:4326).")
    if not req.indicators:
        raise HTTPException(400, "indicators مطلوبة (مؤشّر واحد على الأقلّ).")
    job_id = f"cdse_{uuid.uuid4().hex[:12]}"
    main._jobs.set(
        job_id,
        {
            "job_id": job_id,
            "status": main.JobStatus.pending,
            "progress_pct": 0,
            "created_at": datetime.now(UTC).isoformat(),
            "indicators": list(req.indicators),
            "provider": "cdse",
        },
    )
    background_tasks.add_task(main._run_cdse_processing, job_id, field_id, req)
    return {
        "provider": "cdse",
        "available": True,
        "queued": True,
        "job_id": job_id,
        "status": main.JobStatus.pending,
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

    إن وُجد COG مقصوص للحقل (من /process مع clip_polygon) → يُقرأ ويُصغّر
    إلى grid×grid مع تصنيف مناطق الشدّة (real_data=True). وإلّا → شبكة محاكاة
    مُعلَّمة بصدق (real_data=False, source="simulation") — نفس شكل العقد دائماً.
    """
    await main._require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (ذاكرة + جدول fields)
    import indicator_grid as ig

    # تطبيع اسم المؤشّر المعروض (salinity/NDVU aliases مقبولة للواجهة)
    out_index = main._display_index(index)
    index = main._normalize_index(index)

    layer = await main._resolve_field_layer(field_id, index, date)
    if layer is not None:
        real = main._grid_from_cog(layer, out_index, date, grid)
        if real is not None:
            return real

    # fallback: شبكة محاكاة (لا COG حقيقي / لا rasterio / لا شبكة) — مُعلَّمة بصدق
    # bbox افتراضي حول اليمن (الجوف) إن لم تتوفّر حدود حقيقيّة.
    bbox = [44.0, 16.0, 44.01, 16.01]
    if layer is not None and layer.get("bounds_4326"):
        bbox = [round(float(x), 6) for x in layer["bounds_4326"]]
    return ig.synthetic_grid(field_id, out_index, date, bbox, grid)


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
    await main._require_field_tenant(field_id, hide_existence=True)
    out_index = main._display_index(index)
    index = main._normalize_index(index)
    layer = await main._resolve_field_layer(field_id, index, date)
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
    path = main.object_store.to_gdal_path(layer.get("cog_url") or layer.get("raster_url") or "")
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
            quality = main._pixel_quality(layer, float(value))
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
    field_id: str, req: main.PrescriptionRequest, x_agent_token: str = Header(None)
):
    """وصفة مناطق الإدارة (VRT) من شبكة المؤشّر — سدّ Sprint 5b.

    يبني شبكة المؤشّر للحقل (نفس مسار indicator-grid: COG حقيقي إن وُجد وإلّا
    محاكاة صادقة)، يقسّمها بالكوانتايل إلى n_zones مناطق أداء، ويشتقّ معدّلاً
    موصى به لكلّ منطقة إن مُرّر base_rate. يُرجِع المناطق + إحصاء كلّ منطقة
    (pixel_count, pct, value_range) + متوسّط/تباين الحقل.

    صدق: real_data ينعكس من مصدر الشبكة؛ المعدّلات إرشاديّة (قرار agronomic
    يحتاج تحقّقاً ميدانيّاً).
    """
    main._require_service_token(
        x_agent_token
    )  # توكن خدمة إلزاميّ (مطابقة الشقيقات — منع كشف الحقول)
    import indicator_grid as ig
    import management_zones as mz

    layer = await main._resolve_field_layer(field_id, req.index, req.date)
    grid_resp = None
    if layer is not None:
        grid_resp = main._grid_from_cog(layer, req.index, req.date, req.grid)
    if grid_resp is None:
        bbox = [44.0, 16.0, 44.01, 16.01]
        if layer is not None and layer.get("bounds_4326"):
            bbox = [round(float(x), 6) for x in layer["bounds_4326"]]
        grid_resp = ig.synthetic_grid(field_id, req.index, req.date, bbox, req.grid)

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
async def field_change(
    field_id: str, req: main.FieldChangeRequest, x_agent_token: str = Header(None)
):
    """كشف التغيّر المكاني (per-pixel 2D) للحقل بين تاريخين — أين تدهور/تحسّن.

    يبني شبكتي المؤشّر الحقيقيّتين (من COG المقصوص لكلّ تاريخ، نفس مسار
    indicator-grid) ويُمرّرهما لـdetect_change. صدق: إن لم تتوفّر شبكة حقيقيّة
    لأحد التاريخين (لا COG / لا rasterio) يُرجِع real_data=False بلا تغيّر مُفبرَك.
    """
    main._require_service_token(
        x_agent_token
    )  # توكن خدمة إلزاميّ (مطابقة الشقيقات — منع كشف الحقول)
    grid_a = await main._real_field_grid(field_id, req.index, req.date_a, req.grid)
    grid_b = await main._real_field_grid(field_id, req.index, req.date_b, req.grid)

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
    await main._require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (DB مصدر الحقيقة + ذاكرة)
    out_index = main._display_index(index)
    index = main._normalize_index(index)
    requested_dates = [d.strip() for d in dates.split(",") if d.strip()]
    if not requested_dates:
        # كلّ تواريخ الطبقات الحقيقيّة المتاحة للحقل+المؤشّر. نبدأ بالذاكرة، ثم
        # نقرأ raster_assets عند إعادة التشغيل/worker آخر؛ وإلّا يصبح الـtimeline
        # فارغاً رغم وجود COGs مخزّنة. لا نُنشئ نقاطاً، فقط نكتشف التواريخ.
        internal = main._normalize_index(index)
        seen: set[str] = set()
        for lid in main._field_layers.get(field_id, []):
            lyr = main._layers.get(lid)
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
                        field_id, internal, tenant_id=main._REQ_TENANT.get()
                    )
                )
            except Exception as e:  # noqa: BLE001 — لا نكسر السلسلة الزمنية عند غياب DB
                main.logger.warning("raster_assets dates rehydrate skipped (%s): %s", field_id, e)
        requested_dates = sorted(seen)

    points: list[dict] = []
    for date in requested_dates:
        real = await main._real_field_grid(field_id, index, date, grid)
        if real is None:
            continue
        points.append(
            {
                "datetime": str(real.get("date") or date)[:10],
                "mean": real["stats"]["mean"],
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
    await main._require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (DB مصدر الحقيقة + ذاكرة)
    index = main._normalize_index(index)
    main._obs_inc("tile_requests_total", index)
    tenant = main._REQ_TENANT.get()
    cache_path = main._tile_cache_key(field_id, index, date, z, x, y, tenant, v=v)
    cached_png = main._read_tile_cache(cache_path)
    if cached_png:
        main._obs_inc("tile_cache_hits_total", index)
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
    layer = await main._resolve_field_layer(field_id, index, date)
    if layer is not None and layer.get("cog_url"):
        try:
            import tile_render

            cog_path = main.object_store.to_gdal_path(layer["cog_url"])
            internal = main._normalize_index(index)
            png = tile_render.render_tile_png(cog_path, z, x, y, internal)
            if png:
                main._obs_inc("tile_cache_misses_total", index)
                main._write_tile_cache(cache_path, png)
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
            main._obs_inc("tile_render_errors_total", index)
            main.logger.warning("field_tile render skipped (%s): %s", field_id, e)
    # لا COG/بيانات/rasterio → بلاطة شفّافة (لا 500)
    main._obs_inc("tile_transparent_total", index)
    return Response(
        content=main._TRANSPARENT_PNG,
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
):
    """Return real imagery acquisition dates with ready/COG status for a field.

    This endpoint is used by MapHub's scene selector. It must be tenant-filtered
    and must report dates from actual persisted/generated COGs, not from the UI
    or a provider search alone.
    """
    await main._require_field_tenant(field_id, hide_existence=True)
    wanted = [main._normalize_index(index)] if index else []
    by_date: dict[str, dict] = {}

    def _add(date_value, *, idx=None, has_cog=True, cloud_pct=None, scene_id=None):
        if not date_value:
            return
        d = str(date_value)[:10]
        if len(d) != 10:
            return
        rec = by_date.setdefault(
            d, {"date": d, "has_cog": False, "indices": set(), "cloud_pct": None, "scene_id": None}
        )
        rec["has_cog"] = bool(rec["has_cog"] or has_cog)
        if idx:
            rec["indices"].add(main._display_index(idx))
        if cloud_pct is not None and rec["cloud_pct"] is None:
            try:
                rec["cloud_pct"] = float(cloud_pct)
            except (TypeError, ValueError):
                pass
        if scene_id and not rec["scene_id"]:
            rec["scene_id"] = str(scene_id)

    for lid in main._field_layers.get(field_id, []):
        lyr = main._layers.get(lid)
        if not lyr or not lyr.get("cog_url"):
            continue
        idx = lyr.get("index")
        if wanted and main._normalize_index(idx) not in wanted:
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
            tenant_id=main._REQ_TENANT.get(),
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
            )
    except Exception as e:  # noqa: BLE001
        main.logger.warning("available dates DB lookup skipped (%s): %s", field_id, e)

    dates = []
    for rec in by_date.values():
        rec["indices"] = sorted(rec["indices"])
        dates.append(rec)
    dates.sort(key=lambda r: r["date"], reverse=True)
    return {"field_id": field_id, "dates": dates[:limit]}


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
    await main._require_field_tenant(
        field_id, hide_existence=True
    )  # لا نكشف وجود حقل tenant آخر عبر tilejson
    out_index = main._display_index(index)
    index = main._normalize_index(index)
    main._obs_inc("tilejson_requests_total", index)
    layer = await main._resolve_field_layer(field_id, index, date)
    bounds = None
    if layer is not None and layer.get("bounds_4326"):
        b = layer["bounds_4326"]
        if b and len(b) == 4 and any(v != 0.0 for v in b):
            bounds = [round(float(v), 6) for v in b]
    # صدق: غياب COG ⇒ لا حدود حقيقيّة. لا نختلق حدوداً ضيّقة (الجوف) كأنّها بيانات
    # الحقل — نعلن available=False ونعطي حدوداً عالميّة محايدة (لا تُقفِز الخريطة لمكان
    # خاطئ)، فيستطيع المستهلِك (FieldIndicatorMap) أن يميّز "لا طبقة" من بيانات فعليّة.
    has_data = bounds is not None
    main._obs_inc("tilejson_available_total" if has_data else "tilejson_unavailable_total", index)
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
    req_tenant = main._REQ_TENANT.get()
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
    cog_url = main._public_cog_url(layer.get("cog_url") if layer else None)
    if main.TITILER_URL and cog_url:
        internal = main._normalize_index(index)
        colormap = "RdYlGn_r" if internal in ("ndsi", "salinity") else "RdYlGn"
        tj["titiler_tiles"] = [
            f"{main.TITILER_URL}/cog/tiles/{{z}}/{{x}}/{{y}}.png?url={cog_url}&colormap_name={colormap}"
        ]
    return tj
