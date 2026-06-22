"""Canonical pivot field geometry.

For pivot fields the source of truth is center/radius/angles, not an edited
polygon. The polygon is generated deterministically from those parameters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from api.gis_geometry_guard import guard_field_geometry


@dataclass(frozen=True)
class PivotSpec:
    center_lon: float
    center_lat: float
    radius_m: float
    start_angle_deg: float = 0.0
    end_angle_deg: float = 360.0
    vertices: int = 96


def _meters_to_degrees(
    lon: float, lat: float, east_m: float, north_m: float
) -> tuple[float, float]:
    lat_deg = north_m / 111_320.0
    lon_scale = max(0.15, math.cos(math.radians(lat)))
    lon_deg = east_m / (111_320.0 * lon_scale)
    return lon + lon_deg, lat + lat_deg


def generate_pivot_polygon(spec: PivotSpec) -> dict[str, Any]:
    if spec.radius_m <= 0:
        raise ValueError("pivot radius_m must be positive")
    if spec.vertices < 12:
        raise ValueError("pivot polygon requires at least 12 vertices")
    start = spec.start_angle_deg % 360
    end = spec.end_angle_deg % 360
    sweep = (end - start) % 360
    full_circle = math.isclose(sweep, 0.0, abs_tol=1e-9)
    if full_circle:
        sweep = 360.0
    steps = max(12, int(spec.vertices * (sweep / 360.0)))
    pts: list[list[float]] = []
    if not full_circle:
        pts.append([round(spec.center_lon, 7), round(spec.center_lat, 7)])
    for i in range(steps + 1):
        angle = math.radians(start + sweep * i / steps)
        east = spec.radius_m * math.sin(angle)
        north = spec.radius_m * math.cos(angle)
        lon, lat = _meters_to_degrees(spec.center_lon, spec.center_lat, east, north)
        pts.append([round(lon, 7), round(lat, 7)])
    if pts[0] != pts[-1]:
        pts.append(list(pts[0]))
    polygon = {"type": "Polygon", "coordinates": [pts]}
    # Validate canonical output before it can enter DB/raster workflows.
    return guard_field_geometry(polygon, repair=False).geometry


def pivot_spec_from_payload(payload: dict[str, Any]) -> PivotSpec | None:
    pivot = payload.get("pivot") if isinstance(payload, dict) else None
    if not isinstance(pivot, dict):
        return None
    center = pivot.get("center") or {}
    if isinstance(center, dict):
        lon = center.get("lon") if center.get("lon") is not None else center.get("lng")
        lat = center.get("lat")
    elif isinstance(center, (list, tuple)) and len(center) >= 2:
        lon, lat = center[0], center[1]
    else:
        lon, lat = pivot.get("center_lon"), pivot.get("center_lat")
    if lon is None or lat is None:
        return None
    radius = pivot.get("radius_m") or pivot.get("radius")
    if radius is None:
        return None
    return PivotSpec(
        center_lon=float(lon),
        center_lat=float(lat),
        radius_m=float(radius),
        start_angle_deg=float(pivot.get("start_angle_deg", pivot.get("start_angle", 0.0)) or 0.0),
        end_angle_deg=float(pivot.get("end_angle_deg", pivot.get("end_angle", 360.0)) or 360.0),
        vertices=int(pivot.get("vertices", 96) or 96),
    )


def maybe_canonicalize_pivot_geometry(
    payload: dict[str, Any], irrigation_type: str | None
) -> dict[str, Any] | None:
    if (irrigation_type or "").lower() != "pivot":
        return None
    spec = pivot_spec_from_payload(payload)
    if spec is None:
        return None
    return generate_pivot_polygon(spec)
