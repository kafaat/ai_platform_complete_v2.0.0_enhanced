"""Canonical GIS geometry guard for field drawing, raster overlays and mobile sync.

This module is intentionally dependency-light: it uses the existing SAHOOL
geospatial_integrity validator and only imports Shapely when it is installed.
It normalizes all accepted user geometries to GeoJSON Polygon/MultiPolygon in EPSG:4326.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from api.geospatial_integrity import (
    compute_bbox,
    embedded_crs_names,
    polygon_net_area_ha,
    validate_embedded_crs,
    validate_field_geometry,
)

CANONICAL_CRS = "EPSG:4326"
GEOMETRY_PROCESSING_VERSION = "gis-guard-v2-multipolygon"


def field_geometry_error_detail(error: ValueError) -> dict[str, Any]:
    """Name a measured self-intersection without changing validation or repair.

    Keep the existing machine codes, including MultiPolygon part prefixes.
    Unknown failures retain the generic message; never infer a cause from a
    substring of arbitrary exception text.
    """
    issues = str(error).split(",")
    codes: set[str] = set()
    for issue in issues:
        prefix, separator, code = issue.partition(":")
        if not separator:
            codes.add(issue)
        elif prefix.startswith("part_") and prefix[5:].isdigit():
            codes.add(code)
    if "self_intersection" in codes:
        message_ar = "حدود الحقل تتقاطع مع نفسها — أعد رسم الحدود دون تقاطعات ثم حاول الحفظ مجدداً."
    elif "invalid_crs" in codes:
        message_ar = (
            "نظام الإحداثيّات المُعلَن في الهندسة غير مدعوم — أعد إسقاطها إلى "
            "EPSG:4326 (خطّ الطول/خطّ العرض) ثمّ أعد المحاولة."
        )
    elif "antimeridian_crossing" in codes:
        message_ar = "حدود الحقل تعبر خطّ التاريخ (±180°) — هذا غير مدعوم؛ تحقّق من الإحداثيّات."
    else:
        message_ar = "هندسة الحقل غير صالحة — صحّح الحدود وأعد المحاولة."
    return {
        "message_ar": message_ar,
        "code": "invalid_field_geometry",
        "issues": issues,
    }


@dataclass(frozen=True)
class GuardedGeometry:
    geometry: dict[str, Any]
    area_ha: float
    bbox: dict[str, float]
    centroid: tuple[float, float]  # lat, lon
    processing_version: str = GEOMETRY_PROCESSING_VERSION


def _as_polygonal_geojson(geojson: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(geojson, dict):
        raise ValueError("geometry must be a GeoJSON object")
    gtype = geojson.get("type")
    if gtype == "Feature":
        return _as_polygonal_geojson(geojson.get("geometry") or {})
    if gtype == "FeatureCollection":
        features = geojson.get("features") or []
        polygonal = [
            _as_polygonal_geojson(f)
            for f in features
            if isinstance(f, dict)
            and ((f.get("geometry") or {}).get("type") in {"Polygon", "MultiPolygon"})
        ]
        if not polygonal:
            raise ValueError("empty FeatureCollection")
        if len(polygonal) == 1:
            return polygonal[0]
        # Preserve all polygon parts instead of silently choosing the largest one.
        return {
            "type": "MultiPolygon",
            "coordinates": [
                poly["coordinates"]
                for geom in polygonal
                for poly in (
                    [geom]
                    if geom.get("type") == "Polygon"
                    else [
                        {"type": "Polygon", "coordinates": coords}
                        for coords in geom.get("coordinates", [])
                    ]
                )
            ],
        }
    if gtype == "Polygon":
        return {"type": "Polygon", "coordinates": geojson.get("coordinates") or []}
    if gtype == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": geojson.get("coordinates") or []}
    raise ValueError("only GeoJSON Polygon/MultiPolygon is supported for field boundaries")


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


def _normalize_polygon_coords(coords: list[Any]) -> list[list[list[float]]]:
    if not coords:
        raise ValueError("polygon has no coordinates")
    outer = _normalize_ring(coords[0])
    holes = [_normalize_ring(r) for r in coords[1:] if r]
    if len(outer) < 4:
        raise ValueError("polygon outer ring has too few vertices")
    return [outer, *[h for h in holes if len(h) >= 4]]


def normalize_geojson_polygonal(geojson: dict[str, Any]) -> dict[str, Any]:
    """Return canonical GeoJSON Polygon/MultiPolygon: no CRS, closed rings, deduped vertices.

    MultiPolygon is preserved as MultiPolygon; we never collapse it to the largest
    polygon because that loses legitimate disconnected field blocks.
    """
    geom = _as_polygonal_geojson(geojson)
    coords = geom.get("coordinates") or []
    if geom.get("type") == "Polygon":
        return {"type": "Polygon", "coordinates": _normalize_polygon_coords(coords)}
    if geom.get("type") == "MultiPolygon":
        parts = [_normalize_polygon_coords(poly) for poly in coords if poly]
        if not parts:
            raise ValueError("multipolygon has no polygon parts")
        return {"type": "MultiPolygon", "coordinates": parts}
    raise ValueError("only GeoJSON Polygon/MultiPolygon is supported for field boundaries")


def normalize_geojson_polygon(geojson: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias; may now return Polygon or MultiPolygon."""
    return normalize_geojson_polygonal(geojson)


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
        if geom.geom_type not in {"Polygon", "MultiPolygon"}:
            return geometry
        return normalize_geojson_polygonal(mapping(geom))
    except Exception:
        return geometry


