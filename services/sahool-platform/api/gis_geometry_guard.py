"""Canonical GIS geometry guard for field drawing, raster overlays and mobile sync.

This module is intentionally dependency-light: it uses the existing SAHOOL
geospatial_integrity validator and only imports Shapely when it is installed.
It normalizes all accepted user geometries to GeoJSON Polygon in EPSG:4326.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from api.geospatial_integrity import validate_field_geometry

CANONICAL_CRS = "EPSG:4326"
GEOMETRY_PROCESSING_VERSION = "gis-guard-v1"


@dataclass(frozen=True)
class GuardedGeometry:
    geometry: dict[str, Any]
    area_ha: float
    bbox: dict[str, float]
    centroid: tuple[float, float]  # lat, lon
    processing_version: str = GEOMETRY_PROCESSING_VERSION


def _as_polygon_geojson(geojson: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(geojson, dict):
        raise ValueError("geometry must be a GeoJSON object")
    gtype = geojson.get("type")
    if gtype == "Feature":
        return _as_polygon_geojson(geojson.get("geometry") or {})
    if gtype == "FeatureCollection":
        features = geojson.get("features") or []
        if not features:
            raise ValueError("empty FeatureCollection")
        return _as_polygon_geojson(features[0])
    if gtype == "Polygon":
        return {"type": "Polygon", "coordinates": geojson.get("coordinates") or []}
    raise ValueError("only GeoJSON Polygon is supported for field boundaries")


def _normalize_ring(ring: list[Any], *, precision: int = 7) -> list[list[float]]:
    normalized: list[list[float]] = []
    last: tuple[float, float] | None = None
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        lon = round(float(point[0]), precision)
        lat = round(float(point[1]), precision)
        current = (lon, lat)
        if last == current:
            continue
        normalized.append([lon, lat])
        last = current
    if normalized and normalized[0] != normalized[-1]:
        normalized.append(list(normalized[0]))
    return normalized


def normalize_geojson_polygon(geojson: dict[str, Any]) -> dict[str, Any]:
    """Return canonical GeoJSON Polygon: no CRS member, closed rings, deduped vertices."""
    polygon = _as_polygon_geojson(geojson)
    coords = polygon.get("coordinates") or []
    if not coords:
        raise ValueError("polygon has no coordinates")
    outer = _normalize_ring(coords[0])
    holes = [_normalize_ring(r) for r in coords[1:] if r]
    return {"type": "Polygon", "coordinates": [outer, *[h for h in holes if len(h) >= 4]]}


def _try_shapely_make_valid(geometry: dict[str, Any]) -> dict[str, Any]:
    """Best-effort repair. If Shapely is unavailable, return normalized input."""
    try:
        from shapely.geometry import mapping, shape  # type: ignore
        from shapely.validation import make_valid  # type: ignore
    except Exception:
        return geometry
    try:
        geom = shape(geometry)
        if not geom.is_valid:
            geom = make_valid(geom)
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)
        if geom.geom_type != "Polygon":
            return geometry
        return normalize_geojson_polygon(mapping(geom))
    except Exception:
        return geometry


def _centroid_from_bbox(bbox: dict[str, float]) -> tuple[float, float]:
    return ((bbox["min_lat"] + bbox["max_lat"]) / 2.0, (bbox["min_lng"] + bbox["max_lng"]) / 2.0)


def guard_field_geometry(
    geojson: dict[str, Any], *, declared_crs: str | None = None, repair: bool = True
) -> GuardedGeometry:
    """Normalize, repair if possible, and validate a field geometry.

    Raises ValueError with machine-readable-ish text when the geometry must be rejected.
    """
    normalized = normalize_geojson_polygon(geojson)
    if repair:
        normalized = _try_shapely_make_valid(normalized)
    validation = validate_field_geometry(normalized, declared_crs=declared_crs)
    if not validation.valid:
        codes = ",".join(i.code for i in validation.issues)
        raise ValueError(codes or "invalid_geometry")
    if validation.computed_area_ha is None or validation.computed_bbox is None:
        raise ValueError("geometry_area_or_bbox_missing")
    lat, lon = _centroid_from_bbox(validation.computed_bbox)
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError("invalid_geometry_centroid")
    return GuardedGeometry(
        geometry=normalized,
        area_ha=round(float(validation.computed_area_ha), 4),
        bbox=validation.computed_bbox,
        centroid=(lat, lon),
    )


def geometry_metadata(
    *,
    scene_id: str | None = None,
    captured_at: str | None = None,
    field_revision: int | None = None,
) -> dict[str, Any]:
    return {
        "crs": CANONICAL_CRS,
        "processing_version": GEOMETRY_PROCESSING_VERSION,
        "scene_id": scene_id,
        "captured_at": captured_at,
        "field_revision": field_revision,
    }
