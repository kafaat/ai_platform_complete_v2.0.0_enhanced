"""Pixel-processing helpers for raster-service main.py decomposition.

This module owns pure raster pixel/COG processing while main.py keeps thin
compatibility wrappers during the staged split.  A `ctx` module object is passed
from main.py so behaviour remains byte-for-byte compatible with existing
runtime state and private helpers.
"""

from __future__ import annotations

import json
import math
import os
import uuid

import raster_cloud_mask_strategies
import raster_security_context
import raster_settings
import raster_topographic_qa
import raster_validated_product
import raw_data_processing

# WGS84 ellipsoid (EPSG:7030) for metres-per-degree on geographic grids.
_WGS84_A_M = 6378137.0
_WGS84_E2 = 0.0066943799901413165


def _ground_pixel_size_m(crs, transform, shape) -> tuple[float, float] | None:
    """Ground spacing ``(x_m, y_m)`` of one pixel of a grid, or ``None`` if unknown.

    Derived from the final output grid (CRS + affine transform + shape), per
    axis, so a geographic grid is never read as metres:

    - projected CRS: column/row step x the CRS linear unit (metre, US foot, ...);
    - geographic CRS: column/row step in degrees x the WGS84 meridional and
      prime-vertical radii at the grid-centre latitude (x shrinks with cos(lat));
    - missing CRS, engineering CRS or a degenerate transform: ``None`` — callers
      must not publish a metric number they cannot attest.
    """

    if crs is None or transform is None or not shape:
        return None
    try:
        from rasterio.crs import CRS

        crs_obj = CRS.from_user_input(crs)
        # Column step (a, d) and row step (b, e) in CRS units; rotation-safe.
        col_step = (float(transform.a), float(transform.d))
        row_step = (float(transform.b), float(transform.e))
        if crs_obj.is_projected:
            _unit, factor = crs_obj.linear_units_factor
            x_m = math.hypot(*col_step) * float(factor)
            y_m = math.hypot(*row_step) * float(factor)
        elif crs_obj.is_geographic:
            _unit, radians_per_unit = crs_obj.units_factor
            deg_per_unit = math.degrees(float(radians_per_unit))
            h, w = int(shape[-2]), int(shape[-1])
            _lon_c, lat_c = transform * (w / 2.0, h / 2.0)
            phi = math.radians(float(lat_c) * deg_per_unit)
            s2 = math.sin(phi) ** 2
            prime_vertical = _WGS84_A_M / math.sqrt(1.0 - _WGS84_E2 * s2)
            meridional = _WGS84_A_M * (1.0 - _WGS84_E2) / (1.0 - _WGS84_E2 * s2) ** 1.5
            m_per_deg_lon = math.radians(1.0) * prime_vertical * math.cos(phi)
            m_per_deg_lat = math.radians(1.0) * meridional
            x_m = math.hypot(
                col_step[0] * deg_per_unit * m_per_deg_lon,
                col_step[1] * deg_per_unit * m_per_deg_lat,
            )
            y_m = math.hypot(
                row_step[0] * deg_per_unit * m_per_deg_lon,
                row_step[1] * deg_per_unit * m_per_deg_lat,
            )
        else:
            return None
    except Exception:  # noqa: BLE001 — unknown units ⇒ no metric spacing (fail closed)
        return None
    if not (math.isfinite(x_m) and math.isfinite(y_m) and x_m > 0 and y_m > 0):
        return None
    return x_m, y_m


def _grid_bounds_4326(crs, transform, shape) -> list[float]:
    """WGS84 bounds of the final output grid (after any crop), not of the source.

    Same convention as the previous ``src.bounds`` path: a CRS-less grid keeps its
    native coordinates.
    """
    from rasterio.transform import array_bounds
    from rasterio.warp import transform_bounds

    west, south, east, north = array_bounds(int(shape[-2]), int(shape[-1]), transform)
    if crs is None:
        return [west, south, east, north]
    return list(transform_bounds(crs, "EPSG:4326", west, south, east, north))


def _ground_resolution_m(crs, transform, shape) -> float | None:
    """Published ``resolution_m``: ground x-spacing in metres, ``None`` if unknown."""
    spacing = _ground_pixel_size_m(crs, transform, shape)
    return spacing[0] if spacing is not None else None