def _polygon_parts(geometry: dict[str, Any]) -> list[list[list[tuple[float, float]]]]:
    """Extract every polygon part (outer ring + holes) from a canonical Polygon/MultiPolygon."""
    gtype = geometry.get("type")
    if gtype == "Polygon":
        polygons = [geometry.get("coordinates") or []]
    elif gtype == "MultiPolygon":
        polygons = geometry.get("coordinates") or []
    else:
        raise ValueError("only polygonal geometry is supported")
    parts: list[list[list[tuple[float, float]]]] = []
    for poly in polygons:
        if not poly:
            continue
        rings: list[list[tuple[float, float]]] = []
        for raw_ring in poly:
            ring = [
                (float(p[0]), float(p[1]))
                for p in raw_ring
                if isinstance(p, (list, tuple)) and len(p) >= 2
            ]
            if ring:
                rings.append(ring)
        if rings:
            parts.append(rings)
    return parts


def _combined_area_bbox(geometry: dict[str, Any]) -> tuple[float, dict[str, float]]:
    parts = _polygon_parts(geometry)
    if not parts:
        raise ValueError("polygonal_geometry_has_no_rings")
    # Net area: each part's exterior minus its holes. The holes are preserved in the
    # stored geometry, so fields.area_ha must not count ponds/buildings they exclude.
    area = sum(polygon_net_area_ha(rings) for rings in parts)
    bboxes = [compute_bbox(rings[0]) for rings in parts]
    bbox = {
        "min_lng": min(b["min_lng"] for b in bboxes),
        "max_lng": max(b["max_lng"] for b in bboxes),
        "min_lat": min(b["min_lat"] for b in bboxes),
        "max_lat": max(b["max_lat"] for b in bboxes),
    }
    return area, bbox


def _validate_polygonal_geometry(geometry: dict[str, Any], *, declared_crs: str | None) -> None:
    # Reuse the production Polygon validator per part. This preserves the existing
    # CRS/Yemen/area/self-intersection checks while allowing MultiPolygon fields.
    if geometry.get("type") == "Polygon":
        validation = validate_field_geometry(geometry, declared_crs=declared_crs)
        if not validation.valid:
            raise ValueError(",".join(i.code for i in validation.issues) or "invalid_geometry")
        return
    if geometry.get("type") != "MultiPolygon":
        raise ValueError("only_polygonal_geometry_supported")
    part_errors: list[str] = []
    for idx, poly_coords in enumerate(geometry.get("coordinates") or []):
        validation = validate_field_geometry(
            {"type": "Polygon", "coordinates": poly_coords}, declared_crs=declared_crs
        )
        if not validation.valid:
            part_errors.extend(f"part_{idx}:{issue.code}" for issue in validation.issues)
    if part_errors:
        raise ValueError(",".join(part_errors))


