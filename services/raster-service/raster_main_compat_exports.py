"""Legacy compatibility exports for ``main.py`` during raster-service decomposition.

This module keeps old ``main.<symbol>`` imports working while the application
module stays a thin bootstrap. Production routers/workers should import the
owning modules directly; this façade exists for staged tests and old callers.
"""

from __future__ import annotations

from datetime import datetime

import cdse_singleflight
import raster_date_geo
import raster_quality
import raster_settings
import stac_search as stac_search_helpers
import tile_cache_maint
import tile_observability
from raster_api_models import (
    BACKFILL_PRESET_MONTHS as _BACKFILL_PRESET_MONTHS,
)
from raster_api_models import (
    AutoBackfillPolicy,
    BandMapping,
    BatchProcessRequest,
    ChangeDetectRequest,
    FieldChangeRequest,
    FvcComputeRequest,
    GeoParquetExportRequest,
    HistoricalBackfillPreset,
    HistoricalBackfillRequest,
    IndicatorKind,
    JobStatus,
    ManagementZonesRequest,
    MosaicPlanRequest,
    PrescriptionRequest,
    ProcessRequest,
    SalinityClassifyRequest,
    SalinityFitRequest,
    SarRviRequest,
    SceneCandidate,
    SceneRankRequest,
    SearchRequest,
    SourceFormat,
    TerrainRequest,
    TimeSeriesAnalyzeRequest,
)
from raster_main_runtime import (
    _REQ_TENANT,
    AGENT_TOKEN,
    OFFLINE_PACKS_DIR,
    UPLOAD_DIR,
    _field_layers,
    _field_owner,
    _field_owner_cache,
    _jobs,
    _layers,
    _public_cog_url,
    _require_field_tenant,
    _require_layer_tenant,
    _require_layer_tenant_authorized,
    _require_service_token,
    make_raster_lifespan,
)

# Settings aliases.
EARTH_SEARCH_URL = raster_settings.EARTH_SEARCH_URL
HTTP_TIMEOUT = raster_settings.HTTP_TIMEOUT
TITILER_URL = raster_settings.TITILER_URL
_TRANSPARENT_PNG = raster_settings.TRANSPARENT_PNG
RASTER_NODATA = raster_settings.RASTER_NODATA

# Cache maintenance aliases.
invalidate_field_tile_cache = tile_cache_maint.invalidate_field_tile_cache
prune_tile_cache = tile_cache_maint.prune_tile_cache

# Tile/tilejson observability aliases.
_TILE_OBS = tile_observability.TILE_OBS
_TILE_OBS_BY_INDEX = tile_observability.TILE_OBS_BY_INDEX
_obs_inc = tile_observability.obs_inc

# Date-window and geometry aliases.
_parse_ymd = raster_date_geo.parse_ymd
_bbox_from_geojson = raster_date_geo.bbox_from_geojson
_month_windows = raster_date_geo.month_windows


def _backfill_date_range(req: HistoricalBackfillRequest) -> tuple[datetime, datetime, int]:
    return raster_date_geo.backfill_date_range(req, _BACKFILL_PRESET_MONTHS)


def _scene_band_mapping(bands: dict[str, str]) -> BandMapping:
    keys = ["blue", "green", "red", "nir", "rededge", "swir1", "swir2", "scl"]
    return BandMapping(**{k: i + 1 for i, k in enumerate(keys) if bands.get(k)})


def _bbox_from_geom(geom: dict | None) -> list[float] | None:
    return raster_date_geo.bbox_from_geom(geom)


# STAC helper aliases.
_band_urls_from_assets = stac_search_helpers.band_urls_from_assets
_stac_query = stac_search_helpers.stac_query
_stac_search = stac_search_helpers.stac_search
_stac_search_cdse = stac_search_helpers.stac_search_cdse
_stac_search_element84 = stac_search_helpers.stac_search_element84
_stac_search_radar = stac_search_helpers.stac_search_radar
_landsat_thermal_href = stac_search_helpers.landsat_thermal_href
_stac_search_landsat = stac_search_helpers.stac_search_landsat
_stac_search_landsat_unique = stac_search_helpers.stac_search_landsat_unique
_stac_search_dem = stac_search_helpers.stac_search_dem

# Quality aliases.
_INDICATOR_FORMULAS = raster_quality.INDICATOR_FORMULAS
_quality_from_cloud_pct = raster_quality.quality_from_cloud_pct
_pixel_quality = raster_quality.pixel_quality

# CDSE singleflight aliases.
_cdse_tile_cache = cdse_singleflight.cdse_tile_cache
_cdse_key_locks = cdse_singleflight.cdse_key_locks
_cdse_lock = cdse_singleflight.cdse_lock
_cdse_key_lock = cdse_singleflight.cdse_key_lock
_cdse_prune_key_locks_locked = cdse_singleflight.cdse_prune_key_locks_locked

__all__ = [name for name in globals() if not name.startswith("__") and name not in {"datetime"}]
