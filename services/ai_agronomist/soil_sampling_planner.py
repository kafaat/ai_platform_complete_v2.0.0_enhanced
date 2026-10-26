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


# Equirectangular metres per degree — the same constants ``area_ha_for_bbox`` uses.
_M_PER_DEG_LON_AT_EQUATOR = 111_320.0
_M_PER_DEG_LAT = 110_574.0

Ring = list[tuple[float, float]]


def polygon_rings(geometry: Any) -> list[list[Ring]]:
    """GeoJSON Polygon/MultiPolygon -> polygons as ``[outer, *holes]`` lon/lat rings.

    Returns ``[]`` when the geometry is missing, of another type, holds a non-finite
    coordinate, or has no outer ring with at least three distinct vertices. A
    closing vertex equal to the first one is dropped.
    """
    if not isinstance(geometry, dict):
        return []
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list):
        return []
    if gtype == "Polygon":
        raw_polys = [coords]
    elif gtype == "MultiPolygon":
        raw_polys = [p for p in coords if isinstance(p, list)]
    else:
        return []
    polys: list[list[Ring]] = []
    for raw_poly in raw_polys:
        rings: list[Ring] = []
        for raw_ring in raw_poly:
            if not isinstance(raw_ring, list):
                continue
            ring: Ring = []
            for pt in raw_ring:
                if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                    continue
                lon, lat = _as_float(pt[0]), _as_float(pt[1])
                if lon is None or lat is None:
                    return []
                ring.append((lon, lat))
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring.pop()
            if len(set(ring)) >= 3:
                rings.append(ring)
            elif not rings:
                break  # outer ring unusable -> drop this polygon (holes are meaningless)
        if rings:
            polys.append(rings)
    return polys


def _ring_area_deg2(ring: Ring) -> float:
    total = 0.0
    for i, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(i + 1) % len(ring)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def polygon_area_ha(geometry: Any) -> float | None:
    """Polygon area in hectares, or ``None`` when the geometry is not a usable polygon.

    Approximation: shoelace formula on lon/lat degrees scaled to metres with an
    equirectangular projection at the polygon's mean vertex latitude (the same
    metres-per-degree constants as ``area_ha_for_bbox``). Holes are subtracted.
    Good for field-sized polygons; authoritative area belongs to PostGIS geography.
    """
    polys = polygon_rings(geometry)
    if not polys:
        return None
    lats = [lat for poly in polys for ring in poly for _, lat in ring]
    mean_lat = math.radians(sum(lats) / len(lats))
    m_per_deg_lon = _M_PER_DEG_LON_AT_EQUATOR * max(math.cos(mean_lat), 0.01)
    area_deg2 = 0.0
    for outer, *holes in polys:
        area_deg2 += max(_ring_area_deg2(outer) - sum(_ring_area_deg2(h) for h in holes), 0.0)
    return round(area_deg2 * m_per_deg_lon * _M_PER_DEG_LAT / 10_000.0, 3)


def _point_in_polygons(lon: float, lat: float, polys: list[list[Ring]]) -> bool:
    """Even-odd ray cast over every ring of each polygon (holes excluded)."""
    for poly in polys:
        inside = False
        for ring in poly:
            for i, (x1, y1) in enumerate(ring):
                x2, y2 = ring[(i + 1) % len(ring)]
                if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                    inside = not inside
        if inside:
            return True
    return False


def _interior_segments(lat: float, polys: list[list[Ring]]) -> list[tuple[float, float]]:
    """Lon intervals of the horizontal line ``lat`` that lie inside the polygons."""
    segments: list[tuple[float, float]] = []
    for poly in polys:
        crossings: list[float] = []
        for ring in poly:
            for i, (x1, y1) in enumerate(ring):
                x2, y2 = ring[(i + 1) % len(ring)]
                if (y1 > lat) != (y2 > lat):
                    crossings.append(x1 + (lat - y1) * (x2 - x1) / (y2 - y1))
        crossings.sort()
        segments.extend(
            (crossings[k], crossings[k + 1])
            for k in range(0, len(crossings) - 1, 2)
            if crossings[k + 1] > crossings[k]
        )
    return segments


def _clip_ring_to_bbox(ring: Ring, bbox: list[float]) -> Ring:
    """Sutherland-Hodgman clip of a ring against an axis-aligned box (convex window)."""
    lon_min, lat_min, lon_max, lat_max = bbox
    edges = (
        (lambda p: p[0] >= lon_min, 0, lon_min),
        (lambda p: p[0] <= lon_max, 0, lon_max),
        (lambda p: p[1] >= lat_min, 1, lat_min),
        (lambda p: p[1] <= lat_max, 1, lat_max),
    )
    out = list(ring)
    for keep, axis, bound in edges:
        src, out = out, []
        for i, cur in enumerate(src):
            prev = src[i - 1]
            if keep(cur) != keep(prev):
                t = (bound - prev[axis]) / (cur[axis] - prev[axis])
                hit = (prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1]))
                out.append(hit)
            if keep(cur):
                out.append(cur)
        if not out:
            break
    return out


