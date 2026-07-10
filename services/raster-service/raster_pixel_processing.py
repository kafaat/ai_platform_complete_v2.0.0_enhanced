"""Pixel-processing helpers for raster-service main.py decomposition.

This module owns pure raster pixel/COG processing while main.py keeps thin
compatibility wrappers during the staged split.  A `ctx` module object is passed
from main.py so behaviour remains byte-for-byte compatible with existing
runtime state and private helpers.
"""

from __future__ import annotations

import os
import uuid

import raster_cloud_mask_strategies
import raster_topographic_qa
import raster_validated_product
import raw_data_processing


def _topographic_qa_for_indicator(
    ctx,
    *,
    req=None,
    raster_crs=None,
    raster_transform=None,
    raster_shape: tuple[int, int] | None = None,
) -> dict:
    """DEM-derived topographic QA envelope for indicator provenance.

    If ``FIELD_DEM_PATH`` plus raster grid metadata are available, this helper
    aligns the DEM to the current indicator array and computes slope risk. If
    request sun geometry is also supplied, it computes a conservative
    hillshade-based terrain shade risk. If anything is missing, it fails closed
    with ``available=false`` and never fabricates a topographic mask.
    """

    dem_path = os.getenv("FIELD_DEM_PATH") or None
    dem_configured = bool(dem_path and os.path.isfile(dem_path))
    sources = ["FIELD_DEM_PATH"] if dem_configured else []
    sun_azimuth_deg = getattr(req, "sun_azimuth_deg", None) if req is not None else None
    sun_altitude_deg = getattr(req, "sun_altitude_deg", None) if req is not None else None
    if not dem_configured:
        return raster_topographic_qa.build_topographic_qa(
            dem_configured=False,
            dem_aligned=False,
            hillshade_available=False,
            sun_geometry_available=bool(
                sun_azimuth_deg is not None and sun_altitude_deg is not None
            ),
            sources=[],
        )
    if raster_crs is None or raster_transform is None or not raster_shape:
        return raster_topographic_qa.build_topographic_qa(
            dem_configured=True,
            dem_aligned=False,
            hillshade_available=False,
            sun_geometry_available=bool(
                sun_azimuth_deg is not None and sun_altitude_deg is not None
            ),
            sources=sources,
            extra_warnings=["indicator_grid_unavailable_for_dem_alignment"],
        )
    try:
        import numpy as np
        import rasterio
        from rasterio.warp import Resampling, reproject

        dst = np.full(tuple(raster_shape), np.nan, dtype="float32")
        with rasterio.open(dem_path) as dem_src:
            reproject(
                source=rasterio.band(dem_src, 1),
                destination=dst,
                src_transform=dem_src.transform,
                src_crs=dem_src.crs,
                dst_transform=raster_transform,
                dst_crs=raster_crs,
                src_nodata=dem_src.nodata,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )
        # Use approximate x pixel size in raster CRS units. For UTM/metre CRS this
        # is direct; for degree CRS this remains conservative provenance, and the
        # QA warnings make DEM/grid alignment explicit.
        pixel_size_m = abs(float(getattr(raster_transform, "a", 0.0) or 0.0)) or 1.0
        out = raster_topographic_qa.build_topographic_qa_from_dem_array(
            dst,
            pixel_size_m=pixel_size_m,
            sun_azimuth_deg=sun_azimuth_deg,
            sun_altitude_deg=sun_altitude_deg,
            sources=sources + ["indicator_grid_dem_alignment"],
        )
        if not bool(out.get("available")):
            out.setdefault("warnings", []).append("dem_aligned_but_topographic_risk_incomplete")
        return out
    except Exception as _e:  # noqa: BLE001 — topographic QA must not fabricate or break indicator path
        return raster_topographic_qa.build_topographic_qa(
            dem_configured=True,
            dem_aligned=False,
            hillshade_available=False,
            sun_geometry_available=bool(
                sun_azimuth_deg is not None and sun_altitude_deg is not None
            ),
            sources=sources,
            extra_warnings=["dem_topographic_qa_failed", str(_e)[:160]],
        )


