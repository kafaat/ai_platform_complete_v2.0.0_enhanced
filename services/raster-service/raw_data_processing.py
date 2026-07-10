"""Raw raster data inspection and normalization helpers.

This module intentionally lives beside raster pixel processing instead of inside
``main.py``.  It provides a conservative raw-data path: read a source raster via
``safe_raster_source``, compute truthful per-band metadata/statistics, and
optionally normalize raw digital numbers to reflectance for downstream QA.

It does **not** fabricate agronomic indicators.  The output is provenance/QA for
raw scenes before indicator computation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RawBandSpec:
    """A normalized request for one raw band."""

    index: int
    name: str


def _as_float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _finite_stats(np, arr) -> dict[str, Any]:
    valid = np.isfinite(arr)
    vals = arr[valid]
    if vals.size == 0:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "p02": None,
            "p50": None,
            "p98": None,
            "valid_pixels": 0,
            "nodata_pixels": int((~valid).sum()),
        }
    return {
        "min": float(np.min(vals)),
        "max": float(np.max(vals)),
        "mean": float(np.mean(vals)),
        "std": float(np.std(vals)),
        "p02": float(np.percentile(vals, 2)),
        "p50": float(np.percentile(vals, 50)),
        "p98": float(np.percentile(vals, 98)),
        "valid_pixels": int(valid.sum()),
        "nodata_pixels": int((~valid).sum()),
    }


def _normalize_band_names(count: int, requested: list[int] | None) -> list[RawBandSpec]:
    if requested:
        indices = requested
    else:
        indices = list(range(1, count + 1))
    out: list[RawBandSpec] = []
    seen: set[int] = set()
    for idx in indices:
        if idx in seen:
            continue
        if idx < 1 or idx > count:
            raise ValueError(f"band index {idx} خارج عدد نطاقات الراستر ({count})")
        seen.add(idx)
        out.append(RawBandSpec(index=idx, name=f"band_{idx}"))
    return out


def compute_quality_score(
    *,
    valid_pixel_ratio: float | None,
    cloud_pct: float | None,
    cloud_mask_applied: bool,
    qa_layer_present: bool = False,
    shadow_pct: float | None = None,
    snow_pct: float | None = None,
    aerosol_pct: float | None = None,
    saturation_pct: float | None = None,
    terrain_shadow_risk_pct: float | None = None,
    cast_shadow_risk_pct: float | None = None,
    slope_risk_pct: float | None = None,
    topographic_qa_applied: bool = False,
    cloud_shadow_mask_applied: bool = False,
    snow_mask_applied: bool = False,
    aerosol_mask_applied: bool = False,
    saturation_mask_applied: bool = False,
) -> dict[str, Any]:
    """Return a conservative pixel-level QA score for raw/indicator preprocessing.

    The score is deterministic and intentionally conservative.  Coverage is the
    base, then known contamination fractions subtract trust.  Missing masks are
    surfaced as warnings, not hidden.  This is a QA/provenance gate, not an
    agronomic indicator and not a replacement for source-native QA bands.
    """

    def _fraction(value: float | None) -> float:
        if value is None:
            return 0.0
        return max(0.0, min(1.0, float(value) / 100.0))

    coverage = 0.0 if valid_pixel_ratio is None else max(0.0, min(1.0, float(valid_pixel_ratio)))
    cloud_penalty = _fraction(cloud_pct) * 0.35
    shadow_penalty = _fraction(shadow_pct) * 0.20
    snow_penalty = _fraction(snow_pct) * 0.20
    aerosol_penalty = _fraction(aerosol_pct) * 0.15
    saturation_penalty = _fraction(saturation_pct) * 0.20
    terrain_shadow_penalty = _fraction(terrain_shadow_risk_pct) * 0.12
    slope_risk_penalty = _fraction(slope_risk_pct) * 0.08
    mask_penalty = 0.0 if cloud_mask_applied else 0.10
    qa_bonus = 0.03 if qa_layer_present else 0.0
    score = max(
        0.0,
        min(
            1.0,
            coverage
            - cloud_penalty
            - shadow_penalty
            - snow_penalty
            - aerosol_penalty
            - saturation_penalty
            - terrain_shadow_penalty
            - slope_risk_penalty
            - mask_penalty
            + qa_bonus,
        ),
    )
    warnings: list[str] = []
    if not cloud_mask_applied:
        warnings.append("cloud_mask_not_applied_or_unavailable")
    if shadow_pct is not None and not cloud_shadow_mask_applied:
        warnings.append("cloud_shadow_mask_detected_but_not_applied")
    if snow_pct is not None and not snow_mask_applied:
        warnings.append("snow_mask_detected_but_not_applied")
    if aerosol_pct is not None and not aerosol_mask_applied:
        warnings.append("aerosol_mask_detected_but_not_applied")
    if saturation_pct is not None and not saturation_mask_applied:
        warnings.append("saturation_mask_detected_but_not_applied")
    if terrain_shadow_risk_pct is not None and not topographic_qa_applied:
        warnings.append("terrain_shadow_risk_detected_but_not_applied")
    if slope_risk_pct is not None and not topographic_qa_applied:
        warnings.append("slope_risk_detected_but_not_applied")
    if terrain_shadow_risk_pct is not None and terrain_shadow_risk_pct >= 20.0:
        warnings.append("high_terrain_shadow_risk")
    if slope_risk_pct is not None and slope_risk_pct >= 30.0:
        warnings.append("high_slope_risk")
    if coverage < 0.50:
        warnings.append("low_valid_pixel_ratio")
    if cloud_pct is not None and cloud_pct >= 50.0:
        warnings.append("high_cloud_fraction")
    if shadow_pct is not None and shadow_pct >= 20.0:
        warnings.append("high_shadow_fraction")
    if saturation_pct is not None and saturation_pct >= 5.0:
        warnings.append("high_saturation_fraction")
    return {
        "schema": "sahool.raster_pixel_qa/1",
        "raw_qa_required": True,
        "quality_score": round(float(score), 4),
        "valid_pixel_ratio": round(float(coverage), 4),
        "cloud_pct": cloud_pct,
        "shadow_pct": shadow_pct,
        "snow_pct": snow_pct,
        "aerosol_pct": aerosol_pct,
        "saturation_pct": saturation_pct,
        "terrain_shadow_risk_pct": terrain_shadow_risk_pct,
        "cast_shadow_risk_pct": cast_shadow_risk_pct,
        "slope_risk_pct": slope_risk_pct,
        "topographic_qa_applied": bool(topographic_qa_applied),
        "cloud_mask_applied": bool(cloud_mask_applied),
        "cloud_shadow_mask_applied": bool(cloud_shadow_mask_applied),
        "snow_mask_applied": bool(snow_mask_applied),
        "aerosol_mask_applied": bool(aerosol_mask_applied),
        "saturation_mask_applied": bool(saturation_mask_applied),
        "qa_layer_present": bool(qa_layer_present),
        "warnings": warnings,
        "indicator_computed": False,
        "fabricated_indicator": False,
    }


def build_quality_flags(
    *,
    nodata_mask_applied: bool,
    qa_layer_present: bool,
    cloud_mask_applied: bool,
    cloud_shadow_mask_applied: bool = False,
    snow_mask_applied: bool = False,
    aerosol_mask_applied: bool = False,
    saturation_mask_applied: bool = False,
    topographic_qa_applied: bool = False,
    terrain_shadow_risk_applied: bool = False,
    cast_shadow_risk_applied: bool = False,
    slope_risk_applied: bool = False,
    cloud_mask_sources: list[str] | None = None,
    cloud_shadow_mask_sources: list[str] | None = None,
    snow_mask_sources: list[str] | None = None,
    aerosol_mask_sources: list[str] | None = None,
    saturation_mask_sources: list[str] | None = None,
    topographic_qa_sources: list[str] | None = None,
    source_native_qa_policy: str = "source_native_first_when_available",
) -> dict[str, Any]:
    """Canonical raw raster QA flags shared by raw QA and indicator paths."""

    return {
        "schema": "sahool.raster_quality_flags/1",
        "nodata_mask_applied": bool(nodata_mask_applied),
        "qa_layer_present": bool(qa_layer_present),
        "cloud_mask_applied": bool(cloud_mask_applied),
        "cloud_shadow_mask_applied": bool(cloud_shadow_mask_applied),
        "snow_mask_applied": bool(snow_mask_applied),
        "aerosol_mask_applied": bool(aerosol_mask_applied),
        "saturation_mask_applied": bool(saturation_mask_applied),
        "topographic_qa_applied": bool(topographic_qa_applied),
        "terrain_shadow_risk_applied": bool(terrain_shadow_risk_applied),
        "cast_shadow_risk_applied": bool(cast_shadow_risk_applied),
        "slope_risk_applied": bool(slope_risk_applied),
        "cloud_mask_sources": list(cloud_mask_sources or []),
        "cloud_shadow_mask_sources": list(cloud_shadow_mask_sources or []),
        "snow_mask_sources": list(snow_mask_sources or []),
        "aerosol_mask_sources": list(aerosol_mask_sources or []),
        "saturation_mask_sources": list(saturation_mask_sources or []),
        "topographic_qa_sources": list(topographic_qa_sources or []),
        "source_native_qa_policy": source_native_qa_policy,
    }


def process_raw_raster(ctx, req) -> dict[str, Any]:
    """Inspect a raw raster and return metadata + per-band QA statistics.

    ``ctx`` is the same explicit context pattern used by the existing raster
    processing runtime.  Required attributes: ``_safe_raster_source``.
    Optional attributes: ``band_math`` for reflectance conversion.
    """

    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds

    if not getattr(req, "raster_url", None):
        raise ValueError("raster_url مطلوب لمعالجة البيانات الخام")

    with rasterio.open(ctx._safe_raster_source(req.raster_url)) as src:
        src_crs = src.crs
        bounds_4326 = (
            list(transform_bounds(src_crs, "EPSG:4326", *src.bounds))
            if src_crs is not None
            else list(src.bounds)
        )
        band_specs = _normalize_band_names(src.count, getattr(req, "bands", None))
        max_pixels = int(getattr(req, "max_pixels", 2_000_000) or 2_000_000)
        total_pixels = int(src.width * src.height)
        # Keep local/CI inspection bounded.  For huge rasters, sample by stride instead of
        # reading the full scene into memory; this is QA, not final indicator computation.
        stride = max(1, int((total_pixels / max_pixels) ** 0.5)) if total_pixels > max_pixels else 1
        window_note = None
        if stride > 1:
            window_note = f"sampled_every_{stride}_pixels_for_bounded_raw_qa"

        raw_bands: list[dict[str, Any]] = []
        normalized_bands: list[dict[str, Any]] = []
        for spec in band_specs:
            arr = src.read(
                spec.index, out_shape=(src.height // stride, src.width // stride)
            ).astype("float32")
            nodata = src.nodata
            if nodata is not None:
                arr = np.where(arr == nodata, np.nan, arr)
            scale = None
            offset = None
            if src.scales:
                scale = _as_float_or_none(src.scales[spec.index - 1])
            if src.offsets:
                offset = _as_float_or_none(src.offsets[spec.index - 1])
            band_record = {
                "index": spec.index,
                "name": spec.name,
                "dtype": str(src.dtypes[spec.index - 1]),
                "nodata": _as_float_or_none(nodata),
                "scale": scale,
                "offset": offset,
                "raw_stats": _finite_stats(np, arr),
            }
            raw_bands.append(band_record)
            if getattr(req, "normalize_reflectance", False):
                converted = getattr(ctx, "band_math", None)
                if converted is not None:
                    refl = converted.to_reflectance(arr, scale, offset, np)
                else:
                    sc = 1.0 if scale in (None, 0.0) else scale
                    off = 0.0 if offset is None else offset
                    refl = arr * sc + off
                normalized_bands.append(
                    {
                        "index": spec.index,
                        "name": spec.name,
                        "reflectance_stats": _finite_stats(np, refl),
                    }
                )

        tags = {}
        if getattr(req, "include_tags", False):
            try:
                tags = dict(src.tags())
            except Exception:  # noqa: BLE001 — tags are optional QA metadata
                tags = {}

        return {
            "schema": "sahool.raw_raster_processing/1",
            "status": "processed",
            "tenant_id": getattr(req, "tenant_id", None),
            "field_id": getattr(req, "field_id", None),
            "source": {
                "raster_url": req.raster_url,
                "width": int(src.width),
                "height": int(src.height),
                "count": int(src.count),
                "crs": str(src_crs or ""),
                "srid": src_crs.to_epsg() if src_crs is not None else None,
                "bounds_4326": bounds_4326,
                "resolution": [float(abs(src.res[0])), float(abs(src.res[1]))],
                "driver": src.driver,
                "transform": list(src.transform)[:6],
                "sample_note": window_note,
            },
            "raw_bands": raw_bands,
            "normalized_bands": normalized_bands,
            "tags": tags,
            "source_kind": "satellite_raster",
            "product_level": "raw_or_provider_processed_raster",
            "quality_flags": build_quality_flags(
                nodata_mask_applied=True,
                qa_layer_present=any(
                    str(k).lower() in {"scl", "clm", "clp", "qa", "quality"} for k in tags
                ),
                cloud_mask_applied=False,
                cloud_shadow_mask_applied=False,
                snow_mask_applied=False,
                aerosol_mask_applied=False,
                saturation_mask_applied=False,
                topographic_qa_applied=False,
                terrain_shadow_risk_applied=False,
                slope_risk_applied=False,
            ),
            "quality_score": compute_quality_score(
                valid_pixel_ratio=(
                    sum(b["raw_stats"]["valid_pixels"] for b in raw_bands)
                    / max(
                        1,
                        sum(
                            b["raw_stats"]["valid_pixels"] + b["raw_stats"]["nodata_pixels"]
                            for b in raw_bands
                        ),
                    )
                ),
                cloud_pct=None,
                shadow_pct=None,
                snow_pct=None,
                aerosol_pct=None,
                saturation_pct=None,
                cloud_mask_applied=False,
                cloud_shadow_mask_applied=False,
                snow_mask_applied=False,
                aerosol_mask_applied=False,
                saturation_mask_applied=False,
                topographic_qa_applied=False,
                qa_layer_present=any(
                    str(k).lower() in {"scl", "clm", "clp", "qa", "quality"} for k in tags
                ),
            ),
            "topographic_qa": {
                "schema": "sahool.raster_topographic_qa/1",
                "available": False,
                "topographic_qa_applied": False,
                "terrain_shadow_risk_pct": None,
                "slope_risk_pct": None,
                "fabricated_topographic_mask": False,
                "warnings": ["raw_process_does_not_coregister_dem"],
            },
            "spatial_alignment": {
                "source_crs": str(src_crs or ""),
                "target_crs": "EPSG:4326",
                "resampling_method": "none_raw_inspection",
                "reprojected_for_processing": False,
            },
            "temporal_alignment": {
                "acquisition_time": getattr(req, "capture_datetime", None),
                "aggregation": "none_raw_scene",
            },
            "provenance": {
                "operation": "raw_data_processing",
                "schema": "sahool.raw_processing/1",
                "fabricated_indicator": False,
                "indicator_computed": False,
                "derived_product_computed": False,
            },
        }
