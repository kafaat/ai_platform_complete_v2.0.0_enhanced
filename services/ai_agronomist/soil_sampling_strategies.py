"""Soil-sampling strategies (V61.1) — grid / zone / hybrid + sample-count guidance.

Extends the v61 zone-stratified planner with two more designs, selected by
``sampling_strategy`` (default ``zone`` = unchanged v61 behaviour):

- ``grid``: a regular grid over the field extent — bias-free spatial coverage when
  productivity zones are unknown or the agronomist wants uniform density.
- ``hybrid``: zone strata (v61) plus grid infill up to the area-based target — combines
  stratification with coverage.

Sample-count guidance is a documented agronomic rule of thumb (≈1 composite per 2 ha, floor 3,
cap 20); it is advisory and always overridable. Proposal-only — nothing is persisted.
Pure Python + stdlib.
"""

from __future__ import annotations

import math
from typing import Any

from shared.soil_sampling_guidance import COMPOSITE_PURPOSES, PURPOSE_GUIDANCE

VALID_STRATEGIES = ("zone", "grid", "hybrid")


def collection_protocol(params: dict[str, Any]) -> tuple[str, list[list[int]]]:
    default = (
        "salinity"
        if str(params.get("lab_panel", "")).strip().lower() == "salinity"
        else "fertility"
    )
    purpose = str(params.get("sampling_purpose", default)).strip().lower()
    if purpose not in PURPOSE_GUIDANCE:
        raise ValueError("unknown_sampling_purpose")
    intervals = params.get("depth_intervals_cm", [])
    if not isinstance(intervals, list):
        raise ValueError("invalid_depth_intervals")
    depths = []
    for interval in intervals:
        if not isinstance(interval, dict):
            raise ValueError("invalid_depth_intervals")
        top, bottom = interval.get("from_cm"), interval.get("to_cm")
        if type(top) is not int or type(bottom) is not int or not 0 <= top < bottom:
            raise ValueError("invalid_depth_intervals")
        depths.append([top, bottom])
    depths.sort()
    if any(left[1] > right[0] for left, right in zip(depths, depths[1:], strict=False)):
        raise ValueError("overlapping_depth_intervals")
    return purpose, depths


def prepare_collection(points, purpose, depths, strategy):
    """Return one labelled bag per specified layer, or a location awaiting depth selection."""
    bags = []
    for point in points:
        grid = strategy == "grid" or point["zone_id"] == "grid-infill"
        unit = "خلية الشبكة حول الموضع" if grid else "المنطقة المحددة"
        for depth in depths or [[]]:
            bag = dict(point)
            if len(depths) > 1:
                bag["sample_id"] = f"{point['sample_id']}-d{depth[0]}-{depth[1]}"
            bag.update(
                depth_cm=depth,
                sampling_purpose=purpose,
                location_id=point["sample_id"],
                composite=purpose in COMPOSITE_PURPOSES,
                instructions_ar=f"وحدة الجمع: {unit}. {PURPOSE_GUIDANCE[purpose]}",
            )
            bags.append(bag)
    return bags


def recommended_samples_for_area(
    area_ha: float, *, per_ha: float = 0.5, floor: int = 3, cap: int = 20
) -> int:
    """Advisory composite-sample count for a field of ``area_ha`` hectares.

    Default ≈ one composite per 2 ha (per_ha=0.5), clamped to [floor, cap]. Heuristic,
    not a standard — the caller may override via ``samples_per_zone``/explicit counts.
    """
    if not isinstance(area_ha, (int, float)) or area_ha <= 0:
        return floor
    return max(floor, min(cap, math.ceil(area_ha * per_ha)))


def grid_dims(n: int) -> tuple[int, int]:
    """Roughly-square (cols, rows) covering at least ``n`` cells."""
    n = max(1, n)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows


def grid_points(bbox: list[float], n: int) -> list[list[float]]:
    """``n`` deterministic interior grid points across ``bbox`` (edge-avoiding)."""
    lon_min, lat_min, lon_max, lat_max = bbox
    cols, rows = grid_dims(n)
    pts: list[list[float]] = []
    for r in range(rows):
        for c in range(cols):
            if len(pts) >= n:
                break
            fx = (c + 0.5) / cols  # cell centres → never on the edge
            fy = (r + 0.5) / rows
            pts.append(
                [
                    round(lon_min + fx * (lon_max - lon_min), 7),
                    round(lat_min + fy * (lat_max - lat_min), 7),
                ]
            )
    return pts


def build_grid_samples(
    bbox: list[float], count: int, lab_panel: str, analytes: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (sample_points, single grid stratum) for a regular-grid design."""
    pts = grid_points(bbox, count)
    samples = [
        {
            "sample_id": f"ss-grid-{i + 1}",
            "zone_id": "grid",
            "productivity_class": "unknown",
            "priority": "normal",
            "point": {"type": "Point", "coordinates": p},
            "depth_cm": [],
            "composite": True,
            "lab_panel": lab_panel,
            "analytes": analytes,
            "instructions_ar": PURPOSE_GUIDANCE["fertility"],
        }
        for i, p in enumerate(pts)
    ]
    stratum = {
        "zone_id": "grid",
        "productivity_class": "unknown",
        "priority": "normal",
        "sample_count": len(samples),
        "design": "regular_grid",
    }
    return samples, stratum