def _clip_polygons_to_bbox(polys: list[list[Ring]], bbox: list[float]) -> dict[str, Any] | None:
    """Clip polygons to a box and return a GeoJSON (Multi)Polygon, or ``None`` if empty."""
    clipped: list[list[list[list[float]]]] = []
    for outer, *holes in polys:
        c_outer = _clip_ring_to_bbox(outer, bbox)
        if len(set(c_outer)) < 3 or _ring_area_deg2(c_outer) <= 0:
            continue
        rings = [c_outer] + [
            c for c in (_clip_ring_to_bbox(h, bbox) for h in holes) if len(set(c)) >= 3
        ]
        clipped.append([[[x, y] for x, y in r] + [[r[0][0], r[0][1]]] for r in rings])
    if not clipped:
        return None
    if len(clipped) == 1:
        return {"type": "Polygon", "coordinates": clipped[0]}
    return {"type": "MultiPolygon", "coordinates": clipped}


def _sample_point_in_zone(
    polys: list[list[Ring]], bbox: list[float], sample_index: int, total: int
) -> list[float] | None:
    """Deterministic sample point guaranteed inside the zone polygon.

    Keeps the v61 bbox placement when it already falls inside. Otherwise the point is
    moved onto the widest interior span of a horizontal scan line (first at the
    candidate latitude, then the bbox mid-latitude, then evenly spaced lines), at the
    same fractional position the bbox placement used. ``None`` if no interior point
    exists (degenerate geometry) — never a point outside the zone.
    """
    candidate = _sample_point_for_bbox(bbox, sample_index, total)
    if not polys or _point_in_polygons(candidate[0], candidate[1], polys):
        return candidate
    lon_min, lat_min, lon_max, lat_max = bbox
    frac = (sample_index + 1) / (total + 1)
    scan_lats = [candidate[1], (lat_min + lat_max) / 2] + [
        lat_min + (lat_max - lat_min) * k / 10 for k in range(1, 10)
    ]
    for lat in scan_lats:
        segments = _interior_segments(lat, polys)
        if not segments:
            continue
        a, b = max(segments, key=lambda s: s[1] - s[0])
        point = [round(a + (b - a) * frac, 7), round(lat, 7)]
        if _point_in_polygons(point[0], point[1], polys):
            return point
    return None


