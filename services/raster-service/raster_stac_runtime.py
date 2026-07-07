"""STAC runtime bootstrap shared by the FastAPI app and standalone workers.

This module owns construction of the resilient STAC client and configuration of
``stac_search`` helpers. Keeping it outside ``main.py`` avoids duplicating the
same provider/fallback wiring in workers while preserving a small app bootstrap.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import raster_settings
import stac_search as stac_search_helpers
from stac_client import ResilientStacClient


def make_stac_client() -> ResilientStacClient:
    """Build the configured resilient STAC client without importing FastAPI app code."""
    return ResilientStacClient(
        raster_settings.EARTH_SEARCH_URL,
        timeout=raster_settings.HTTP_TIMEOUT,
        max_retries=int(os.getenv("STAC_MAX_RETRIES", "3")),
        cache_ttl=float(os.getenv("STAC_CACHE_TTL", "900")),
        redis_url=os.getenv("REDIS_URL"),
        fallback_urls=raster_settings.stac_fallback_chain(),
    )


def configure_stac_search(*, logger: logging.Logger | None = None, stac: Any | None = None) -> Any:
    """Configure ``stac_search`` helpers and return the STAC client in use."""
    client = stac if stac is not None else make_stac_client()
    stac_search_helpers.configure(
        stac=client,
        logger=logger or logging.getLogger("raster-service"),
        earth_search_url=raster_settings.EARTH_SEARCH_URL,
        http_timeout=raster_settings.HTTP_TIMEOUT,
        historical_search_provider=raster_settings.HISTORICAL_SEARCH_PROVIDER,
        sentinel_collection=raster_settings.SENTINEL_COLLECTION,
        sentinel1_collection=raster_settings.SENTINEL1_COLLECTION,
        landsat_collection=raster_settings.LANDSAT_COLLECTION,
        dem_collection=raster_settings.DEM_COLLECTION,
        landsat_unique_indices=raster_settings.LANDSAT_UNIQUE_INDICES,
        landsat_direct_raster_indices=raster_settings.LANDSAT_DIRECT_RASTER_INDICES,
        landsat_derived_indices=raster_settings.LANDSAT_DERIVED_INDICES,
        landsat_duplicate_sentinel_indices=raster_settings.LANDSAT_DUPLICATE_SENTINEL_INDICES,
        landsat_thermal_asset_candidates=raster_settings.LANDSAT_THERMAL_ASSET_CANDIDATES,
    )
    return client
