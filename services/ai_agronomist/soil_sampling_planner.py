"""Soil Sampling Planner (V61) — deterministic proposal engine.

The planner turns confirmed/proposed productivity zones into a field sampling plan.
It is proposal-only: it does not persist plans, create tasks, or assign scouts. Saving
or converting the plan to work orders is a separate high-risk approval action.
"""

from __future__ import annotations

import math
from typing import Any

try:
    from .field_boundary_ai import area_ha_for_bbox, bbox_polygon, normalize_bbox
    from .productivity_zones import bbox_from_polygon
except ImportError:  # direct spec import used by legacy unit guards
    from services.ai_agronomist.field_boundary_ai import (  # type: ignore
        area_ha_for_bbox,
        bbox_polygon,
        normalize_bbox,
    )
    from services.ai_agronomist.productivity_zones import bbox_from_polygon  # type: ignore

_DEFAULT_ANALYTES = ("pH", "EC", "OM", "N", "P", "K", "texture")
_FULL_PANEL_ANALYTES = _DEFAULT_ANALYTES + ("Ca", "Mg", "S", "Zn", "Fe", "Mn", "B", "CEC")
_ZONE_PRIORITY = {"low": "high", "medium": "normal", "high": "normal"}


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _zone_bbox(zone: dict[str, Any]) -> list[float] | None:
    geom = zone.get("geometry") if isinstance(zone, dict) else None
    bbox = bbox_from_polygon(geom) if isinstance(geom, dict) else None
    if bbox is not None:
        return bbox
    raw = zone.get("bbox") if isinstance(zone, dict) else None
    return normalize_bbox(raw)


def _sample_point_for_bbox(bbox: list[float], sample_index: int, total: int) -> list[float]:
    """Return a deterministic interior lon/lat point for a bbox."""
    lon_min, lat_min, lon_max, lat_max = bbox
    # Spread samples across thirds while staying away from edges.
    frac = (sample_index + 1) / (total + 1)
    lon = lon_min + (lon_max - lon_min) * frac
    # Alternate slightly north/south around center for multi-point zones.
    offset = (0.18 if sample_index % 2 == 0 else -0.18) * (lat_max - lat_min)
    lat = (lat_min + lat_max) / 2 + offset
    return [round(lon, 7), round(lat, 7)]


def _class_for_zone(zone: dict[str, Any], idx: int) -> str:
    raw = str(zone.get("productivity_class") or zone.get("class") or "").strip().lower()
    if raw in {"high", "medium", "low"}:
        return raw
    return ("high", "medium", "low")[idx % 3]


def _samples_for_zone(zone: dict[str, Any], zone_class: str, default: int) -> int:
    requested = _as_float(zone.get("samples") or zone.get("sample_count"))
    if requested is not None:
        return max(1, min(8, int(requested)))
    # Low productivity zones get one extra observation by default.
    return max(1, min(8, default + (1 if zone_class == "low" else 0)))


def _zones_from_params(params: dict[str, Any]) -> list[dict[str, Any]]:
    zones = params.get("zones") if isinstance(params, dict) else None
    if isinstance(zones, list):
        return [z for z in zones if isinstance(z, dict)]
    return []


def plan_soil_sampling(
    params: dict[str, Any],
    *,
    field_id: str | None = None,
    evidence_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a confirmable soil-sampling proposal.

    Preferred input is the V60 ``productivity_zones`` array. If it is missing, the
    function falls back to a boundary/bbox and creates three provisional strata so
    the chat agent can still propose a plan, while clearly marking the method.
    """
    params = params if isinstance(params, dict) else {}
    zones = _zones_from_params(params)
    method = "productivity_zone_stratified_sampling"

    if not zones:
        bbox = bbox_from_polygon(
            params.get("boundary") if isinstance(params.get("boundary"), dict) else None
        )
        if bbox is None:
            bbox = normalize_bbox(params.get("bbox"))
        if bbox is None:
            return {
                "field_id": field_id,
                "soil_sampling_plan": None,
                "sample_points": [],
                "requires_user_confirmation": True,
                "error": "missing_productivity_zones_or_boundary",
                "method": "soil_sampling_planner_fallback",
            }
        method = "geometry_seeded_sampling_fallback"
        lon_min, lat_min, lon_max, lat_max = bbox
        step = (lon_max - lon_min) / 3
        zones = [
            {
                "zone_id": f"fallback-{i + 1}",
                "productivity_class": ("high", "medium", "low")[i],
                "geometry": bbox_polygon(
                    [lon_min + i * step, lat_min, lon_min + (i + 1) * step, lat_max]
                ),
            }
            for i in range(3)
        ]

    try:
        default_samples = int(params.get("samples_per_zone") or 2)
    except (TypeError, ValueError):
        default_samples = 2
    default_samples = max(1, min(6, default_samples))

    lab_panel = str(params.get("lab_panel") or "standard").strip().lower()
    analytes = list(
        _FULL_PANEL_ANALYTES if lab_panel in {"full", "complete", "advanced"} else _DEFAULT_ANALYTES
    )

    sample_points: list[dict[str, Any]] = []
    strata: list[dict[str, Any]] = []
    for idx, zone in enumerate(zones[:8]):
        bbox = _zone_bbox(zone)
        if bbox is None:
            continue
        zone_class = _class_for_zone(zone, idx)
        count = _samples_for_zone(zone, zone_class, default_samples)
        zone_id = str(zone.get("zone_id") or f"zone-{idx + 1}")
        area = _as_float(zone.get("area_ha")) or area_ha_for_bbox(bbox)
        strata.append(
            {
                "zone_id": zone_id,
                "productivity_class": zone_class,
                "priority": _ZONE_PRIORITY.get(zone_class, "normal"),
                "area_ha": round(area, 3),
                "sample_count": count,
            }
        )
        for j in range(count):
            sample_points.append(
                {
                    "sample_id": f"ss-{idx + 1}-{j + 1}",
                    "zone_id": zone_id,
                    "productivity_class": zone_class,
                    "priority": _ZONE_PRIORITY.get(zone_class, "normal"),
                    "point": {
                        "type": "Point",
                        "coordinates": _sample_point_for_bbox(bbox, j, count),
                    },
                    "depth_cm": [0, 30],
                    "composite": True,
                    "lab_panel": lab_panel,
                    "analytes": analytes,
                    "instructions_ar": "خذ عينة مركبة من 8–12 نقطة صغيرة حول هذه النقطة داخل نفس المنطقة الإنتاجية، وتجنب الحواف ومسارات المركبات.",
                }
            )

    if not sample_points:
        return {
            "field_id": field_id,
            "soil_sampling_plan": None,
            "sample_points": [],
            "requires_user_confirmation": True,
            "error": "no_valid_sampling_strata",
            "method": method,
        }

    evidence_dates = 0
    if isinstance(evidence_context, dict):
        imagery = evidence_context.get("imagery_timeline")
        if isinstance(imagery, dict):
            try:
                evidence_dates = int(imagery.get("total_dates") or 0)
            except (TypeError, ValueError):
                evidence_dates = 0

    return {
        "field_id": field_id,
        "method": method,
        "soil_sampling_plan": {
            "plan_id": "ssp-proposal-1",
            "lab_panel": lab_panel,
            "analytes": analytes,
            "strata": strata,
            "total_samples": len(sample_points),
            "estimated_field_hours": round(max(1.0, len(sample_points) * 0.18), 2),
            "source_evidence_dates": evidence_dates,
        },
        "sample_points": sample_points,
        "requires_user_confirmation": True,
        "persistence": "proposal_only_until_user_confirms",
        "next_step": "v62_vra_prescription_engine",
    }
