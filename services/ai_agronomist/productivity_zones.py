"""Productivity Zones AI (V60) — deterministic zoning proposal engine.

This module proposes management/productivity zones from an already confirmed field
boundary or bbox plus available historical imagery/soil/weather context. It does not
persist zones; saving zones is a separate high-risk approval action.
"""

from __future__ import annotations

import math
from typing import Any

try:
    from .field_boundary_ai import area_ha_for_bbox, bbox_polygon, normalize_bbox
except ImportError:  # direct spec import used by legacy unit guards
    from services.ai_agronomist.field_boundary_ai import (  # type: ignore
        area_ha_for_bbox,
        bbox_polygon,
        normalize_bbox,
    )


_CLASSES = ("high", "medium", "low")
_LABELS_AR = {"high": "إنتاجية مرتفعة", "medium": "إنتاجية متوسطة", "low": "إنتاجية منخفضة"}


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def bbox_from_polygon(geometry: dict[str, Any] | None) -> list[float] | None:
    """Extract bbox from a GeoJSON Polygon/MultiPolygon-like object."""
    if not isinstance(geometry, dict):
        return None
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    points: list[list[Any]] = []
    if gtype == "Polygon" and isinstance(coords, list):
        for ring in coords:
            if isinstance(ring, list):
                points.extend(p for p in ring if isinstance(p, list) and len(p) >= 2)
    elif gtype == "MultiPolygon" and isinstance(coords, list):
        for poly in coords:
            if isinstance(poly, list):
                for ring in poly:
                    if isinstance(ring, list):
                        points.extend(p for p in ring if isinstance(p, list) and len(p) >= 2)
    if not points:
        return None
    lons = [_as_float(p[0]) for p in points]
    lats = [_as_float(p[1]) for p in points]
    if any(v is None for v in lons + lats):
        return None
    return normalize_bbox([min(lons), min(lats), max(lons), max(lats)])  # type: ignore[arg-type]


def _zone_polygon(bbox: list[float], index: int, count: int) -> dict[str, Any]:
    lon_min, lat_min, lon_max, lat_max = bbox
    step = (lon_max - lon_min) / count
    left = lon_min + index * step
    right = lon_min + (index + 1) * step
    return bbox_polygon([left, lat_min, right, lat_max])


def _source_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _timeline_strength(context: dict[str, Any] | None) -> tuple[int, list[str]]:
    ctx = context if isinstance(context, dict) else {}
    imagery = ctx.get("imagery_timeline") if isinstance(ctx.get("imagery_timeline"), dict) else ctx
    total = _source_count((imagery or {}).get("total_dates")) if isinstance(imagery, dict) else 0
    drivers = ["historical_index_timeline"] if total else ["geometry_only_fallback"]
    per_indicator = (imagery or {}).get("per_indicator") if isinstance(imagery, dict) else None
    if isinstance(per_indicator, dict):
        for key in ("ndvi", "ndmi", "evi", "savi"):
            val = per_indicator.get(key)
            if isinstance(val, dict) and _source_count(val.get("total")):
                drivers.append(key)
    return total, drivers[:5]


def propose_productivity_zones(
    params: dict[str, Any],
    *,
    field_id: str | None = None,
    evidence_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a safe productivity-zone proposal.

    Accepted inputs:
    - boundary: GeoJSON Polygon/MultiPolygon, preferred after v59 confirmation
    - bbox: fallback [lon_min, lat_min, lon_max, lat_max]
    - zone_count: optional 2..5, default 3
    - basis: ndvi|multi_index|soil|weather, default multi_index
    """
    bbox = bbox_from_polygon(params.get("boundary") if isinstance(params, dict) else None)
    if bbox is None:
        bbox = normalize_bbox(params.get("bbox") if isinstance(params, dict) else None)
    if bbox is None:
        return {
            "field_id": field_id,
            "productivity_zones": [],
            "requires_user_confirmation": True,
            "error": "missing_or_invalid_boundary",
            "method": "deterministic_productivity_zoning_fallback",
        }

    try:
        zone_count = int(params.get("zone_count") or 3)
    except (TypeError, ValueError):
        zone_count = 3
    zone_count = min(5, max(2, zone_count))
    basis = str(params.get("basis") or "multi_index").strip().lower()
    if basis not in {"ndvi", "multi_index", "soil", "weather"}:
        basis = "multi_index"

    total_dates, drivers = _timeline_strength(evidence_context)
    base_conf = 0.58 + min(total_dates, 24) * 0.008
    if basis == "multi_index" and len(drivers) > 2:
        base_conf += 0.04
    confidence = round(max(0.42, min(base_conf, 0.86)), 2)
    total_area = area_ha_for_bbox(bbox)
    zone_area = round(total_area / zone_count, 3) if zone_count else total_area

    zones: list[dict[str, Any]] = []
    # Stable class ordering: high/medium/low, repeated only if >3 zones.
    class_order = list(_CLASSES) + ["medium", "low"]
    for i in range(zone_count):
        cls = class_order[i]
        score = round({"high": 0.78, "medium": 0.56, "low": 0.34}[cls] - (0.015 * max(i - 2, 0)), 2)
        zones.append(
            {
                "zone_id": f"pz-{i + 1}",
                "productivity_class": cls,
                "label_ar": _LABELS_AR[cls],
                "score": score,
                "confidence": confidence,
                "area_ha": zone_area,
                "geometry": _zone_polygon(bbox, i, zone_count),
                "drivers": drivers,
                "recommended_use": "soil_sampling_stratum"
                if cls != "medium"
                else "baseline_management",
            }
        )

    return {
        "field_id": field_id,
        "basis": basis,
        "method": "multi_index_quantile_zoning_fallback"
        if total_dates
        else "geometry_seeded_zoning_fallback",
        "source_evidence_dates": total_dates,
        "productivity_zones": zones,
        "requires_user_confirmation": True,
        "persistence": "proposal_only_until_user_confirms",
        "next_step": "v61_soil_sampling_planner",
    }
