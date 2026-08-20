"""Plot-wise raster evidence extraction for field trials.

This module converts authoritative trial polygons into exact raster zonal
measurements and produces the outcome payload consumed by
``shared.precision_agriculture.bind_plot_outcomes``. It performs no agronomic
interpretation and cannot promote a treatment; it only binds measured evidence to
stable plot IDs.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform_geom


def _finite_stats(values: np.ndarray) -> dict[str, float]:
    flat = np.asarray(values, dtype="float64").reshape(-1)
    flat = flat[np.isfinite(flat)]
    if not flat.size:
        raise ValueError("plot has no finite raster pixels")
    return {
        "count": float(flat.size),
        "mean": float(np.mean(flat)),
        "min": float(np.min(flat)),
        "max": float(np.max(flat)),
        "std": float(np.std(flat)),
    }


def extract_plot_zonal_outcomes(
    assignments: list[dict[str, Any]],
    raster_layers: list[dict[str, Any]],
    *,
    all_touched: bool = False,
) -> dict[str, dict[str, Any]]:
    """Extract deterministic per-plot statistics from one or more rasters.

    Each raster layer requires ``name``, ``path`` and ``evidence_ref``; ``band``
    defaults to 1, with optional ``scale``/``offset``. Geometry is accepted in
    canonical EPSG:4326 and reprojected to the raster CRS before masking.
    """
    if not assignments:
        raise ValueError("trial assignments are required")
    if not raster_layers:
        raise ValueError("at least one raster layer is required")

    plot_ids = [str(row.get("plot_id") or "") for row in assignments]
    if any(not pid for pid in plot_ids) or len(plot_ids) != len(set(plot_ids)):
        raise ValueError("trial assignments require unique plot_id values")

    outcomes: dict[str, dict[str, Any]] = {
        pid: {"outcome_refs": [], "measurements": {}} for pid in plot_ids
    }
    for layer in raster_layers:
        name = str(layer.get("name") or "").strip()
        path = Path(str(layer.get("path") or ""))
        evidence_ref = str(layer.get("evidence_ref") or "").strip()
        band = int(layer.get("band", 1))
        scale = float(layer.get("scale", 1.0))
        offset = float(layer.get("offset", 0.0))
        if not name or not evidence_ref or not path.is_file() or band < 1:
            raise ValueError("raster layer requires valid name/path/evidence_ref/band")
        if not math.isfinite(scale) or not math.isfinite(offset):
            raise ValueError("raster scale/offset must be finite")

        with rasterio.open(path) as src:
            if src.crs is None:
                raise ValueError(f"raster layer {name} has no CRS")
            if band > src.count:
                raise ValueError(f"raster layer {name} band {band} exceeds raster band count")
            for row in assignments:
                plot_id = str(row["plot_id"])
                geometry = row.get("geometry")
                if not isinstance(geometry, dict) or geometry.get("type") not in {
                    "Polygon",
                    "MultiPolygon",
                }:
                    raise ValueError(f"plot {plot_id} has invalid geometry")
                geom_src = transform_geom("EPSG:4326", src.crs, geometry, precision=12)
                data, _ = rio_mask(
                    src,
                    [geom_src],
                    crop=True,
                    indexes=band,
                    filled=False,
                    all_touched=all_touched,
                )
                values = np.asarray(data.compressed() if hasattr(data, "compressed") else data)
                values = values.astype("float64") * scale + offset
                stats = _finite_stats(values)
                measurements = outcomes[plot_id]["measurements"]
                for stat_name, value in stats.items():
                    measurements[f"{name}_{stat_name}"] = value
                outcomes[plot_id]["outcome_refs"].append(evidence_ref)

    for payload in outcomes.values():
        payload["outcome_refs"] = list(dict.fromkeys(payload["outcome_refs"]))
    return outcomes
