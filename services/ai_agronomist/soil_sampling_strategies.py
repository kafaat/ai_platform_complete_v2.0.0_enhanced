"""Soil-sampling strategies (V61.1) — grid / zone / hybrid + sample-count guidance.

Extends the v61 zone-stratified planner with two more designs, selected by
``sampling_strategy`` (default ``zone`` = unchanged v61 behaviour):

- ``grid``: a regular grid over the field extent — bias-free spatial coverage when
  productivity zones are unknown or the agronomist wants uniform density.
- ``hybrid``: zone strata (v61) plus grid infill up to the area-based target — combines
  stratification with coverage.

Sample-count guidance is a documented agronomic rule of thumb (≈1 core per 2 ha, floor 3,
cap 20); it is advisory and always overridable. Proposal-only — nothing is persisted.
Pure Python + stdlib.
"""

from __future__ import annotations

import math
from typing import Any

VALID_STRATEGIES = ("zone", "grid", "hybrid")


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
            "depth_cm": [0, 30],
            "composite": True,
            "lab_panel": lab_panel,
            "analytes": analytes,
            "instructions_ar": "خذ عينة مركبة من 8–12 نقطة صغيرة حول هذه النقطة، وتجنب الحواف ومسارات المركبات.",
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
