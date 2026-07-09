"""Pixel-processing helpers for raster-service main.py decomposition.

This module owns pure raster pixel/COG processing while main.py keeps thin
compatibility wrappers during the staged split.  A `ctx` module object is passed
from main.py so behaviour remains byte-for-byte compatible with existing
runtime state and private helpers.
"""

from __future__ import annotations

import os
import uuid


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
    stats = {
        "min": float(np.min(vals)) if vals.size else 0.0,
        "max": float(np.max(vals)) if vals.size else 0.0,
        "mean": float(np.mean(vals)) if vals.size else 0.0,
        "std": float(np.std(vals)) if vals.size else 0.0,
        "valid_pixels": int(valid.sum()),
        "nodata_pixels": int((~valid).sum()),
    }
    cog_url = None
    cog_crs = str(src_crs or "EPSG:4326")
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
    stats = {
        "min": 0.0,
        "max": 255.0,
        "mean": 0.0,
        "std": 0.0,
        "valid_pixels": int(valid.sum()),
        "nodata_pixels": int((~valid).sum()),
    }
    cog_url = None
    cog_crs = str(src_crs or "EPSG:4326")
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
    }
    return stats, bounds, res_m, meta


def process_pixels(ctx, req, layer_id: str):
    """المعالجة الفعليّة للبكسلات (تعمل عند توفّر rasterio). تُرجع
    (stats, bounds_4326, resolution_m, meta) حيث meta يحوي cog_url/cog_crs/
    srid/nodata. تطبّق القصّ على الحقل + قناع الغيوم + إعادة إسقاط الحدود."""
    import numpy as np
    import rasterio

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
                arr_b, t = _rio_mask(
                    src,
                    [clip_geom_src],
                    crop=True,
                    filled=True,
                    nodata=nodata_val,
                    indexes=[idx],
                )
                _out["transform"] = t
                a = arr_b[0].astype("float32")
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
            arr = 1.5 * (nir - red) / (nir + red + 0.5)
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

        # ── (٢) قناع الغيوم (SCL + CLM/CLP s2cloudless) ────────────────
        # أفضل الممارسات: لا نعتمد SCL وحده عندما تتوفر CLM/CLP؛ ندمج SCL
        # مع قناع/احتمالية s2cloudless. SCL أصناف الغيوم/الظلال = {3,8,9,10,11}.
        cloud_pct = None
        cloud_mask_sources: list[str] = []
        if req.apply_cloud_mask:
            masks = []
            if b.scl is not None:
                scl = band_raw(b.scl)
                if scl is not None and scl.shape == arr.shape:
                    masks.append(np.isin(scl, [3, 8, 9, 10, 11]))
                    cloud_mask_sources.append("SCL")
                else:
                    ctx.logger.warning(
                        "cloud mask requested but SCL band could not be read or shape mismatched for layer %s",
                        layer_id,
                    )
            if b.clm is not None:
                clm = band_raw(b.clm)
                if clm is not None and clm.shape == arr.shape:
                    masks.append(clm.astype("float32") > 0)
                    cloud_mask_sources.append("CLM")
                else:
                    ctx.logger.warning(
                        "cloud mask requested but CLM band could not be read or shape mismatched for layer %s",
                        layer_id,
                    )
            if b.clp is not None:
                clp = band_raw(b.clp)
                if clp is not None and clp.shape == arr.shape:
                    clp_f = clp.astype("float32")
                    # Accept both 0..1 and 0..100 probability encodings.
                    threshold = 0.40 if float(np.nanmax(clp_f)) <= 1.0 else 40.0
                    masks.append(clp_f >= threshold)
                    cloud_mask_sources.append("CLP")
                else:
                    ctx.logger.warning(
                        "cloud mask requested but CLP band could not be read or shape mismatched for layer %s",
                        layer_id,
                    )
            if masks:
                cloud_classes = masks[0]
                for m in masks[1:]:
                    cloud_classes = np.logical_or(cloud_classes, m)
                cloud_pct = float(np.mean(cloud_classes) * 100.0) if cloud_classes.size else None
                arr = np.where(cloud_classes, np.nan, arr)
            else:
                ctx.logger.warning(
                    "cloud mask requested but no SCL/CLM/CLP quality band is available for layer %s; proceeding unmasked",
                    layer_id,
                )

        valid = np.isfinite(arr)
        vals = arr[valid]
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
            "confidence": quality["confidence"],
            "quality": quality["quality"],
            "quality_reason": quality["reason"],
        }
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
        }
        return stats, bounds, res_m, meta
