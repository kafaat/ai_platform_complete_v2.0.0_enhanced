"""Field geometry save guard — pure production checks before persisting boundaries.

This module is intentionally dependency-light and DB-free.  It complements the
existing GIS guard by enforcing save-specific invariants that protect downstream
NDVI, irrigation, VRA, raster cache, and reports from poor boundary artifacts.
"""

from __future__ import annotations

import math
from typing import Any

MAX_FIELD_VERTEX_COUNT = 2_000
MIN_FIELD_AREA_HA = 0.001  # 10 m²: rejects empty/near-empty accidental polygons.
MAX_FIELD_AREA_HA = 100_000.0


def _ring(geometry: dict[str, Any]) -> list:
    if not isinstance(geometry, dict):
        raise ValueError("geometry_not_object")
    if geometry.get("type") != "Polygon":
        raise ValueError("only_polygon_supported_for_save")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords or not isinstance(coords[0], list):
        raise ValueError("missing_outer_ring")
    return coords[0]


def boundary_vertex_count(geometry: dict[str, Any]) -> int:
    """Return the outer-ring vertex count for a GeoJSON Polygon."""
    return len(_ring(geometry))


def validate_boundary_for_save(
    geometry: dict[str, Any],
    *,
    area_ha: float,
    max_vertices: int = MAX_FIELD_VERTEX_COUNT,
    min_area_ha: float = MIN_FIELD_AREA_HA,
    max_area_ha: float = MAX_FIELD_AREA_HA,
) -> dict[str, Any]:
    """Validate save-time geometry invariants and return transparent metadata.

    Raises ValueError with machine-readable issue codes when the boundary should
    not be saved.  The existing PostGIS/GeometryGuard checks geometry validity;
    this function adds production UX/quality guardrails: finite area, reasonable
    area bounds, and no pathological vertex explosion from segmentation masks.
    """
    issues: list[str] = []
    try:
        vertices = boundary_vertex_count(geometry)
    except ValueError as exc:
        raise exc

    if vertices < 4:
        issues.append("boundary_ring_too_short")
    if vertices > max_vertices:
        issues.append("boundary_too_many_vertices")

    try:
        area_value = float(area_ha)
    except (TypeError, ValueError):
        area_value = float("nan")
    if not math.isfinite(area_value):
        issues.append("boundary_area_not_finite")
    elif area_value < min_area_ha:
        issues.append("boundary_area_too_small")
    elif area_value > max_area_ha:
        issues.append("boundary_area_too_large")

    if issues:
        raise ValueError(",".join(issues))

    return {
        "vertices": vertices,
        "area_ha": round(area_value, 4),
        "max_vertices": max_vertices,
        "min_area_ha": min_area_ha,
        "max_area_ha": max_area_ha,
    }


def sanitize_boundary_metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only safe/portable boundary provenance fields from the client/model.

    This metadata is audit/provenance only.  It must not grant trust or override
    server-side tenant/security decisions.
    """
    if not isinstance(value, dict):
        return {}
    allowed = {
        "source",
        "mode",
        "confidence",
        "imagery_source",
        "imagery_date",
        "cloud_cover",
        "model",
        "model_version",
        "checkpoint",
        "model_cfg",
        "post_processing",
        "vertices_before",
        "vertices_after",
        "inference_ms",
        "mask_area_px",
    }
    out: dict[str, Any] = {}
    for key in allowed:
        if key in value:
            out[key] = value[key]
    return out
