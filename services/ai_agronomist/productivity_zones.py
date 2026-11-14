"""Productivity Zones AI (V60) — deterministic zoning proposal engine.

This module proposes management/productivity zones from an already confirmed field
boundary or bbox plus available historical imagery/soil/weather context. It does not
persist zones; saving zones is a separate high-risk approval action.
"""

from __future__ import annotations

import math
from typing import Any

try:
    from .field_boundary_ai import bbox_polygon, normalize_bbox
except ImportError:  # direct spec import used by legacy unit guards
    from services.ai_agronomist.field_boundary_ai import (  # type: ignore
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
    # عدد المناطق: صريح من المستخدم (يُحترَم) أو تلقائيّ (FPI/NCE) عند العنقدة الحقيقيّة.
    explicit_zone_count = params.get("zone_count") if isinstance(params, dict) else None
    try:
        zone_count = int(explicit_zone_count) if explicit_zone_count is not None else 3
    except (TypeError, ValueError):
        zone_count = 3
        explicit_zone_count = None
    zone_count = min(5, max(2, zone_count))
    basis = str(params.get("basis") or "multi_index").strip().lower()
    if basis not in {"ndvi", "multi_index", "soil", "weather"}:
        basis = "multi_index"

    total_dates, drivers = _timeline_strength(evidence_context)
    base_conf = 0.58 + min(total_dates, 24) * 0.008
    if basis == "multi_index" and len(drivers) > 2:
        base_conf += 0.04
    confidence = round(max(0.42, min(base_conf, 0.86)), 2)

    # V60.1 — real NDVI-driven zoning when a grid is available (opt-in); else strips.
    # V60.3 — multi-index zoning (NDVI + NDMI/RECI/MSAVI/slope) when co-registered aux
    # grids are supplied and basis is not explicitly "ndvi" (Management Zone Analyst:
    # multi-variable clustering, not NDVI-only). Aux is fail-safe: misaligned ⇒ NDVI-only.
    from .productivity_zones_clustering import (
        extract_aux_grids,
        extract_ndvi_grid,
        indicator_sources,
        ndvi_grid_exceeds_cap,
        zones_from_ndvi_grid,
    )

    grid = extract_ndvi_grid(params, evidence_context)
    from .zoning_grid_geometry import GridGeometryError, ZoningGridGeometry

    georef = None
    spatial_error = None
    if grid:
        try:
            georef = ZoningGridGeometry(
                grid, params, evidence_context, bbox, params.get("boundary")
            )
            grid = georef.masked_grid(grid)
        except ImportError:
            spatial_error = "grid_geometry_runtime_unavailable"
        except GridGeometryError as exc:
            spatial_error = str(exc)
    if bbox is None and (not grid or spatial_error == "missing_or_invalid_boundary"):
        return {
            "field_id": field_id,
            "productivity_zones": [],
            "requires_user_confirmation": True,
            "error": "missing_or_invalid_boundary",
            "method": "insufficient_data",
            "status": "insufficient_data",
        }
    aux_grids = (
        extract_aux_grids(params, evidence_context, ndvi_grid=grid) if basis != "ndvi" else None
    )
    # عدد صريح ⇒ يُحترَم؛ غيابه ⇒ k=None فيختار FPI/NCE الأمثل. + تنعيم تجاور مكانيّ.
    k_arg = zone_count if explicit_zone_count is not None else None
    clustered = (
        zones_from_ndvi_grid(
            grid, [0, 0, georef.cols, georef.rows], k_arg, smooth=True, aux_grids=aux_grids
        )
        if georef is not None and not spatial_error
        else None
    )
    if clustered:
        cl_conf = round(
            max(0.42, min(confidence + 0.05 * clustered["cluster_separability"], 0.92)), 2
        )
        feature_names = clustered.get("feature_names") or ["ndvi"]
        sources = indicator_sources(params, evidence_context, feature_names)
        is_multi = len(feature_names) > 1
        cl_method = "multi_index_kmeans_clustering" if is_multi else "ndvi_kmeans_clustering"
        # وسوم مُوجِّهة صادقة: تعكس الميزات الفعليّة المستعملة (ndmi/reci/msavi/slope) لا مجرّد تسمية.
        driver_tag = "multi_index_grid_kmeans" if is_multi else "ndvi_grid_kmeans"
        cl_drivers = [driver_tag, *feature_names[1:], *drivers][:5]
        cl_zones = [
            {
                "zone_id": z["zone_id"],
                "productivity_class": z["productivity_class"],
                "label_ar": _LABELS_AR[z["productivity_class"]],
                "zoning_method": cl_method,
                "score": z["score"],
                "feature_names": feature_names,
                "indicator_sources": sources,
                "ndvi_centroid": z["ndvi_centroid"],
                "confidence": cl_conf,
                "area_ha": spatial[1],
                "geometry": spatial[0],
                "drivers": cl_drivers,
                "recommended_use": "soil_sampling_stratum"
                if z["productivity_class"] != "medium"
                else "baseline_management",
            }
            for z in clustered["zones"]
            if (spatial := georef.zone(z["geometry"])) is not None
        ]
        return {
            "field_id": field_id,
            "basis": basis,
            "method": cl_method,
            "feature_names": feature_names,
            "indicator_sources": sources,
            "status": "proposal",
            "grid_bbox": georef.bbox,
            "grid_bbox_source": georef.source,
            "grid_crs": georef.crs,
            "grid_input_source": georef.owner,
            "grid_georeferencing_verified": not georef.declared,
            "grid_footprint_field_coverage": georef.field_coverage,
            "confidence_method": "heuristic_input_support_not_probability",
            "confidence_is_probability": False,
            "limitations": [
                "single_grid_not_multiseason_yield",
                *(["caller_grid_georeferencing_required"] if georef.declared else []),
            ],
            "source_evidence_dates": total_dates,
            "cluster_separability": clustered["cluster_separability"],
            "ndvi_centroids": clustered["ndvi_centroids"],
            "k_effective": clustered["k_effective"],
            "zone_count_source": "user_specified"
            if explicit_zone_count is not None
            else "auto_fpi_nce",
            "zone_count_recommendation": clustered.get("zone_count_recommendation"),
            "spatially_smoothed": clustered.get("spatially_smoothed", False),
            "productivity_zones": cl_zones,
            "requires_user_confirmation": True,
            "persistence": "proposal_only_until_user_confirms",
            "next_step": "v61_soil_sampling_planner",
        }

    return {
        "field_id": field_id,
        "basis": basis,
        "method": "insufficient_data",
        "status": "insufficient_data",
        "reason_codes": [spatial_error or "usable_indicator_grid_required"]
        + (
            ["indicator_grid_exceeds_size_cap"]
            if ndvi_grid_exceeds_cap(params, evidence_context)
            else []
        ),
        "source_evidence_dates": total_dates,
        "productivity_zones": [],
        "confidence": None,
        "requires_user_confirmation": True,
        "persistence": "proposal_only_until_user_confirms",
        "next_step": "acquire_valid_indicator_grid",
    }