def process_precomputed_pixels(ctx, req, layer_id: str):
    """مسار CDSE: المؤشّر محسوب خادميّاً (evalscript) فالراستر نطاق-واحد جاهز.

    يقرأ النطاق الأوّل مباشرةً (لا band math، لا تحويل انعكاس)، يعيد إسقاط الحدود إلى
    EPSG:4326، يحسب الإحصاءات، ويكتب COG محسّناً (نفس مسار التخزين/الأصل). يُرجِع
    ``(stats, bounds_4326, resolution_m, meta)`` بنفس تعاقُد :func:`_process_pixels`.
    صدق: لا قناع SCL (CDSE يقنّع الغيوم بـdataMask/maxCloudCoverage خادميّاً)؛ ``NaN`` = لا بيانات.
    """
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds

    # الصورة الخام (truecolor) راستر RGBA متعدّد النطاقات — مسار حفظ منفصل (لا إحصاء
    # مؤشّر/نطاق واحد؛ لا يمرّ عبر ctx._INDICATOR_FORMULAS). يقرأ 4 نطاقات ويكتب COG RGBA.
    if req.indicator.value == "truecolor":
        return process_precomputed_truecolor(ctx, req)

    with rasterio.open(ctx._safe_raster_source(req.raster_url)) as src:
        res_m = abs(src.res[0])
        src_crs = src.crs
        if src_crs is not None:
            bounds = list(transform_bounds(src_crs, "EPSG:4326", *src.bounds))
        else:
            bounds = list(src.bounds)
        arr = src.read(1).astype("float32")
        if src.nodata is not None:
            arr = np.where(arr == src.nodata, np.nan, arr)
        transform = src.transform

    valid = np.isfinite(arr)
    vals = arr[valid]
    total_px = int(valid.size) if hasattr(valid, "size") else 0
    valid_ratio = (float(valid.sum()) / float(total_px)) if total_px else 0.0
    topographic_qa = _topographic_qa_for_indicator(
        ctx, req=req, raster_crs=src_crs, raster_transform=transform, raster_shape=arr.shape
    )
    pixel_qa = raw_data_processing.compute_quality_score(
        valid_pixel_ratio=valid_ratio,
        cloud_pct=None,
        cloud_mask_applied=False,
        terrain_shadow_risk_pct=topographic_qa.get("terrain_shadow_risk_pct"),
        cast_shadow_risk_pct=topographic_qa.get("cast_shadow_risk_pct"),
        slope_risk_pct=topographic_qa.get("slope_risk_pct"),
        topographic_qa_applied=bool(topographic_qa.get("topographic_qa_applied")),
        qa_layer_present=False,
    )
    min_raw_quality_score = float(getattr(req, "min_raw_quality_score", 0.0) or 0.0)
    if (
        bool(getattr(req, "raw_qa_required", True))
        and pixel_qa["quality_score"] < min_raw_quality_score
    ):
        raise ctx.HTTPException(
            422,
            {
                "code": "raw_raster_quality_below_threshold",
                "quality_score": pixel_qa["quality_score"],
                "min_raw_quality_score": min_raw_quality_score,
                "warnings": pixel_qa.get("warnings", []),
            },
        )
    stats = {
        "min": float(np.min(vals)) if vals.size else 0.0,
        "max": float(np.max(vals)) if vals.size else 0.0,
        "mean": float(np.mean(vals)) if vals.size else 0.0,
        "std": float(np.std(vals)) if vals.size else 0.0,
        "valid_pixels": int(valid.sum()),
        "nodata_pixels": int((~valid).sum()),
        "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
        "raw_quality_score": pixel_qa["quality_score"],
        "pixel_qa": pixel_qa,
        "topographic_qa": topographic_qa,
        "quality_flags": raw_data_processing.build_quality_flags(
            nodata_mask_applied=True,
            qa_layer_present=False,
            cloud_mask_applied=False,
            topographic_qa_applied=bool(topographic_qa.get("topographic_qa_applied")),
            terrain_shadow_risk_applied=topographic_qa.get("terrain_shadow_risk_pct") is not None,
            cast_shadow_risk_applied=topographic_qa.get("cast_shadow_risk_pct") is not None,
            slope_risk_applied=topographic_qa.get("slope_risk_pct") is not None,
            topographic_qa_sources=topographic_qa.get("sources", []),
            source_native_qa_policy="precomputed_index_provider_mask_expected",
        ),
    }
    cog_url = None
    cog_crs = str(src_crs or "EPSG:4326")

    validated_product = raster_validated_product.build_validated_raster_product(
        req=req,
        pixel_qa=pixel_qa,
        quality_flags=stats["quality_flags"],
        spatial_crs=cog_crs,
        bounds_4326=bounds,
        topographic_qa=topographic_qa,
        cloud_mask_strategy="provider_precomputed_expected",
        reflectance_normalized=False,
        source_uri=getattr(req, "raster_url", None),
    )
    raster_validated_product.assert_indicator_accepts_validated_product(validated_product)
    stats["validated_raster_product"] = validated_product.model_dump(mode="json")
    RASTER_NODATA = ctx.RASTER_NODATA
    try:
        import cog_writer

        cog_uid = uuid.uuid4().hex[:8]
        cog_path = os.path.join(ctx.UPLOAD_DIR, f"{req.indicator.value}_{cog_uid}.tif")
        cog_info = cog_writer.write_cog(arr, cog_path, transform, crs=cog_crs, nodata=RASTER_NODATA)
        stats["cog"] = cog_info
        if cog_info.get("written"):
            cog_url = ctx.object_store.upload_cog(
                cog_path, f"{req.field_id or 'nofield'}/{req.indicator.value}_{cog_uid}.tif"
            )
    except Exception as _e:  # noqa: BLE001 — حفظ COG اختياري لا يُفشل الحساب
        stats["cog"] = {"written": False, "reason": str(_e)}
    meta = {
        "cog_url": cog_url,
        "cog_crs": cog_crs,
        "srid": (src_crs.to_epsg() if src_crs is not None else 4326),
        "nodata": RASTER_NODATA,
        "pixel_qa": pixel_qa,
        "topographic_qa": topographic_qa,
        "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
    }
    return stats, bounds, res_m, meta