def _centroid_from_bbox(bbox: dict[str, float]) -> tuple[float, float]:
    return ((bbox["min_lat"] + bbox["max_lat"]) / 2.0, (bbox["min_lng"] + bbox["max_lng"]) / 2.0)


def guard_field_geometry(
    geojson: dict[str, Any], *, declared_crs: str | None = None, repair: bool = True
) -> GuardedGeometry:
    """Normalize, repair if possible, and validate a field geometry.

    Raises ValueError with machine-readable-ish text when the geometry must be rejected.
    A ``crs`` member embedded in the GeoJSON (2008 spec) is honoured: anything other
    than WGS84 lon/lat is rejected as ``invalid_crs`` instead of being dropped by
    normalization, even when ``declared_crs`` says EPSG:4326.
    """
    if any(validate_embedded_crs(name) for name in embedded_crs_names(geojson)):
        raise ValueError("invalid_crs")
    normalized = normalize_geojson_polygonal(geojson)
    if repair:
        normalized = _try_shapely_make_valid(normalized)
    _validate_polygonal_geometry(normalized, declared_crs=declared_crs)
    area_ha, bbox = _combined_area_bbox(normalized)
    lat, lon = _centroid_from_bbox(bbox)
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError("invalid_geometry_centroid")
    return GuardedGeometry(
        geometry=normalized,
        area_ha=round(float(area_ha), 4),
        bbox=bbox,
        centroid=(lat, lon),
    )


# Split/merge area conservation. Children of a split must tile their source and a
# merged field must equal the union of its sources. Tolerance is relative to the
# source area: canonical coordinates are rounded to 1e-7° (~1 cm), so honest
# client-side (@turf) or server-side (/gis/union, /gis/split) results differ from
# the exact overlay by about perimeter x 1 cm (~0.04% for a 1 ha square, ~0.4% for
# a 100 m² plot). 1% passes that rounding and still rejects a lost/extra block.
AREA_CONSERVATION_REL_TOL = 0.01


def _shapely_polygonal(geometry: dict[str, Any]):  # noqa: ANN202 - Shapely type is optional
    from shapely.geometry import shape  # type: ignore
    from shapely.validation import make_valid  # type: ignore

    geom = shape(normalize_geojson_polygonal(geometry))
    return geom if geom.is_valid else make_valid(geom)


def area_conservation_issues(
    sources: list[Any],
    results: list[dict[str, Any]],
    *,
    rel_tol: float = AREA_CONSERVATION_REL_TOL,
) -> list[str]:
    """Return machine codes when ``results`` do not partition ``union(sources)``.

    Used for split (one source, several children) and merge (several sources, one
    result). Overlay is planar in lon/lat; only area *ratios* are compared, which
    are scale-invariant within a field-sized extent. A missing source geometry
    cannot be verified and is reported instead of silently accepted.
    """
    if any(not isinstance(src, dict) for src in sources):
        return ["source_geometry_missing"]
    from shapely.ops import unary_union  # type: ignore

    try:
        source_union = unary_union([_shapely_polygonal(src) for src in sources])
    except Exception:  # noqa: BLE001 - malformed stored geometry is reported, not raised
        return ["source_geometry_invalid"]
    parts = [_shapely_polygonal(res) for res in results]
    result_union = unary_union(parts)
    reference = source_union.area
    if reference <= 0:
        return ["source_geometry_empty"]
    tolerance = rel_tol * reference
    issues: list[str] = []
    if sum(p.area for p in parts) - result_union.area > tolerance:
        issues.append("result_parts_overlap")
    if source_union.difference(result_union).area > tolerance:
        issues.append("source_area_not_covered")
    if result_union.difference(source_union).area > tolerance:
        issues.append("result_outside_source")
    return issues


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
