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
            arr = src.read(spec.index, out_shape=(src.height // stride, src.width // stride)).astype(
                "float32"
            )
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
            "provenance": {
                "operation": "raw_data_processing",
                "fabricated_indicator": False,
                "indicator_computed": False,
            },
        }
