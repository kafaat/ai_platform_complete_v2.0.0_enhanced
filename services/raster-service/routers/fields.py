"""routers/fields.py — مسارات الحقل (Field-scoped: grid/prescription/change/timeseries/tiles)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``. المساعِدات المشتركة
(تحليل الطبقات/التفويض/التصيير) والنماذج والحالة تبقى في ``main`` وتُشار إليها
عبر ``main.X``. مسارات CDSE الحيّة في ``routers/cdse_tiles.py`` (منفصلة).
"""

from __future__ import annotations

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
        vrt_path, index_map = stac_vrt.build_band_vrt(safe_hrefs)
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

    # تطبيع اسم المؤشّر المعروض (salinity مقبول للواجهة)
    out_index = index

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
    await main._require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (ذاكرة + جدول fields)
    requested_dates = [d.strip() for d in dates.split(",") if d.strip()]
    if not requested_dates:
        # كلّ تواريخ الطبقات الحقيقيّة المتاحة للحقل+المؤشّر (من الذاكرة)
        internal = main._GRID_INDEX_ALIASES.get(index, index)
        seen: set[str] = set()
        for lid in main._field_layers.get(field_id, []):
            lyr = main._layers.get(lid)
            if not lyr or not lyr.get("cog_url") or lyr.get("index") != internal:
                continue
            d = lyr.get("acquisition_date")
            if d:
                seen.add(str(d)[:10])
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
            "index": index,
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
        "index": index,
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
):
    """بلاطة slippy-map (XYZ) مصيَّرة فعليّاً من COG المؤشّر المقصوص للحقل.

    يجد أحدث COG للحقل+المؤشّر (نفس بحث الشبكة؛ salinity→ndsi)، يحسب حدود
    البلاطة في EPSG:3857، يعيد إسقاط COG (UTM غالباً) إلى 256×256 لتلك البقعة،
    يلوّنها بتدرّج المؤشّر، ويُرجِع PNG. البكسلات خارج الحقل/NaN → شفّافة.

    صدق + لا 500: عند غياب COG/rasterio/تقاطع البيانات → بلاطة شفّافة (الخريطة
    لا تُظهر شيئاً فوق الحقل) بدل خطأ خادم.
    """
    await main._require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (ذاكرة + جدول fields)
    layer = await main._resolve_field_layer(field_id, index, date)
    if layer is not None and layer.get("cog_url"):
        try:
            import tile_render

            cog_path = main.object_store.to_gdal_path(layer["cog_url"])
            internal = main._GRID_INDEX_ALIASES.get(index, index)
            png = tile_render.render_tile_png(cog_path, z, x, y, internal)
            if png:
                return Response(
                    content=png,
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"},
                )
        except Exception as e:  # noqa: BLE001 — لا نُفشل الخريطة، نخدم شفّافاً
            main.logger.warning("field_tile render skipped (%s): %s", field_id, e)
    # لا COG/بيانات/rasterio → بلاطة شفّافة (لا 500)
    return Response(
        content=main._TRANSPARENT_PNG,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get("/v1/fields/{field_id}/tilejson")
async def field_tilejson(
    field_id: str,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
):
    """TileJSON 2.2.0 للحقل — يستهلكه Leaflet/MapLibre مباشرة.

    tiles[] يشير إلى مسار التصيير الذاتي (يعمل بلا TiTiler). bounds من حدود
    COG بـ4326. إن ضُبط TITILER_URL ووُجد cog_url نعرض رابط TiTiler إضافيّاً
    (اختياري)، لكنّ البلاطات الذاتيّة تعمل دائماً.
    """
    await main._require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (ذاكرة + جدول fields)
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
    if bounds is None:
        bounds = [-180.0, -85.0, 180.0, 85.0]

    center = [
        round((bounds[0] + bounds[2]) / 2.0, 6),
        round((bounds[1] + bounds[3]) / 2.0, 6),
        14,
    ]
    qs = f"index={index}&date={date}"
    self_tiles = f"/v1/fields/{field_id}/tiles/{{z}}/{{x}}/{{y}}.png?{qs}"

    tj = {
        "tilejson": "2.2.0",
        "name": f"field-{field_id}-{index}",
        "description": "بلاطات مؤشّر مصيَّرة ذاتيّاً من COG الحقل المقصوص",
        "scheme": "xyz",
        "tiles": [self_tiles],
        "minzoom": 8,
        "maxzoom": 20,
        "bounds": bounds,
        "center": center,
        "source": "self-rendered",
        "available": has_data,
        "note": (
            None
            if has_data
            else "لا COG مقصوص للحقل — شغّل /process أوّلاً (الحدود عالميّة محايدة لا بيانات حقل)"
        ),
    }
    # اختياري: رابط TiTiler الديناميكي إن توفّر (لا يُلغي الذاتي). cog_url للعميل:
    # عامّ http(s) فقط — لا نكشف مسارات التخزين الداخليّة (file://، s3://، مضيف داخليّ).
    cog_url = main._public_cog_url(layer.get("cog_url") if layer else None)
    if main.TITILER_URL and cog_url:
        internal = main._GRID_INDEX_ALIASES.get(index, index)
        colormap = "RdYlGn_r" if internal in ("ndsi", "salinity") else "RdYlGn"
        tj["titiler_tiles"] = [
            f"{main.TITILER_URL}/cog/tiles/{{z}}/{{x}}/{{y}}.png?url={cog_url}&colormap_name={colormap}"
        ]
    return tj
