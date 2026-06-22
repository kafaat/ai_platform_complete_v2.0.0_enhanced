"""Unified CRS service for SAHOOL — normalization + map-projection transforms.

SAHOOL's internal canon is **WGS84 / EPSG:4326** (geographic lon/lat). Geometry
is *stored* in 4326 only; the geometry guard
(``services/sahool-platform/api/gis_geometry_guard.py``) strips any GeoJSON
``crs`` member on ingest. This module is the single explicit place callers reach
for two operations:

* :func:`normalize_to_wgs84` — assert/normalize a GeoJSON geometry to EPSG:4326,
  rejecting a *declared* non-4326 CRS (we do not silently reproject geographic
  data on ingest; SAHOOL stores 4326 only). Already-4326 GeoJSON has its ``crs``
  member stripped and is returned in canonical lon/lat order.
* :func:`transform_to_map_projection` — project canonical 4326 lon/lat into
  Web Mercator (EPSG:3857) for raster / map-tile output.

Dependency policy: ``pyproj`` is **not** a SAHOOL dependency (it appears in no
``requirements*.txt``). To stay zero-new-dependency, the Web Mercator transform
is implemented inline with the standard spherical formula (the exact same
formula EPSG:3857 / EPSG:900913 web-tiling uses). If ``pyproj`` is ever added to
the dependency set it will be used automatically; until then the inline formula
is authoritative.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

# ── Canonical CRS identifiers ──────────────────────────────────────────────
WGS84 = "EPSG:4326"
WEB_MERCATOR = "EPSG:3857"

# EPSG:3857 sphere radius (semi-major axis of WGS84, used as a sphere). This is
# the value baked into the de-facto web-mercator / slippy-map definition.
_EARTH_RADIUS_M = 6378137.0

# CRS strings (upper-cased) that are equivalent to EPSG:4326. Mirrors the set
# accepted by ``api.geospatial_integrity.validate_crs`` so callers see one
# consistent notion of "this is already WGS84".
_WGS84_FORMS: frozenset[str] = frozenset(
    {
        "EPSG:4326",
        "4326",
        "WGS84",
        "WGS:84",
        "WGS 84",
        "URN:OGC:DEF:CRS:EPSG::4326",
        "URN:OGC:DEF:CRS:OGC:1.3:CRS84",
        "HTTP://WWW.OPENGIS.NET/DEF/CRS/EPSG/0/4326",
        "OGC:CRS84",
        "CRS:84",
        "CRS84",
    }
)


def _is_wgs84(crs_string: str | None) -> bool:
    """True when ``crs_string`` denotes EPSG:4326 (or is absent → assumed 4326)."""
    if crs_string is None:
        return True
    token = str(crs_string).strip().upper()
    if not token:
        return True
    return token in _WGS84_FORMS


def _extract_declared_crs(geojson: dict[str, Any]) -> str | None:
    """Return the CRS name declared in a (legacy) GeoJSON ``crs`` member, if any.

    GeoJSON 2008 allowed ``{"crs": {"type": "name", "properties": {"name": ...}}}``.
    RFC 7946 dropped it (everything is WGS84). We read it only to *reject*
    non-4326 declarations; we never carry it forward.
    """
    crs = geojson.get("crs")
    if not isinstance(crs, dict):
        return None
    props = crs.get("properties")
    if isinstance(props, dict):
        name = props.get("name")
        if isinstance(name, str):
            return name
    return None


def _strip_crs(obj: Any) -> Any:
    """Recursively drop any ``crs`` member from a GeoJSON object (in place on a copy)."""
    if isinstance(obj, dict):
        obj.pop("crs", None)
        for value in obj.values():
            _strip_crs(value)
    elif isinstance(obj, list):
        for item in obj:
            _strip_crs(item)
    return obj


def normalize_to_wgs84(geojson: dict[str, Any]) -> dict[str, Any]:
    """Assert/normalize a GeoJSON geometry to canonical EPSG:4326 (lon/lat).

    SAHOOL stores geometry in EPSG:4326 only. This function:

    * accepts GeoJSON that is already 4326 (the SAHOOL norm), strips any legacy
      ``crs`` member, and returns it in canonical lon/lat order;
    * **raises** :class:`ValueError` when a non-4326 CRS is *declared*. We do not
      reproject geographic coordinates on ingest — callers must reproject to
      4326 before storing (e.g. with ogr2ogr / a GIS pipeline). Web Mercator and
      other projected systems are *output* concerns, see
      :func:`transform_to_map_projection`.

    The input is not mutated; a deep copy is returned.

    Args:
        geojson: A GeoJSON-shaped ``dict`` (Geometry, Feature, or
            FeatureCollection). Coordinates are assumed to already be lon/lat.

    Returns:
        A new ``dict`` with no ``crs`` member.

    Raises:
        ValueError: if ``geojson`` is not a dict, or declares a non-4326 CRS.
    """
    if not isinstance(geojson, dict):
        raise ValueError("geojson must be a GeoJSON object (dict)")

    declared = _extract_declared_crs(geojson)
    if not _is_wgs84(declared):
        raise ValueError(
            f"non-WGS84 CRS declared ({declared!r}); SAHOOL stores EPSG:4326 only. "
            "Reproject to EPSG:4326 before normalization."
        )

    out = deepcopy(geojson)
    _strip_crs(out)
    return out


def _lonlat_to_web_mercator(lon: float, lat: float) -> list[float]:
    """Spherical Web Mercator (EPSG:3857) forward transform: lon/lat° → x/y metres.

    Latitude is clamped to ±85.05112878° — the standard Web Mercator cutoff
    beyond which y → ±infinity. This is the canonical slippy-map formula.
    """
    lon = float(lon)
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    x = math.radians(lon) * _EARTH_RADIUS_M
    y = math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) * _EARTH_RADIUS_M
    return [x, y]


def _transform_coords(coords: Any, fn: Any) -> Any:
    """Recursively apply ``fn`` to every ``[lon, lat]`` pair in a coordinate tree."""
    if (
        isinstance(coords, (list, tuple))
        and len(coords) >= 2
        and all(isinstance(c, (int, float)) for c in coords[:2])
    ):
        return fn(coords[0], coords[1])
    if isinstance(coords, (list, tuple)):
        return [_transform_coords(c, fn) for c in coords]
    raise ValueError("invalid coordinate structure")


def transform_to_map_projection(
    geojson: dict[str, Any], target: str = WEB_MERCATOR
) -> dict[str, Any]:
    """Project a canonical EPSG:4326 GeoJSON geometry into Web Mercator (EPSG:3857).

    Use this for raster / map-tile output where projected (metre) coordinates are
    required. The input is first normalized via :func:`normalize_to_wgs84` (so a
    declared non-4326 CRS is rejected), then every coordinate is projected.

    Implementation uses :mod:`pyproj` **only if it is installed**; ``pyproj`` is
    not a SAHOOL dependency, so the default path is the inline spherical
    Web Mercator formula (identical result for the EPSG:3857 case). No new
    dependency is introduced.

    The output GeoJSON carries an explicit ``crs`` member naming the target —
    these are *projected output* coordinates, no longer the storable 4326 canon.

    Args:
        geojson: A GeoJSON-shaped ``dict`` in EPSG:4326 (lon/lat).
        target: Target CRS. Only ``"EPSG:3857"`` (Web Mercator) is supported.

    Returns:
        A new ``dict`` with projected coordinates and ``crs`` = ``target``.

    Raises:
        ValueError: if ``target`` is not EPSG:3857, or coordinates are malformed.
    """
    if str(target).strip().upper() not in {WEB_MERCATOR, "3857", "EPSG:900913"}:
        raise ValueError(
            f"unsupported target projection {target!r}; only {WEB_MERCATOR} is supported"
        )

    normalized = normalize_to_wgs84(geojson)

    project = _make_projector()
    out = _project_geojson(normalized, project)
    out["crs"] = {"type": "name", "properties": {"name": WEB_MERCATOR}}
    return out


def _make_projector() -> Any:
    """Return a ``(lon, lat) -> [x, y]`` projector.

    Prefers :mod:`pyproj` when installed (it is *not* a declared dependency);
    otherwise falls back to the inline spherical formula. Both yield EPSG:3857.
    """
    try:
        from pyproj import Transformer  # type: ignore
    except Exception:
        return _lonlat_to_web_mercator

    transformer = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)

    def _project(lon: float, lat: float) -> list[float]:
        x, y = transformer.transform(lon, lat)
        return [x, y]

    return _project


def _project_geojson(geojson: dict[str, Any], project: Any) -> dict[str, Any]:
    """Apply ``project`` to the coordinates of a Geometry/Feature/FeatureCollection."""
    gtype = geojson.get("type")

    if gtype == "FeatureCollection":
        features = geojson.get("features") or []
        return {
            "type": "FeatureCollection",
            "features": [_project_geojson(f, project) for f in features],
        }

    if gtype == "Feature":
        out = deepcopy(geojson)
        geometry = geojson.get("geometry")
        out["geometry"] = (
            _project_geojson(geometry, project) if isinstance(geometry, dict) else None
        )
        return out

    if gtype == "GeometryCollection":
        geoms = geojson.get("geometries") or []
        return {
            "type": "GeometryCollection",
            "geometries": [_project_geojson(g, project) for g in geoms],
        }

    coords = geojson.get("coordinates")
    if coords is None:
        raise ValueError(f"geometry of type {gtype!r} has no coordinates")
    return {"type": gtype, "coordinates": _transform_coords(coords, project)}