def process_precomputed_truecolor(ctx, req):
    """مسار CDSE للصورة الخام (truecolor): الراستر RGBA (4 نطاقات UINT8) جاهز خادميّاً.

    يقرأ النطاقات كلّها، يحسب إحصاء توفّر بسيطاً من قناة ألفا (لا min/max/mean لمؤشّر —
    RGB بلا معنًى إحصائيّ)، ويكتب COG RGBA محسّناً (``write_rgba_cog``) ثمّ يرفعه. يُرجِع
    ``(stats, bounds_4326, resolution_m, meta)`` بنفس تعاقُد :func:`_process_precomputed_pixels`."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(ctx._safe_raster_source(req.raster_url)) as src:
        res_m = abs(src.res[0])
        src_crs = src.crs
        if src_crs is not None:
            bounds = list(transform_bounds(src_crs, "EPSG:4326", *src.bounds))
        else:
            bounds = list(src.bounds)
        arr = src.read()  # (bands, H, W) uint8
        transform = src.transform

    # صدق الإحصاء: البكسل «صالح» = ألفا>0 (النطاق الرابع) إن وُجد، وإلّا كلّه صالح.
    if arr.shape[0] >= 4:
        valid = arr[3] > 0
    else:
        valid = np.ones(arr.shape[1:], dtype=bool)
    total_px = int(valid.size) if hasattr(valid, "size") else 0
    valid_ratio = (float(valid.sum()) / float(total_px)) if total_px else 0.0
    topographic_qa = _topographic_qa_for_indicator(
        ctx, req=req, raster_crs=src_crs, raster_transform=transform, raster_shape=valid.shape
    )
    pixel_qa = raw_data_processing.compute_quality_score(
        valid_pixel_ratio=valid_ratio,
        cloud_pct=None,
        cloud_mask_applied=False,
        terrain_shadow_risk_pct=topographic_qa.get("terrain_shadow_risk_pct"),
        cast_shadow_risk_pct=topographic_qa.get("cast_shadow_risk_pct"),
        slope_risk_pct=topographic_qa.get("slope_risk_pct"),
        topographic_qa_applied=bool(topographic_qa.get("topographic_qa_applied")),
        qa_layer_present=arr.shape[0] >= 4,
    )
    stats = {
        "min": 0.0,
        "max": 255.0,
        "mean": 0.0,
        "std": 0.0,
        "valid_pixels": int(valid.sum()),
        "nodata_pixels": int((~valid).sum()),
        "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
        "raw_quality_score": pixel_qa["quality_score"],
        "pixel_qa": pixel_qa,
        "topographic_qa": topographic_qa,
        "quality_flags": raw_data_processing.build_quality_flags(
            nodata_mask_applied=True,
            qa_layer_present=arr.shape[0] >= 4,
            cloud_mask_applied=False,
            saturation_mask_applied=False,
            topographic_qa_applied=bool(topographic_qa.get("topographic_qa_applied")),
            terrain_shadow_risk_applied=topographic_qa.get("terrain_shadow_risk_pct") is not None,
            cast_shadow_risk_applied=topographic_qa.get("cast_shadow_risk_pct") is not None,
            slope_risk_applied=topographic_qa.get("slope_risk_pct") is not None,
            topographic_qa_sources=topographic_qa.get("sources", []),
            cloud_mask_sources=["alpha"] if arr.shape[0] >= 4 else [],
            source_native_qa_policy="rgba_alpha_mask",
        ),
    }
    cog_url = None
    cog_crs = str(src_crs or "EPSG:4326")

    validated_product = raster_validated_product.build_validated_raster_product(
        req=req,
        pixel_qa=pixel_qa,
        quality_flags=stats["quality_flags"],
        spatial_crs=cog_crs,
        bounds_4326=bounds,
        topographic_qa=topographic_qa,
        cloud_mask_strategy="rgba_alpha_mask",
        reflectance_normalized=False,
        source_uri=getattr(req, "raster_url", None),
    )
    raster_validated_product.assert_indicator_accepts_validated_product(validated_product)
    stats["validated_raster_product"] = validated_product.model_dump(mode="json")
    try:
        import cog_writer

        cog_uid = uuid.uuid4().hex[:8]
        cog_path = os.path.join(ctx.UPLOAD_DIR, f"truecolor_{cog_uid}.tif")
        cog_info = cog_writer.write_rgba_cog(arr, cog_path, transform, crs=cog_crs)
        stats["cog"] = cog_info
        if cog_info.get("written"):
            cog_url = ctx.object_store.upload_cog(
                cog_path, f"{req.field_id or 'nofield'}/truecolor_{cog_uid}.tif"
            )
    except Exception as _e:  # noqa: BLE001 — حفظ COG اختياري لا يُفشل المعالجة
        stats["cog"] = {"written": False, "reason": str(_e)}
    meta = {
        "cog_url": cog_url,
        "cog_crs": cog_crs,
        "srid": (src_crs.to_epsg() if src_crs is not None else 4326),
        "nodata": None,  # RGBA يستخدم قناة ألفا لا قيمة nodata
        "pixel_qa": pixel_qa,
        "topographic_qa": topographic_qa,
        "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
    }
    return stats, bounds, res_m, meta


def _process_pixels_truecolor(ctx, req, layer_id: str):
    """مسار Element84 للصورة الخام (truecolor): يقرأ نطاقات RGB من VRT،
    يحوّلها إلى RGBA uint8، ويكتب COG ويرجع (stats, bounds_4326, res_m, meta)."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(ctx._safe_raster_source(req.raster_url)) as src:
        res_m = abs(src.res[0])
        src_crs = src.crs
        bounds = (
            list(transform_bounds(src_crs, "EPSG:4326", *src.bounds))
            if src_crs is not None
            else list(src.bounds)
        )
        b = req.bands

        def _read_uint8(idx):
            if not idx:
                return np.zeros(src.shape, dtype=np.uint8)
            raw = src.read(idx).astype("float32")
            if src.nodata is not None:
                raw = np.where(raw == src.nodata, np.nan, raw)
            _sc = req.reflectance_scale
            _of = req.reflectance_offset
            if _sc is None and src.scales:
                _sc = src.scales[idx - 1]
            if _of is None and src.offsets:
                _of = src.offsets[idx - 1]
            # VRTs built by stac_vrt.build_band_vrt don't carry scale metadata from
            # source COGs — GDAL fills the field with the default 1.0 (identity).
            # Without this fallback, Sentinel-2 L2A DN values (0-10000) pass through
            # to_reflectance unchanged and clip(raw, 0, 1) → all-white image.
            if (
                _sc is None or float(_sc) == 1.0
            ) and req.source_format == ctx.SourceFormat.sentinel2_l2a:
                _sc = 0.0001
            raw = ctx.band_math.to_reflectance(raw, _sc, _of, np)
            raw = np.nan_to_num(np.clip(raw, 0.0, 1.0), nan=0.0)
            return (raw * 255).astype(np.uint8)

        r = _read_uint8(b.red)
        g = _read_uint8(b.green)
        bl = _read_uint8(b.blue)
        transform = src.transform

    alpha = np.where((r > 0) | (g > 0) | (bl > 0), np.uint8(255), np.uint8(0))
    rgba = np.stack([r, g, bl, alpha], axis=0)  # (4, H, W) uint8
    valid_count = int((alpha > 0).sum())
    total = int(alpha.size)
    stats = {
        "min": 0.0,
        "max": 255.0,
        "mean": 0.0,
        "std": 0.0,
        "valid_pixels": valid_count,
        "nodata_pixels": total - valid_count,
    }
    cog_url = None
    cog_crs = str(src_crs or "EPSG:4326")
    try:
        import cog_writer

        cog_uid = uuid.uuid4().hex[:8]
        cog_path = os.path.join(ctx.UPLOAD_DIR, f"truecolor_{cog_uid}.tif")
        cog_info = cog_writer.write_rgba_cog(rgba, cog_path, transform, crs=cog_crs)
        stats["cog"] = cog_info
        if cog_info.get("written"):
            cog_url = ctx.object_store.upload_cog(
                cog_path, f"{req.field_id or 'nofield'}/truecolor_{cog_uid}.tif"
            )
    except Exception as _e:  # noqa: BLE001
        stats["cog"] = {"written": False, "reason": str(_e)}
    meta = {
        "cog_url": cog_url,
        "cog_crs": cog_crs,
        "srid": (src_crs.to_epsg() if src_crs is not None else 4326),
        "nodata": None,
    }
    return stats, bounds, res_m, meta