def _cog_publishable(cog_info: dict) -> bool:
    """بوّابة الرفع (P2-PUB-2): COG يُرفَع فقط إن كُتِب **و**اجتاز تدقيق البنية.

    ``validation.valid`` كان معلوماتيّاً فحسب: يُرفَع COG غير صالح ويُحفَظ ويُنشَر لأنّ
    الشرط كان ``written`` وحده. ``valid`` غير ``True`` (False/None/غائب) ⇒ لا رفع، فلا
    ``cog_url`` ولا إدامة، وتنتهي المهمّة غير مؤهَّلة للنشر مع بقاء الحكم ظاهراً في
    ``stats["cog"]["validation"]`` للتشخيص.
    """
    return bool(cog_info.get("written")) and (cog_info.get("validation") or {}).get("valid") is True


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
        # Slope is rise over *ground* run: per-axis metres of the indicator grid,
        # never its CRS units (a 0.00027° grid is ~29 m, not 0.00027 m).
        spacing_m = _ground_pixel_size_m(raster_crs, raster_transform, raster_shape)
        if spacing_m is None:
            return raster_topographic_qa.build_topographic_qa(
                dem_configured=True,
                dem_aligned=True,
                hillshade_available=False,
                sun_geometry_available=bool(
                    sun_azimuth_deg is not None and sun_altitude_deg is not None
                ),
                sources=sources + ["indicator_grid_dem_alignment"],
                extra_warnings=["raster_grid_ground_spacing_unknown"],
            )
        out = raster_topographic_qa.build_topographic_qa_from_dem_array(
            dst,
            pixel_size_m=spacing_m[0],
            pixel_size_y_m=spacing_m[1],
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


def _admit_min_raw_quality(ctx, req, pixel_qa: dict) -> None:
    """بوّابة قبول QA واحدة لكلّ فرع (scalar · precomputed · truecolor) قبل أيّ كتابة COG.

    ``raw_qa_required`` مع ``min_raw_quality_score`` يرفضان المنتَج بـ422 إن قلّت درجته
    المحسوبة عن الحدّ المطلوب؛ لا فرع يتجاوز الحدّ بصمت (P2-CDSE-1).
    """
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


def process_precomputed_pixels(ctx, req, layer_id: str):
    """مسار CDSE: المؤشّر محسوب خادميّاً (evalscript) فالراستر نطاق-واحد جاهز.

    يقرأ النطاق الأوّل مباشرةً (لا band math، لا تحويل انعكاس)، يعيد إسقاط الحدود إلى
    EPSG:4326، يحسب الإحصاءات، ويكتب COG محسّناً (نفس مسار التخزين/الأصل). يُرجِع
    ``(stats, bounds_4326, resolution_m, meta)`` بنفس تعاقُد :func:`_process_pixels`.
    Native receipts supply measured SCL/dataMask; legacy single-band bytes have no QA proof.
    """
    import cdse_native_product
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds

    # الصورة الخام (truecolor) راستر RGBA متعدّد النطاقات — مسار حفظ منفصل (لا إحصاء
    # مؤشّر/نطاق واحد؛ لا يمرّ عبر ctx._INDICATOR_FORMULAS). يقرأ 4 نطاقات ويكتب COG RGBA.
    if req.indicator.value == "truecolor":
        return process_precomputed_truecolor(ctx, req)

    native = getattr(req, "_cdse_native_product", None)
    observed = None
    with rasterio.open(ctx._safe_raster_source(req.raster_url)) as src:
        # دقّة أرضيّة بالأمتار (CDSE يُسلِّم EPSG:4326 بالدرجات) — لا وحدات CRS كأمتار.
        res_m = _ground_resolution_m(src.crs, src.transform, src.shape)
        src_crs = src.crs
        if src_crs is not None:
            bounds = list(transform_bounds(src_crs, "EPSG:4326", *src.bounds))
        else:
            bounds = list(src.bounds)
        # الحجم يُفحَص **قبل** التخصيص كنظيره truecolor أدناه (EXTRA-10): الرابط حرّ عبر
        # `safe_raster_source`، والفرعان يقرآن المجموعة كاملةً — الإرث نطاقه الأوّل
        # (`read(1, masked=True)` + float32)، والأصليّ نطاقاته الأربعة.
        raster_security_context.assert_readable_size(
            src,
            what="scalar precomputed",
            ceiling=raster_settings.RASTER_MAX_READ_BAND_PIXELS,
        )
        if isinstance(native, cdse_native_product.NativeProduct):
            arr, observed = cdse_native_product.measured_pixels(src, native, req.raster_url)
            # Only actual returned contributors can replace catalogue/request guesses.
            req.scene_id = observed["scene_id"]
            req.capture_datetime = observed["acquisition_datetime"]
        else:
            arr = src.read(1, masked=True).astype("float32").filled(np.nan)
        if src.nodata is not None:
            arr = np.where(arr == src.nodata, np.nan, arr)
        transform = src.transform

    valid = np.isfinite(arr)
    vals = arr[valid]
    if not vals.size:
        raise ctx.HTTPException(422, {"code": "raw_raster_no_valid_pixels", "valid_pixels": 0})
    total_px = int(valid.size) if hasattr(valid, "size") else 0
    valid_ratio = (float(valid.sum()) / float(total_px)) if total_px else 0.0
    topographic_qa = _topographic_qa_for_indicator(
        ctx, req=req, raster_crs=src_crs, raster_transform=transform, raster_shape=arr.shape
    )
    pixel_qa = raw_data_processing.compute_quality_score(
        valid_pixel_ratio=valid_ratio,
        cloud_pct=observed["cloud_pct"] if observed else None,
        cloud_mask_applied=observed is not None,
        terrain_shadow_risk_pct=topographic_qa.get("terrain_shadow_risk_pct"),
        cast_shadow_risk_pct=topographic_qa.get("cast_shadow_risk_pct"),
        slope_risk_pct=topographic_qa.get("slope_risk_pct"),
        topographic_qa_applied=bool(topographic_qa.get("topographic_qa_applied")),
        qa_layer_present=observed is not None,
    )
    _admit_min_raw_quality(ctx, req, pixel_qa)
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
            qa_layer_present=observed is not None,
            cloud_mask_applied=observed is not None,
            topographic_qa_applied=bool(topographic_qa.get("topographic_qa_applied")),
            terrain_shadow_risk_applied=topographic_qa.get("terrain_shadow_risk_pct") is not None,
            cast_shadow_risk_applied=topographic_qa.get("cast_shadow_risk_pct") is not None,
            slope_risk_applied=topographic_qa.get("slope_risk_pct") is not None,
            topographic_qa_sources=topographic_qa.get("sources", []),
            source_native_qa_policy=(
                cdse_native_product.MASK_VERSION
                if observed
                else "precomputed_index_provider_mask_expected"
            ),
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
        cloud_mask_strategy=(
            cdse_native_product.MASK_VERSION if observed else "provider_precomputed_expected"
        ),
        reflectance_normalized=False,
        source_uri=getattr(req, "raster_url", None),
    )
    if observed:
        validated_product.provenance.algorithm_version = observed["algorithm_version"]
        validated_product.provenance.qa_mask_version = observed["qa_mask_version"]
        validated_product.provenance.input_checksum = observed["input_checksum"]
        stats["quality_score"] = pixel_qa["quality_score"]
        stats["quality_score_semantics"] = pixel_qa["schema"]
        stats["cloud_pct"] = observed["cloud_pct"]
        stats["cdse_native_qa"] = observed
    raster_validated_product.assert_indicator_accepts_validated_product(validated_product)
    stats["validated_raster_product"] = validated_product.model_dump(mode="json")
    RASTER_NODATA = ctx.RASTER_NODATA
    try:
        import cog_writer

        cog_uid = uuid.uuid4().hex[:8]
        cog_path = os.path.join(ctx.UPLOAD_DIR, f"{req.indicator.value}_{cog_uid}.tif")
        cog_info = cog_writer.write_cog(arr, cog_path, transform, crs=cog_crs, nodata=RASTER_NODATA)
        stats["cog"] = cog_info
        if _cog_publishable(cog_info):
            cog_url = ctx.object_store.upload_cog(
                cog_path, f"{req.field_id or 'nofield'}/{req.indicator.value}_{cog_uid}.tif"
            )
    except Exception as _e:  # noqa: BLE001 — حفظ COG اختياري لا يُفشل الحساب
        stats["cog"] = {"written": False, "reason": str(_e)}
    meta = {
        "cog_url": cog_url,
        "cog_crs": cog_crs,
        "srid": (src_crs.to_epsg() if src_crs is not None else 4326),
        "resolution_m": res_m,  # كي لا يسقط السجلّ إلى 10 م افتراضيّاً
        "nodata": RASTER_NODATA,
        "pixel_qa": pixel_qa,
        "topographic_qa": topographic_qa,
        "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
    }
    return stats, bounds, res_m, meta


