"""SAHOOL shared GIS package.

Unified, dependency-light CRS helpers. SAHOOL stores geometry in EPSG:4326
(WGS84 lon/lat) only; this package gives callers one place for normalization
and map-projection transforms.
"""

from __future__ import annotations

from shared.gis.crs_service import (
    WEB_MERCATOR,
    WGS84,
    normalize_to_wgs84,
    transform_to_map_projection,
)

__all__ = [
    "WEB_MERCATOR",
    "WGS84",
    "normalize_to_wgs84",
    "transform_to_map_projection",
]
