"""Minimal ADAPT v2 edge mapping for SAHOOL.

This module is deliberately an interchange adapter, not a canonical data model.
It exports only the ADAPT structures that SAHOOL can prove from existing field
state: Field and FieldBoundary.  It does not claim full ADAPT interoperability
for prescriptions, work orders, products or devices until those mappings have
separate conformance fixtures.

Reference: ADAPT root schema 2.0.2 (data-only standard).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

ADAPT_ROOT_SCHEMA_VERSION = "2.0.2"
SAHOOL_ADAPT_MAPPING_VERSION = "sahool.adapt-edge.v1"


@dataclass(frozen=True)
class AdaptExportBundle:
    schema_version: str
    mapping_version: str
    document: dict[str, Any]
    content_digest: str
    conformance_scope: tuple[str, ...]


def _fmt_number(value: float | int) -> str:
    value = float(value)
    if not (-1.0e308 < value < 1.0e308):
        raise ValueError("coordinate must be finite")
    return format(value, ".12g")


def _ring_wkt(ring: list[list[float]]) -> str:
    if len(ring) < 4:
        raise ValueError("polygon ring requires at least four coordinates")
    pts = [(float(p[0]), float(p[1])) for p in ring if isinstance(p, list) and len(p) >= 2]
    if len(pts) != len(ring):
        raise ValueError("invalid polygon coordinate")
    if pts[0] != pts[-1]:
        raise ValueError("polygon ring must be closed")
    for lon, lat in pts:
        if not -180.0 <= lon <= 180.0:
            raise ValueError("longitude must be within [-180, 180]")
        if not -90.0 <= lat <= 90.0:
            raise ValueError("latitude must be within [-90, 90]")
    return "(" + ", ".join(f"{_fmt_number(x)} {_fmt_number(y)}" for x, y in pts) + ")"


def geojson_polygon_to_wkt(geometry: dict[str, Any]) -> str:
    """Convert Polygon/MultiPolygon GeoJSON to ADAPT-required WKT in EPSG:4326.

    SAHOOL field geometry is already canonical WGS84 at this boundary.  This
    converter therefore performs no reprojection and rejects unsupported types.
    """
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        if not isinstance(coords, list) or not coords:
            raise ValueError("Polygon coordinates missing")
        return "POLYGON (" + ", ".join(_ring_wkt(ring) for ring in coords) + ")"
    if gtype == "MultiPolygon":
        if not isinstance(coords, list) or not coords:
            raise ValueError("MultiPolygon coordinates missing")
        polys = []
        for polygon in coords:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError("invalid MultiPolygon member")
            polys.append("(" + ", ".join(_ring_wkt(ring) for ring in polygon) + ")")
        return "MULTIPOLYGON (" + ", ".join(polys) + ")"
    raise ValueError("ADAPT field boundary export accepts Polygon or MultiPolygon only")


def export_field_boundary_bundle(
    *,
    field_id: str,
    field_name: str,
    geometry: dict[str, Any],
    boundary_revision: int | str,
) -> AdaptExportBundle:
    """Export the proven Field + FieldBoundary subset of ADAPT 2.0.2.

    No prescription or work-order data is synthesized.  IDs are namespaced but
    preserve the SAHOOL identity so round-trip adapters can recover provenance.
    """
    if not field_id or not field_name:
        raise ValueError("field_id and field_name are required")
    if boundary_revision in (None, ""):
        raise ValueError("boundary_revision is required")
    adapt_field_id = f"sahool:field:{field_id}"
    adapt_boundary_id = f"sahool:field-boundary:{field_id}:{boundary_revision}"
    wkt = geojson_polygon_to_wkt(geometry)
    document = {
        "rootSchemaVersion": ADAPT_ROOT_SCHEMA_VERSION,
        "catalog": {
            "description": "SAHOOL ADAPT edge export; canonical authority remains SAHOOL",
            "fields": [
                {
                    "id": {"referenceId": adapt_field_id},
                    "name": field_name,
                    "activeBoundaryId": adapt_boundary_id,
                }
            ],
            "fieldBoundaries": [
                {
                    "id": {"referenceId": adapt_boundary_id},
                    "name": f"{field_name} boundary r{boundary_revision}",
                    "fieldId": adapt_field_id,
                    "boundary": {"geometry": wkt},
                }
            ],
        },
    }
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return AdaptExportBundle(
        schema_version=ADAPT_ROOT_SCHEMA_VERSION,
        mapping_version=SAHOOL_ADAPT_MAPPING_VERSION,
        document=document,
        content_digest=hashlib.sha256(raw).hexdigest(),
        conformance_scope=("catalog.fields", "catalog.fieldBoundaries"),
    )


def _split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for idx, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced WKT parentheses")
        elif char == "," and depth == 0:
            parts.append(value[start:idx].strip())
            start = idx + 1
    if depth != 0:
        raise ValueError("unbalanced WKT parentheses")
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def _strip_outer_parens(value: str) -> str:
    value = value.strip()
    if len(value) < 2 or value[0] != "(" or value[-1] != ")":
        raise ValueError("invalid WKT parentheses")
    return value[1:-1].strip()


def _parse_ring_wkt(value: str) -> list[list[float]]:
    body = _strip_outer_parens(value)
    coords: list[list[float]] = []
    for token in _split_top_level(body):
        parts = token.split()
        if len(parts) != 2:
            raise ValueError("ADAPT boundary WKT must contain 2D coordinates")
        lon, lat = float(parts[0]), float(parts[1])
        if not -180.0 <= lon <= 180.0:
            raise ValueError("longitude must be within [-180, 180]")
        if not -90.0 <= lat <= 90.0:
            raise ValueError("latitude must be within [-90, 90]")
        coords.append([lon, lat])
    if len(coords) < 4 or coords[0] != coords[-1]:
        raise ValueError("ADAPT boundary ring must be closed")
    return coords


def wkt_to_geojson_polygon(wkt: str) -> dict[str, Any]:
    """Parse the Polygon/MultiPolygon WKT subset emitted by this adapter."""
    value = str(wkt or "").strip()
    if value.startswith("POLYGON "):
        body = _strip_outer_parens(value[len("POLYGON ") :])
        rings = [_parse_ring_wkt(part) for part in _split_top_level(body)]
        return {"type": "Polygon", "coordinates": rings}
    if value.startswith("MULTIPOLYGON "):
        body = _strip_outer_parens(value[len("MULTIPOLYGON ") :])
        polygons: list[list[list[list[float]]]] = []
        for polygon in _split_top_level(body):
            polygon_body = _strip_outer_parens(polygon)
            polygons.append([_parse_ring_wkt(part) for part in _split_top_level(polygon_body)])
        return {"type": "MultiPolygon", "coordinates": polygons}
    raise ValueError("ADAPT boundary import accepts Polygon or MultiPolygon WKT only")


def import_field_boundary_bundle(document: dict[str, Any]) -> dict[str, Any]:
    """Round-trip the proven ADAPT Field+FieldBoundary subset back to SAHOOL IDs.

    The importer is strict about the exact bounded conformance scope. It refuses
    foreign/unrelated IDs rather than pretending to implement the full ADAPT model.
    """
    if (
        not isinstance(document, dict)
        or document.get("rootSchemaVersion") != ADAPT_ROOT_SCHEMA_VERSION
    ):
        raise ValueError("unsupported ADAPT root schema version")
    catalog = document.get("catalog")
    if not isinstance(catalog, dict):
        raise ValueError("ADAPT catalog is required")
    fields = catalog.get("fields")
    boundaries = catalog.get("fieldBoundaries")
    if not isinstance(fields, list) or len(fields) != 1:
        raise ValueError("bounded ADAPT import requires exactly one Field")
    if not isinstance(boundaries, list) or len(boundaries) != 1:
        raise ValueError("bounded ADAPT import requires exactly one FieldBoundary")
    field = fields[0]
    boundary = boundaries[0]
    field_ref = str((field.get("id") or {}).get("referenceId") or "")
    boundary_ref = str((boundary.get("id") or {}).get("referenceId") or "")
    if not field_ref.startswith("sahool:field:"):
        raise ValueError("ADAPT field ID is not a SAHOOL edge identity")
    field_id = field_ref.removeprefix("sahool:field:")
    prefix = f"sahool:field-boundary:{field_id}:"
    if not boundary_ref.startswith(prefix):
        raise ValueError("ADAPT boundary ID is not bound to the field identity")
    if field.get("activeBoundaryId") != boundary_ref or boundary.get("fieldId") != field_ref:
        raise ValueError("ADAPT field/boundary references are inconsistent")
    wkt = (boundary.get("boundary") or {}).get("geometry")
    if not isinstance(wkt, str) or not wkt:
        raise ValueError("ADAPT field boundary geometry is required")
    return {
        "field_id": field_id,
        "field_name": str(field.get("name") or ""),
        "boundary_revision": boundary_ref.removeprefix(prefix),
        "geometry": wkt_to_geojson_polygon(wkt),
        "schema_version": ADAPT_ROOT_SCHEMA_VERSION,
        "mapping_version": SAHOOL_ADAPT_MAPPING_VERSION,
        "authority": "interchange_roundtrip_only",
    }