def process_precomputed_truecolor(ctx, req):
    """مسار CDSE للصورة الخام (truecolor): الراستر RGBA (4 نطاقات UINT8) جاهز خادميّاً.

    يقرأ نوافذ محدودة ويحسب التوفّر من قناع المصدر وألفا (لا min/max/mean لمؤشّر —
    RGB بلا معنًى إحصائيّ)، ويكتب COG RGBA محسّناً (``write_rgba_cog_source``) ثمّ يرفعه. يُرجِع
    ``(stats, bounds_4326, resolution_m, meta)`` بنفس تعاقُد :func:`_process_precomputed_pixels`."""
    import cog_writer
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(ctx._safe_raster_source(req.raster_url)) as src:
        # دقّة أرضيّة بالأمتار (CDSE يُسلِّم EPSG:4326 بالدرجات) — لا وحدات CRS كأمتار.
        res_m = _ground_resolution_m(src.crs, src.transform, src.shape)
        src_crs = src.crs
        if src_crs is not None:
            bounds = list(transform_bounds(src_crs, "EPSG:4326", *src.bounds))
        else:
            bounds = list(src.bounds)
        # الحجم يُفحَص **قبل** التخصيص: `safe_raster_source` يقبل أيّ رابط http(s) غير
        # محجوب، فأبعاد المصدر ليست تحت سيطرة الخدمة. `rasterio.open` أعطاها بلا قراءة.
        raster_security_context.assert_readable_size(
            src,
            what="truecolor precomputed",
            ceiling=raster_settings.RASTER_MAX_READ_BAND_PIXELS,
        )
        if (
            src.crs is None
            or src.count not in (3, 4)
            or any(dtype != "uint8" for dtype in src.dtypes)
        ):
            raise ctx.HTTPException(422, {"code": "invalid_truecolor_source"})
        transform = src.transform
        total_px = src.height * src.width
        valid_pixels = 0
        for window in cog_writer.write_windows(src.height, src.width):
            valid = src.dataset_mask(window=window) > 0
            if src.count == 4:
                valid &= src.read(4, window=window) > 0
            valid_pixels += int(valid.sum())

        valid_ratio = float(valid_pixels) / total_px if total_px else 0.0
        if not valid_pixels:
            raise ctx.HTTPException(422, {"code": "raw_raster_no_valid_pixels", "valid_pixels": 0})
        topographic_qa = _topographic_qa_for_indicator(
            ctx, req=req, raster_crs=src_crs, raster_transform=transform, raster_shape=src.shape
        )
        pixel_qa = raw_data_processing.compute_quality_score(
            valid_pixel_ratio=valid_ratio,
            cloud_pct=None,
            cloud_mask_applied=False,
            terrain_shadow_risk_pct=topographic_qa.get("terrain_shadow_risk_pct"),
            cast_shadow_risk_pct=topographic_qa.get("cast_shadow_risk_pct"),
            slope_risk_pct=topographic_qa.get("slope_risk_pct"),
            topographic_qa_applied=bool(topographic_qa.get("topographic_qa_applied")),
            qa_layer_present=src.count == 4,
        )
        _admit_min_raw_quality(ctx, req, pixel_qa)
        stats = {
            "min": 0.0,
            "max": 255.0,
            "mean": 0.0,
            "std": 0.0,
            "valid_pixels": valid_pixels,
            "nodata_pixels": total_px - valid_pixels,
            "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
            "raw_quality_score": pixel_qa["quality_score"],
            "pixel_qa": pixel_qa,
            "topographic_qa": topographic_qa,
            "quality_flags": raw_data_processing.build_quality_flags(
                nodata_mask_applied=True,
                qa_layer_present=src.count == 4,
                cloud_mask_applied=False,
                saturation_mask_applied=False,
                topographic_qa_applied=bool(topographic_qa.get("topographic_qa_applied")),
                terrain_shadow_risk_applied=topographic_qa.get("terrain_shadow_risk_pct")
                is not None,
                cast_shadow_risk_applied=topographic_qa.get("cast_shadow_risk_pct") is not None,
                slope_risk_applied=topographic_qa.get("slope_risk_pct") is not None,
                topographic_qa_sources=topographic_qa.get("sources", []),
                cloud_mask_sources=["alpha"] if src.count == 4 else [],
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
            cog_uid = uuid.uuid4().hex[:8]
            cog_path = os.path.join(ctx.UPLOAD_DIR, f"truecolor_{cog_uid}.tif")
            cog_info = cog_writer.write_rgba_cog_source(src, cog_path)
            stats["cog"] = cog_info
            if _cog_publishable(cog_info):
                cog_url = ctx.object_store.upload_cog(
                    cog_path, f"{req.field_id or 'nofield'}/truecolor_{cog_uid}.tif"
                )
        except Exception as _e:  # noqa: BLE001 — حفظ COG اختياري لا يُفشل المعالجة
            stats["cog"] = {"written": False, "reason": str(_e)}
        meta = {
            "cog_url": cog_url,
            "cog_crs": cog_crs,
            "srid": (src_crs.to_epsg() if src_crs is not None else 4326),
            "resolution_m": res_m,  # كي لا يسقط السجلّ إلى 10 م افتراضيّاً
            "nodata": None,  # RGBA يستخدم قناة ألفا لا قيمة nodata
            "pixel_qa": pixel_qa,
            "topographic_qa": topographic_qa,
            "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
        }
        return stats, bounds, res_m, meta


def _pixel_read_context(src, clip_geom_src):
    """Identity for a read-only batch dataset and its exact output grid/mask.

    Retain the dataset itself, not its filename or id: another open of the same
    path may contain different pixels, and an id can be reused after collection.
    The caller owns this short-lived cache and must not mutate source pixels
    during the batch. Metadata and clipping changes still get separate entries.
    """
    return (
        src,
        tuple(src.transform),
        str(src.crs),
        tuple(src.shape),
        tuple(src.nodatavals),
        tuple(src.dtypes),
        json.dumps(clip_geom_src, sort_keys=True, separators=(",", ":")),
    )


def _reflectance_cache_params(scale, offset):
    """Use the same effective numeric transform as band_math.to_reflectance."""
    return (1.0 if scale is None else float(scale), 0.0 if offset is None else float(offset))


def _process_pixels_truecolor(ctx, req, layer_id: str, *, shared_src=None, shared_cache=None):
    """مسار Element84 للصورة الخام (truecolor): يقرأ نطاقات RGB من VRT،
    يحوّلها إلى RGBA uint8، ويكتب COG ويرجع (stats, bounds_4326, res_m, meta)."""
    from contextlib import nullcontext

    import numpy as np
    import rasterio
    from rasterio.mask import mask as _rio_mask

    _src_cm = (
        nullcontext(shared_src)
        if shared_src is not None
        else rasterio.open(ctx._safe_raster_source(req.raster_url))
    )
    with _src_cm as src:
        src_crs = src.crs
        b = req.bands

        # ── Fix 1: قصّ على حدود الحقل قبل قراءة البكسلات (windowed read) ──
        # بدون قصّ، src.read(idx) يقرأ حزمة Sentinel-2 الكاملة (10980×10980،
        # ~1.4 GB/نطاق) ويُعطّل العامل بنفاد الذاكرة. نُعيد إسقاط الحقل إلى
        # CRS المصدر ونستخدم rasterio.mask.mask(crop=True) لقراءة منطقة الحقل
        # فقط (<5 MB للحقول الزراعيّة الاعتياديّة).
        clip_geom_src = None
        _clip_out: dict = {}  # يخزّن transform وشكل المصفوفة بعد القصّ
        if req.clip_polygon_geojson:
            from rasterio.warp import transform_geom

            geojson = req.clip_polygon_geojson
            geom_in = geojson
            if geojson.get("type") == "Feature":
                geom_in = geojson["geometry"]
            elif geojson.get("type") == "FeatureCollection":
                geom_in = geojson["features"][0]["geometry"]
            target_crs = src_crs if src_crs is not None else "EPSG:4326"
            clip_geom_src = transform_geom("EPSG:4326", target_crs, geom_in)

        read_context = _pixel_read_context(src, clip_geom_src)

        def _read_uint8(idx):
            """يُرجِع (لون uint8، قناع صلاحيّة) للنطاق؛ نطاق غائب ⇒ (أصفار، None).

            الصلاحيّة (nodata المُعلَن + القناع الداخليّ + خارج المضلّع) تُحمَل منفصلةً
            عن اللون **قبل** التكميم: البكسل الصالح الأسود/الخافت (انعكاس < 1/255) يبقى
            صالحاً وإن صار RGB 0 (P2-COL-1)، والقناع الداخليّ يُحترَم بلا مضلّع (P2-COL-2).
            """
            if not idx:
                shape = _clip_out.get("shape") or src.shape
                return np.zeros(shape, dtype=np.uint8), None
            _sc = req.reflectance_scale
            _of = req.reflectance_offset
            # Preserve the existing truecolor-only Sentinel-2 fallback, but only for
            # undeclared calibration: an explicit request scale (even the identity 1)
            # always wins, so calibrated reflectance is not scaled twice (P2-COL-3).
            # A raster scale of 1.0 is GDAL's "undeclared" default, not an attestation.
            if _sc is None and src.scales:
                _sc = src.scales[idx - 1]
                if (
                    _sc is not None
                    and float(_sc) == 1.0
                    and req.source_format == ctx.SourceFormat.sentinel2_l2a
                ):
                    _sc = None
            if _of is None and src.offsets:
                _of = src.offsets[idx - 1]
            if _sc is None and req.source_format == ctx.SourceFormat.sentinel2_l2a:
                _sc = 0.0001
            cache_key = (
                "truecolor_uint8",
                read_context,
                int(idx),
                _reflectance_cache_params(_sc, _of),
            )
            if shared_cache is not None and cache_key in shared_cache:
                out, valid, transform = shared_cache[cache_key]
                _clip_out.update(transform=transform, shape=out.shape)
                return out, valid
            if clip_geom_src is not None:
                # filled=False → masked array؛ يُجنِّب OverflowError حين nodata خارج uint16
                arr_b, t = _rio_mask(
                    src,
                    [clip_geom_src],
                    crop=True,
                    filled=False,
                    indexes=[idx],
                )
                _clip_out["transform"] = t
                _clip_out["shape"] = arr_b.shape[1:]  # (H, W) of clipped window
                raw = np.ma.filled(arr_b[0].astype("float32"), fill_value=np.nan)
            else:
                # masked=True يحمل nodata والقناع الداخليّ كما في مسار المؤشّرات.
                raw = np.ma.filled(src.read(idx, masked=True).astype("float32"), np.nan)
            if src.nodata is not None:
                raw = np.where(raw == src.nodata, np.nan, raw)
            raw = ctx.band_math.to_reflectance(raw, _sc, _of, np)
            valid = np.isfinite(raw)
            raw = np.nan_to_num(np.clip(raw, 0.0, 1.0), nan=0.0)
            out = (raw * 255).astype(np.uint8)
            if shared_cache is not None:
                shared_cache[cache_key] = (out, valid, _clip_out.get("transform", src.transform))
            return out, valid

        r, r_valid = _read_uint8(b.red)
        g, g_valid = _read_uint8(b.green)
        bl, bl_valid = _read_uint8(b.blue)
        transform = _clip_out.get("transform") or src.transform

    # الحدود والدقّة من شبكة المُخرَج النهائيّة (بعد القصّ) لا من المشهد المصدر.
    bounds = _grid_bounds_4326(src_crs, transform, r.shape)
    res_m = _ground_resolution_m(src_crs, transform, r.shape)
    # ألفا = صلاحيّة المصدر لا سطوع اللون المُكمَّم: البكسل صالح إن صلح في كلّ نطاق
    # حاضر؛ بلا أيّ نطاق لا شيء صالح.
    present = [v for v in (r_valid, g_valid, bl_valid) if v is not None]
    valid_px = np.logical_and.reduce(present) if present else np.zeros(r.shape, dtype=bool)
    alpha = np.where(valid_px, np.uint8(255), np.uint8(0))
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
        if _cog_publishable(cog_info):
            cog_url = ctx.object_store.upload_cog(
                cog_path, f"{req.field_id or 'nofield'}/truecolor_{cog_uid}.tif"
            )
    except Exception as _e:  # noqa: BLE001
        stats["cog"] = {"written": False, "reason": str(_e)}
    meta = {
        "cog_url": cog_url,
        "cog_crs": cog_crs,
        "srid": (src_crs.to_epsg() if src_crs is not None else 4326),
        "resolution_m": res_m,  # كي لا يسقط السجلّ إلى 10 م افتراضيّاً
        "nodata": None,
    }
    return stats, bounds, res_m, meta


def process_pixels(ctx, req, layer_id: str, *, shared_src=None, shared_cache=None):
    """المعالجة الفعليّة للبكسلات (تعمل عند توفّر rasterio). تُرجع
    (stats, bounds_4326, resolution_m, meta) حيث meta يحوي cog_url/cog_crs/
    srid/nodata. تطبّق القصّ على الحقل + قناع الغيوم + إعادة إسقاط الحدود."""
    from contextlib import nullcontext

    import numpy as np
    import rasterio

    if shared_cache is None:
        shared_cache = {}

    # truecolor ليس مؤشّراً طيفيّاً — لا صيغة في _INDICATOR_FORMULAS؛ مسار خاصّ.
    if req.indicator.value == "truecolor":
        return _process_pixels_truecolor(
            ctx, req, layer_id, shared_src=shared_src, shared_cache=shared_cache
        )

    formula = ctx._INDICATOR_FORMULAS[req.indicator.value]
    _src_cm = (
        nullcontext(shared_src)
        if shared_src is not None
        else rasterio.open(ctx._safe_raster_source(req.raster_url))
    )
    with _src_cm as src:
        b = req.bands
        # الحدود (WGS84) والدقّة (أمتار) تُشتقّ لاحقاً من شبكة المُخرَج النهائيّة
        # (transform + شكل المصفوفة بعد القصّ) — انظر (٣) أدناه.
        src_crs = src.crs

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

        read_context = _pixel_read_context(src, clip_geom_src)

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

        normalization_applied: dict[int, bool] = {}

        def band(idx):
            """يقرأ نطاقاً كـfloat32 مع قصّ اختياري + تحويل DN→انعكاس [0,1].

            في مسار الدفعة، تُخزَّن القراءة المحوّلة لكل نطاق داخل shared_cache،
            لذلك لا يُعاد I/O ولا القصّ عند حساب مؤشرات أخرى من المشهد نفسه.
            """
            if not idx:
                return None
            _sc, _of = _refl_params(idx)
            # GDAL defaults (1, 0) do not attest that raw DN are reflectance.
            effective_scale = 1.0 if _sc is None else float(_sc)
            effective_offset = 0.0 if _of is None else float(_of)
            normalization_applied[idx] = bool(
                np.isfinite(effective_scale)
                and effective_scale > 0
                and np.isfinite(effective_offset)
                and (effective_scale != 1 or effective_offset != 0)
            )
            cache_key = (
                "reflectance",
                read_context,
                int(idx),
                _reflectance_cache_params(_sc, _of),
            )
            if cache_key in shared_cache:
                cached, transform = shared_cache[cache_key]
                _out["transform"] = transform
                return cached
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
                a = np.ma.filled(src.read(idx, masked=True).astype("float32"), np.nan)
            # حوّل nodata إلى NaN كي لا يلوّث حساب المؤشّر (قبل المقياس كي لا يُزاح الحارس)
            # Per-band masked reads above preserve nodata and internal masks.
            # A dataset-level nodata value may belong to a different band.
            a = np.where(a == nodata_val, np.nan, a)
            # تحويل DN→انعكاس [0,1] لصحّة المؤشّرات المعتمِدة على المقياس (EVI/SAVI/MSAVI).
            a = ctx.band_math.to_reflectance(a, _sc, _of, np)
            shared_cache[cache_key] = (a, _out["transform"])
            return a

        def band_raw(idx):
            """يقرأ نطاقاً (مثل SCL) دون تحويل nodata→NaN، مع نفس القصّ."""
            if not idx:
                return None
            cache_key = ("raw", read_context, int(idx))
            if cache_key in shared_cache:
                return shared_cache[cache_key]
            if clip_geom_src is not None:
                arr_b, _t = _rio_mask(
                    src,
                    [clip_geom_src],
                    crop=True,
                    filled=True,
                    nodata=0,
                    indexes=[idx],
                )
                out = arr_b[0]
            else:
                out = src.read(idx)
            shared_cache[cache_key] = out
            return out

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
        # msi (SWIR1/NIR) يُحسَب الآن عبر band_math.NEW_INDEX_BANDS (المصدر الأوحد)
        # في الفرع الأعلى؛ أُزيل الفرع السطريّ المكرَّر (سلوك محفوظ: نفس _eps للمقام).
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
            # قناع الصلاحيّة داخل الحقل: `arr` (المؤشّر) NaN خارج مضلّع القصّ وعند
            # nodata، فـ`isfinite` يعطي «داخل الحقل + بيانات صالحة». تمريره يقصر
            # حساب نِسَب الغيوم/الظلّ/الثلج على هذه البكسلات فقط بدل تخفيفها ببكسلات
            # خارج الحقل المملوءة صفراً (تُصنَّف غير غائمة كذباً).
            _in_field_valid = np.isfinite(arr)
            mask_result = strategy.apply(
                np=np,
                band_reader=band_raw,
                band_mapping=b,
                target_shape=arr.shape,
                valid_mask=_in_field_valid,
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
        if not vals.size:
            raise ctx.HTTPException(422, {"code": "raw_raster_no_valid_pixels", "valid_pixels": 0})
        total_px = int(valid.size) if hasattr(valid, "size") else 0
        valid_ratio = (float(valid.sum()) / float(total_px)) if total_px else 0.0
        qa_layer_present = bool(
            cloud_mask_sources
            or cloud_shadow_mask_sources
            or snow_mask_sources
            or aerosol_mask_sources
            or saturation_mask_sources
        )
        # ── (٣) شبكة المُخرَج النهائيّة مصدرٌ وحيد للهندسة المنشورة ──────────
        # المصدر غالباً UTM (Sentinel-2 L2A). نحوّل حدود **الشبكة المقصوصة** (لا
        # حدود المشهد كاملاً) إلى EPSG:4326، والدقّة إلى أمتار أرضيّة (لا درجات).
        out_transform = _out["transform"]
        bounds = _grid_bounds_4326(src_crs, out_transform, arr.shape)
        res_m = _ground_resolution_m(src_crs, out_transform, arr.shape)
        topographic_qa = _topographic_qa_for_indicator(
            ctx,
            req=req,
            raster_crs=src_crs,
            raster_transform=out_transform,
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
        _admit_min_raw_quality(ctx, req, pixel_qa)
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

        # عقد المنتَج المُصادَق يتطلّب — عند عدم تطبيق قناع فعليّ — استراتيجيّةً صريحة
        # تُمثّل «غير متاح» بدل اسم محاولة قد يُوهِم تطبيقاً لم يحدث. المحاولة نفسها
        # (sentinel2_scl/landsat_qa_pixel) وسببها محفوظان في
        # stats["cloud_mask_strategy"]/التحذيرات، فلا فقدان معلومة. حالة
        # not_requested (المستخدم لم يطلب قناعاً) تُمثَّل صراحةً بذاتها.
        if cloud_pct is not None or cloud_strategy_name == "not_requested":
            _cloud_strategy = cloud_strategy_name
        else:
            _cloud_strategy = "unknown_unavailable"
        validated_product = raster_validated_product.build_validated_raster_product(
            req=req,
            pixel_qa=pixel_qa,
            quality_flags=stats["quality_flags"],
            spatial_crs=cog_crs,
            bounds_4326=bounds,
            topographic_qa=topographic_qa,
            cloud_mask_strategy=_cloud_strategy,
            reflectance_normalized=bool(normalization_applied)
            and all(normalization_applied.values()),
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
                arr, cog_path, out_transform, crs=cog_crs, nodata=RASTER_NODATA
            )
            stats["cog"] = cog_info
            if _cog_publishable(cog_info):
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
            "resolution_m": res_m,  # كي لا يسقط السجلّ إلى 10 م افتراضيّاً
            "nodata": RASTER_NODATA,
            "pixel_qa": pixel_qa,
            "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
        }
        return stats, bounds, res_m, meta