def _zone_area_ha(zone: dict[str, Any], bbox: list[float]) -> float:
    explicit = _as_float(zone.get("area_ha"))
    if explicit:
        return explicit
    poly_area = polygon_area_ha(zone.get("geometry"))
    return poly_area if poly_area is not None else area_ha_for_bbox(bbox)


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

    # V61.1 — strategy dispatch (default ``zone`` = unchanged v61 behaviour).
    from .soil_sampling_strategies import (
        VALID_STRATEGIES,
        build_grid_samples,
        grid_points,
        recommended_samples_for_area,
    )

    strategy = str(params.get("sampling_strategy") or "zone").strip().lower()
    if strategy not in VALID_STRATEGIES:
        strategy = "zone"

    lab_panel_early = str(params.get("lab_panel") or "standard").strip().lower()
    analytes_early = list(
        _FULL_PANEL_ANALYTES
        if lab_panel_early in {"full", "complete", "advanced"}
        else _DEFAULT_ANALYTES
    )

    if strategy == "grid":
        gbox = bbox_from_polygon(
            params.get("boundary") if isinstance(params.get("boundary"), dict) else None
        ) or normalize_bbox(params.get("bbox"))
        if gbox is None:
            return {
                "field_id": field_id,
                "soil_sampling_plan": None,
                "sample_points": [],
                "requires_user_confirmation": True,
                "error": "missing_productivity_zones_or_boundary",
                "method": "regular_grid_sampling",
            }
        boundary_polys = polygon_rings(params.get("boundary"))
        boundary_area = polygon_area_ha(params.get("boundary"))
        area = boundary_area if boundary_area is not None else area_ha_for_bbox(gbox)
        req = _as_float(params.get("samples_per_zone"))
        count = int(req) if req else recommended_samples_for_area(area)
        count = max(1, min(30, count))
        samples, stratum = build_grid_samples(gbox, count, lab_panel_early, analytes_early)
        if boundary_polys:
            # Grid cells cover the boundary's bbox; keep only points inside the field.
            samples = [
                s for s in samples if _point_in_polygons(*s["point"]["coordinates"], boundary_polys)
            ]
            stratum["sample_count"] = len(samples)
            if not samples:
                return {
                    "field_id": field_id,
                    "soil_sampling_plan": None,
                    "sample_points": [],
                    "requires_user_confirmation": True,
                    "error": "no_valid_sampling_strata",
                    "method": "regular_grid_sampling",
                }
        return {
            "field_id": field_id,
            "method": "regular_grid_sampling",
            "sampling_strategy": "grid",
            "recommended_total_samples": recommended_samples_for_area(area),
            "soil_sampling_plan": {
                "plan_id": "ssp-proposal-1",
                "lab_panel": lab_panel_early,
                "analytes": analytes_early,
                "strata": [stratum],
                "total_samples": len(samples),
                "estimated_field_hours": round(max(1.0, len(samples) * 0.18), 2),
            },
            "sample_points": samples,
            "requires_user_confirmation": True,
            "persistence": "proposal_only_until_user_confirms",
            "next_step": "v62_vra_prescription_engine",
        }

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
        boundary_polys = polygon_rings(params.get("boundary"))
        zones = []
        for i in range(3):
            third = [lon_min + i * step, lat_min, lon_min + (i + 1) * step, lat_max]
            # A boundary polygon is clipped to each third so strata never leave the field.
            geometry = (
                _clip_polygons_to_bbox(boundary_polys, third)
                if boundary_polys
                else bbox_polygon(third)
            )
            if geometry is None:
                continue
            zones.append(
                {
                    "zone_id": f"fallback-{i + 1}",
                    "productivity_class": ("high", "medium", "low")[i],
                    "geometry": geometry,
                }
            )

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
        area = _zone_area_ha(zone, bbox)
        zone_polys = polygon_rings(zone.get("geometry"))
        points = [_sample_point_in_zone(zone_polys, bbox, j, count) for j in range(count)]
        points = [p for p in points if p is not None]
        if not points:
            continue
        strata.append(
            {
                "zone_id": zone_id,
                "productivity_class": zone_class,
                "priority": _ZONE_PRIORITY.get(zone_class, "normal"),
                "area_ha": round(area, 3),
                "sample_count": len(points),
            }
        )
        for j, coordinates in enumerate(points):
            sample_points.append(
                {
                    "sample_id": f"ss-{idx + 1}-{j + 1}",
                    "zone_id": zone_id,
                    "productivity_class": zone_class,
                    "priority": _ZONE_PRIORITY.get(zone_class, "normal"),
                    "point": {
                        "type": "Point",
                        "coordinates": coordinates,
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

    total_area = round(sum(s["area_ha"] for s in strata), 3)
    # V61.1 — hybrid: top up zone strata with grid infill toward the area target.
    if strategy == "hybrid":
        method = "hybrid_zone_grid_sampling"
        zone_bboxes = [b for b in (_zone_bbox(z) for z in zones[:8]) if b is not None]
        # Infill points must fall inside some zone (polygon, or bbox for bbox-only zones).
        zone_polys = [
            polygon_rings(z.get("geometry")) or polygon_rings(bbox_polygon(b))
            for z in zones[:8]
            if (b := _zone_bbox(z)) is not None
        ]
        if zone_bboxes:
            union = [
                min(b[0] for b in zone_bboxes),
                min(b[1] for b in zone_bboxes),
                max(b[2] for b in zone_bboxes),
                max(b[3] for b in zone_bboxes),
            ]
            target = recommended_samples_for_area(total_area)
            need = target - len(sample_points)
            if need > 0:
                infill = [
                    p
                    for p in grid_points(union, need)
                    if any(_point_in_polygons(p[0], p[1], zp) for zp in zone_polys)
                ]
                for i, p in enumerate(infill):
                    sample_points.append(
                        {
                            "sample_id": f"ss-grid-{i + 1}",
                            "zone_id": "grid-infill",
                            "productivity_class": "unknown",
                            "priority": "normal",
                            "point": {"type": "Point", "coordinates": p},
                            "depth_cm": [0, 30],
                            "composite": True,
                            "lab_panel": lab_panel,
                            "analytes": analytes,
                            "instructions_ar": "عينة شبكيّة مكمّلة — مركّبة من نقاط صغيرة حولها، تجنّب الحواف.",
                        }
                    )
                if infill:
                    strata.append(
                        {
                            "zone_id": "grid-infill",
                            "productivity_class": "unknown",
                            "priority": "normal",
                            "area_ha": total_area,
                            "sample_count": len(infill),
                            "design": "grid_infill",
                        }
                    )

    return {
        "field_id": field_id,
        "method": method,
        "sampling_strategy": strategy,
        "recommended_total_samples": recommended_samples_for_area(total_area),
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