def process_pixels(ctx, req, layer_id: str):
    """المعالجة الفعليّة للبكسلات (تعمل عند توفّر rasterio). تُرجع
    (stats, bounds_4326, resolution_m, meta) حيث meta يحوي cog_url/cog_crs/
    srid/nodata. تطبّق القصّ على الحقل + قناع الغيوم + إعادة إسقاط الحدود."""
    import numpy as np
    import rasterio

    # truecolor ليس مؤشّراً طيفيّاً — لا صيغة في _INDICATOR_FORMULAS؛ مسار خاصّ.
    if req.indicator.value == "truecolor":
        return _process_pixels_truecolor(ctx, req, layer_id)

    formula = ctx._INDICATOR_FORMULAS[req.indicator.value]
    with rasterio.open(ctx._safe_raster_source(req.raster_url)) as src:
        res_m = abs(src.res[0])
        b = req.bands

        # ── (٣) إعادة إسقاط الحدود إلى WGS84 الحقيقي ──────────────────
        # المصدر غالباً UTM (Sentinel-2 L2A). نحوّل حدوده الفعليّة من CRS
        # المصدر إلى EPSG:4326 بدل تمرير إحداثيّات UTM كأنّها درجات.
        from rasterio.warp import transform_bounds

        src_crs = src.crs
        if src_crs is not None:
            bounds = list(transform_bounds(src_crs, "EPSG:4326", *src.bounds))
        else:
            bounds = list(src.bounds)

        # ── (١) قصّ على حدود الحقل (clip-to-field) ────────────────────
        # عند توفّر مضلّع الحقل (GeoJSON بـEPSG:4326) نعيد إسقاطه إلى CRS
        # المصدر ونطبّق rasterio.mask.mask(crop=True) فنقرأ بكسلات الحقل
        # فقط؛ البكسلات خارج المضلّع تصبح nodata (→ NaN لاحقاً).
        nodata_val = src.nodata if src.nodata is not None else -9999.0
        clip_geom_src = None
        _out = {"transform": src.transform}  # حاوية قابلة للتعديل من band()
        if req.clip_polygon_geojson:
            from rasterio.warp import transform_geom

            geojson = req.clip_polygon_geojson
            # اقبل Feature / FeatureCollection / Geometry
            geom_in = geojson
            if geojson.get("type") == "Feature":
                geom_in = geojson["geometry"]
            elif geojson.get("type") == "FeatureCollection":
                geom_in = geojson["features"][0]["geometry"]
            # تحقّق من صلاحيّة المضلّع عبر shapely (يرمي عند فساده)
            from shapely.geometry import shape as _shape

            _ = _shape(geom_in)  # يتحقّق من البنية الهندسيّة
            target_crs = src_crs if src_crs is not None else "EPSG:4326"
            clip_geom_src = transform_geom("EPSG:4326", target_crs, geom_in)

        from rasterio.mask import mask as _rio_mask

        def _refl_params(idx):
            """(scale, offset) لتحويل DN→انعكاس: تجاوز الطلب أوّلاً، وإلّا المُعلَن في الراستر.

            صدق: لا يُطبَّق إلّا ما هو مُعلَن أو مُمرَّر صراحةً — لا تخمين. هويّة (1,0) ⇒ لا تغيير.
            """
            scale = req.reflectance_scale
            offset = req.reflectance_offset
            if scale is None and src.scales:  # scale/offset المُعلَن في GDAL (per-band)
                scale = src.scales[idx - 1]
            if offset is None and src.offsets:
                offset = src.offsets[idx - 1]
            return scale, offset

        def band(idx):
            """يقرأ نطاقاً كـfloat32 مع قصّ اختياري + تحويل DN→انعكاس [0,1]."""
            if not idx:
                return None
            if clip_geom_src is not None:
                # filled=False → masked array؛ يُجنِّب OverflowError حين dtype=uint16
                # و nodata_val=-9999.0 خارج النطاق. نملأ القناع بـNaN بعد التحويل.
                arr_b, t = _rio_mask(
                    src,
                    [clip_geom_src],
                    crop=True,
                    filled=False,
                    indexes=[idx],
                )
                _out["transform"] = t
                a = np.ma.filled(arr_b[0].astype("float32"), fill_value=np.nan)
            else:
                a = src.read(idx).astype("float32")
            # حوّل nodata إلى NaN كي لا يلوّث حساب المؤشّر (قبل المقياس كي لا يُزاح الحارس)
            if src.nodata is not None:
                a = np.where(a == src.nodata, np.nan, a)
            a = np.where(a == nodata_val, np.nan, a)
            # تحويل DN→انعكاس [0,1] لصحّة المؤشّرات المعتمِدة على المقياس (EVI/SAVI/MSAVI).
            _sc, _of = _refl_params(idx)
            a = ctx.band_math.to_reflectance(a, _sc, _of, np)
            return a

        def band_raw(idx):
            """يقرأ نطاقاً (مثل SCL) دون تحويل nodata→NaN، مع نفس القصّ."""
            if not idx:
                return None
            if clip_geom_src is not None:
                arr_b, _t = _rio_mask(
                    src,
                    [clip_geom_src],
                    crop=True,
                    filled=True,
                    nodata=0,
                    indexes=[idx],
                )
                return arr_b[0]
            return src.read(idx)

        red = band(b.red)
        nir = band(b.nir)
        green = band(b.green)
        blue = band(b.blue)
        swir1 = band(b.swir1)
        rededge = band(b.rededge) if b.rededge is not None else None
        swir2 = band(b.swir2) if b.swir2 is not None else None
        np.seterr(divide="ignore", invalid="ignore")
        ind = req.indicator.value
        if ind in ctx.band_math.NEW_INDEX_BANDS:
            # المؤشّرات الموسّعة (ndre/evi/msavi/moisture) — صيغ نقيّة مختبَرة
            # في ctx.band_math.py (مصدر واحد للحقيقة، يُعيد استخدام نفس قراءة النطاق).
            arr = ctx.band_math.compute(
                ind,
                {
                    "red": red,
                    "nir": nir,
                    "green": green,
                    "blue": blue,
                    "swir1": swir1,
                    "rededge": rededge,
                },
                np,
            )
        elif ind == "ndvi":
            _d = nir + red
            arr = (nir - red) / np.where(_d == 0, 1e-10, _d)  # حماية القسمة (اتّساقاً مع vari/gli)
        elif ind == "gndvi":
            _d = nir + green
            arr = (nir - green) / np.where(_d == 0, 1e-10, _d)
        elif ind == "reci":
            if rededge is None:
                raise ctx.HTTPException(400, "مؤشّر RECI يحتاج نطاق الحافّة الحمراء B05")
            arr = (nir / np.where(rededge == 0, 1e-10, rededge)) - 1.0
        elif ind == "gci":
            arr = (nir / np.where(green == 0, 1e-10, green)) - 1.0
        elif ind == "arvi":
            rb = 2 * red - blue
            _d = nir + rb
            arr = (nir - rb) / np.where(_d == 0, 1e-10, _d)
        elif ind == "sipi":
            _d = nir - red
            arr = (nir - blue) / np.where(_d == 0, 1e-10, _d)
        elif ind == "nbr":
            _d = nir + swir2
            arr = (nir - swir2) / np.where(_d == 0, 1e-10, _d)
        elif ind == "ccci":
            if rededge is None:
                raise ctx.HTTPException(400, "مؤشّر CCCI يحتاج نطاق الحافّة الحمراء B05")
            ndre_d = nir + rededge
            ndvi_d = nir + red
            ndre_v = (nir - rededge) / np.where(ndre_d == 0, 1e-10, ndre_d)
            ndvi_v = (nir - red) / np.where(ndvi_d == 0, 1e-10, ndvi_d)
            arr = ndre_v / np.where(ndvi_v == 0, 1e-10, ndvi_v)
        elif ind == "msi":
            # Moisture Stress Index: SWIR1/NIR (أعلى = إجهاد مائي أكبر)
            arr = swir1 / np.where(nir == 0, 1e-10, nir)
        elif ind == "ndwi":
            _d = green + nir
            arr = (green - nir) / np.where(_d == 0, 1e-10, _d)
        elif ind == "ndmi":
            _d = nir + swir1
            arr = (nir - swir1) / np.where(_d == 0, 1e-10, _d)
        elif ind == "savi":
            _denom = nir + red + 0.5
            arr = 1.5 * (nir - red) / np.where(_denom == 0, 1e-10, _denom)
        elif ind == "vari":
            # حماية القسمة: المقام قد يبلغ صفراً (green+red=blue) → epsilon
            _denom = green + red - blue
            arr = (green - red) / np.where(_denom == 0, 1e-10, _denom)
        elif ind == "gli":
            # حماية القسمة: المقام قد يبلغ صفراً (نادر) → epsilon
            _denom = 2 * green + red + blue
            arr = (2 * green - red - blue) / np.where(_denom == 0, 1e-10, _denom)
        elif ind == "tgi":
            arr = green - 0.39 * red - 0.61 * blue
        elif ind in ("bsi", "bi", "bi2", "ndti", "dbsi", "ndsi", "satvi"):
            # مؤشّرات التربة — من soil_indices.py
            import soil_indices as si

            if ind == "bsi":
                arr = si.compute_bsi(blue, red, nir, swir2, np)
            elif ind == "bi":
                arr = si.compute_bi(red, green, np)
            elif ind == "bi2":
                arr = si.compute_bi2(red, green, nir, np)
            elif ind == "ndti":
                arr = si.compute_ndti(swir1, swir2, np)
            elif ind == "dbsi":
                _d = nir + red
                _ndvi = (nir - red) / np.where(
                    _d == 0, 1e-10, _d
                )  # حماية القسمة (اتّساقاً مع المؤشّرات أعلاه)
                arr = si.compute_dbsi(green, swir1, _ndvi, np)
            elif ind == "ndsi":
                arr = si.compute_ndsi(swir1, swir2, np)
            else:  # satvi
                arr = si.compute_satvi(red, swir1, swir2, np)
        else:  # fapar تقريب من ndvi
            _d = nir + red
            # حماية القسمة: بكسل أسود/ماء عميق (nir+red=0) كان يعطي nan/inf، وclip
            # كان يحوّل inf→fapar=1 خاطئة فيفسد المتوسّط بصمت. الآن →0 (لا غطاء).
            ndvi = (nir - red) / np.where(_d == 0, 1e-10, _d)
            arr = np.clip(1.24 * ndvi - 0.168, 0, 1)

        # ── (٢) أقنعة جودة البكسل: source-native strategy + saturation proxy ─────────
        # لا نُعامل cloud mask كـboolean هش. نختار استراتيجية حسب source_format
        # (Sentinel-2 SCL/CLM/CLP، Landsat QA_PIXEL، أو NoOp صريح للدرون/المخصص).
        # يبقى saturation proxy منفصلاً لأنه ليس cloud mask حسياً بل فحص reflectance.
        cloud_pct = None
        shadow_pct = None
        snow_pct = None
        aerosol_pct = None
        saturation_pct = None
        cloud_mask_sources: list[str] = []
        cloud_shadow_mask_sources: list[str] = []
        snow_mask_sources: list[str] = []
        aerosol_mask_sources: list[str] = []
        saturation_mask_sources: list[str] = []
        cloud_mask = None
        shadow_mask = None
        snow_mask = None
        saturation_mask = None
        cloud_strategy_name = "not_requested"
        cloud_strategy_warnings: list[str] = []
        if req.apply_cloud_mask:
            strategy = raster_cloud_mask_strategies.strategy_for_source_format(
                str(getattr(req, "source_format", "") or "")
            )
            cloud_strategy_name = strategy.name
            mask_result = strategy.apply(
                np=np,
                band_reader=band_raw,
                band_mapping=b,
                target_shape=arr.shape,
            )
            cloud_strategy_warnings = list(mask_result.warnings or [])
            cloud_mask = mask_result.mask
            cloud_pct = mask_result.cloud_pct
            shadow_mask = mask_result.shadow_mask
            shadow_pct = mask_result.shadow_pct
            snow_mask = mask_result.snow_mask
            snow_pct = mask_result.snow_pct
            cloud_mask_sources = list(mask_result.sources or [])
            if shadow_mask is not None:
                cloud_shadow_mask_sources = [
                    s for s in cloud_mask_sources if s in {"SCL", "QA_PIXEL"}
                ]
            if snow_mask is not None:
                snow_mask_sources = [s for s in cloud_mask_sources if s in {"SCL", "QA_PIXEL"}]

            # Saturation proxy: بعد التحويل إلى reflectance، القيم غير المنطقية أو ذات الحافة
            # العليا جداً تفقد الثقة. هذه ليست طبقة sensor-QA؛ لذلك نُسميها reflectance_proxy.
            finite_bands = [
                x for x in [red, nir, green, blue, swir1, rededge, swir2] if x is not None
            ]
            if finite_bands:
                saturation_mask = np.zeros_like(arr, dtype=bool)
                for _band_arr in finite_bands:
                    if getattr(_band_arr, "shape", None) == arr.shape:
                        saturation_mask = np.logical_or(
                            saturation_mask,
                            np.logical_or(_band_arr < -0.05, _band_arr > 1.20),
                        )
                if bool(np.any(saturation_mask)):
                    saturation_mask_sources.append("reflectance_range_proxy")

            combined_mask = None
            for _mask in [cloud_mask, shadow_mask, snow_mask, saturation_mask]:
                if _mask is not None:
                    combined_mask = (
                        _mask if combined_mask is None else np.logical_or(combined_mask, _mask)
                    )
            if combined_mask is not None:
                saturation_pct = (
                    float(np.mean(saturation_mask) * 100.0) if saturation_mask is not None else None
                )
                arr = np.where(combined_mask, np.nan, arr)
            else:
                ctx.logger.warning(
                    "cloud/quality mask requested but strategy %s produced no mask for layer %s; proceeding unmasked warnings=%s",
                    cloud_strategy_name,
                    layer_id,
                    cloud_strategy_warnings,
                )

        valid = np.isfinite(arr)
        vals = arr[valid]
        total_px = int(valid.size) if hasattr(valid, "size") else 0
        valid_ratio = (float(valid.sum()) / float(total_px)) if total_px else 0.0
        qa_layer_present = bool(
            cloud_mask_sources
            or cloud_shadow_mask_sources
            or snow_mask_sources
            or aerosol_mask_sources
            or saturation_mask_sources
        )
        topographic_qa = _topographic_qa_for_indicator(
            ctx,
            req=req,
            raster_crs=src_crs,
            raster_transform=_out["transform"],
            raster_shape=arr.shape,
        )
        pixel_qa = raw_data_processing.compute_quality_score(
            valid_pixel_ratio=valid_ratio,
            cloud_pct=cloud_pct,
            shadow_pct=shadow_pct,
            snow_pct=snow_pct,
            aerosol_pct=aerosol_pct,
            saturation_pct=saturation_pct,
            terrain_shadow_risk_pct=topographic_qa.get("terrain_shadow_risk_pct"),
            slope_risk_pct=topographic_qa.get("slope_risk_pct"),
            topographic_qa_applied=bool(topographic_qa.get("topographic_qa_applied")),
            cloud_mask_applied=bool(cloud_pct is not None),
            cloud_shadow_mask_applied=bool(shadow_pct is not None),
            snow_mask_applied=bool(snow_pct is not None),
            aerosol_mask_applied=bool(aerosol_pct is not None),
            saturation_mask_applied=bool(saturation_pct is not None),
            qa_layer_present=qa_layer_present,
        )
        min_raw_quality_score = float(getattr(req, "min_raw_quality_score", 0.0) or 0.0)
        if (
            bool(getattr(req, "raw_qa_required", True))
            and pixel_qa["quality_score"] < min_raw_quality_score
        ):
            raise ctx.HTTPException(
                422,
                {
                    "code": "raw_raster_quality_below_threshold",
                    "quality_score": pixel_qa["quality_score"],
                    "min_raw_quality_score": min_raw_quality_score,
                    "warnings": pixel_qa.get("warnings", []),
                },
            )
        quality = ctx._quality_from_cloud_pct(cloud_pct, masked=bool(cloud_pct is not None))
        stats = {
            "min": float(np.min(vals)) if vals.size else 0.0,
            "max": float(np.max(vals)) if vals.size else 0.0,
            "mean": float(np.mean(vals)) if vals.size else 0.0,
            "std": float(np.std(vals)) if vals.size else 0.0,
            "valid_pixels": int(valid.sum()),
            "nodata_pixels": int((~valid).sum()),
            "cloud_pct": cloud_pct,
            "cloud_mask_applied": bool(cloud_pct is not None),
            "cloud_mask_sources": cloud_mask_sources,
            "cloud_mask_strategy": cloud_strategy_name,
            "cloud_mask_strategy_warnings": cloud_strategy_warnings,
            "shadow_pct": shadow_pct,
            "snow_pct": snow_pct,
            "aerosol_pct": aerosol_pct,
            "saturation_pct": saturation_pct,
            "confidence": quality["confidence"],
            "quality": quality["quality"],
            "quality_reason": quality["reason"],
            "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
            "raw_quality_score": pixel_qa["quality_score"],
            "pixel_qa": pixel_qa,
            "topographic_qa": topographic_qa,
            "quality_flags": raw_data_processing.build_quality_flags(
                nodata_mask_applied=True,
                qa_layer_present=qa_layer_present,
                cloud_mask_applied=bool(cloud_pct is not None),
                cloud_shadow_mask_applied=bool(shadow_pct is not None),
                snow_mask_applied=bool(snow_pct is not None),
                aerosol_mask_applied=bool(aerosol_pct is not None),
                saturation_mask_applied=bool(saturation_pct is not None),
                topographic_qa_applied=bool(topographic_qa.get("topographic_qa_applied")),
                terrain_shadow_risk_applied=topographic_qa.get("terrain_shadow_risk_pct")
                is not None,
                slope_risk_applied=topographic_qa.get("slope_risk_pct") is not None,
                cloud_mask_sources=cloud_mask_sources,
                cloud_shadow_mask_sources=cloud_shadow_mask_sources,
                snow_mask_sources=snow_mask_sources,
                aerosol_mask_sources=aerosol_mask_sources,
                saturation_mask_sources=saturation_mask_sources,
                topographic_qa_sources=topographic_qa.get("sources", []),
            ),
        }
        cog_crs = str(src_crs or "EPSG:4326")

        _cloud_strategy = cloud_strategy_name
        validated_product = raster_validated_product.build_validated_raster_product(
            req=req,
            pixel_qa=pixel_qa,
            quality_flags=stats["quality_flags"],
            spatial_crs=cog_crs,
            bounds_4326=bounds,
            topographic_qa=topographic_qa,
            cloud_mask_strategy=_cloud_strategy,
            reflectance_normalized=True,
            source_uri=getattr(req, "raster_url", None),
        )
        raster_validated_product.assert_indicator_accepts_validated_product(validated_product)
        stats["validated_raster_product"] = validated_product.model_dump(mode="json")
        # احفظ المؤشّر المحسوب كـCOG محسّن (ضغط + بلاطات + أهرامات) — تحسين
        # التخزين: حجم أصغر + قراءة جزئيّة أسرع (TiTiler/MapLibre). نحفظ المؤشّر
        # المقصوص بـtransform المقصوص (out) وبـCRS المصدر الأصلي (UTM غالباً).
        cog_url = None
        cog_crs = str(src_crs or "EPSG:4326")
        RASTER_NODATA = ctx.RASTER_NODATA
        try:
            import cog_writer

            cog_uid = uuid.uuid4().hex[:8]
            cog_path = os.path.join(ctx.UPLOAD_DIR, f"{req.indicator.value}_{cog_uid}.tif")
            cog_info = cog_writer.write_cog(
                arr, cog_path, _out["transform"], crs=cog_crs, nodata=RASTER_NODATA
            )
            stats["cog"] = cog_info
            if cog_info.get("written"):
                # (٤) خزّن مسار COG كـURI كي يجده tilejson + شبكة المؤشّر.
                # عند ضبط S3 يُرفع الـCOG ويُخزَّن s3://؛ وإلّا يبقى file:// كما هو.
                cog_url = ctx.object_store.upload_cog(
                    cog_path,
                    f"{req.field_id or 'nofield'}/{req.indicator.value}_{cog_uid}.tif",
                )
        except Exception as _e:  # noqa: BLE001 — حفظ COG اختياري لا يُفشل الحساب
            stats["cog"] = {"written": False, "reason": str(_e)}
        _ = formula  # موثّق أعلاه
        meta = {
            "cog_url": cog_url,
            "cog_crs": cog_crs,
            "srid": (src_crs.to_epsg() if src_crs is not None else 4326),
            "nodata": RASTER_NODATA,
            "pixel_qa": pixel_qa,
            "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
        }
        return stats, bounds, res_m, meta
