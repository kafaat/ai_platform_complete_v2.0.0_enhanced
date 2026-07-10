"""Pydantic request/response models and API enums for raster-service.

Extracted from main.py during staged decomposition.  main.py re-exports these
symbols for backward compatibility with routers, workers, and existing tests.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class IndicatorKind(StrEnum):
    ndvi = "ndvi"
    evi = "evi"
    savi = "savi"
    ndwi = "ndwi"
    ndmi = "ndmi"
    gndvi = "gndvi"
    fapar = "fapar"
    vari = "vari"
    gli = "gli"
    tgi = "tgi"
    ndre = "ndre"
    reci = "reci"
    gci = "gci"
    arvi = "arvi"
    sipi = "sipi"
    nbr = "nbr"
    ccci = "ccci"
    msi = "msi"
    msavi = "msavi"
    moisture = "moisture"
    bsi = "bsi"
    bi = "bi"
    bi2 = "bi2"
    ndti = "ndti"
    dbsi = "dbsi"
    ndsi = "ndsi"
    satvi = "satvi"
    lst = "lst"
    cwsi = "cwsi"
    tvdi = "tvdi"
    tci = "tci"
    vhi = "vhi"
    et_inputs = "et_inputs"
    truecolor = "truecolor"


class SourceFormat(StrEnum):
    sentinel2_l2a = "sentinel2_l2a"
    sentinel2_l1c = "sentinel2_l1c"
    landsat8 = "landsat8"
    drone_orthomosaic = "drone_orthomosaic"
    custom = "custom"


class JobStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BandMapping(BaseModel):
    red: int | None = None
    green: int | None = None
    blue: int | None = None
    nir: int | None = None
    rededge: int | None = None
    swir1: int | None = None
    swir2: int | None = None
    scl: int | None = None
    clp: int | None = None
    clm: int | None = None
    qa_pixel: int | None = None


class ProcessRequest(BaseModel):
    tenant_id: str
    field_id: str | None = None
    raster_url: str | None = None
    indicator: IndicatorKind
    source_format: SourceFormat
    bands: BandMapping
    clip_polygon_geojson: dict | None = None
    apply_cloud_mask: bool = True
    reflectance_scale: float | None = None
    reflectance_offset: float | None = None
    tiling_strategy: str = "pyramid"
    zoom_min: int = 10
    zoom_max: int = 18
    scene_id: str | None = None
    capture_datetime: str | None = None
    precomputed_index: bool = False
    provider: str | None = None
    geometry_revision: int | None = None
    raw_qa_required: bool = True
    min_raw_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    sun_azimuth_deg: float | None = Field(default=None, ge=0.0, le=360.0)
    sun_altitude_deg: float | None = Field(default=None, ge=-90.0, le=90.0)




class RawDataProcessRequest(BaseModel):
    tenant_id: str
    field_id: str | None = None
    raster_url: str
    bands: list[int] | None = Field(default=None, description="1-based raw band indices to inspect")
    normalize_reflectance: bool = False
    include_tags: bool = False
    max_pixels: int = Field(default=2_000_000, ge=10_000, le=25_000_000)
    source_kind: str = "satellite_raster"
    product_level: str = "raw_or_provider_processed_raster"
    capture_datetime: str | None = None


class RawDataProcessResponse(BaseModel):
    schema: str
    status: str
    tenant_id: str
    field_id: str | None = None
    source: dict
    raw_bands: list[dict]
    normalized_bands: list[dict] = Field(default_factory=list)
    tags: dict = Field(default_factory=dict)
    source_kind: str = "satellite_raster"
    product_level: str = "raw_or_provider_processed_raster"
    quality_flags: dict = Field(default_factory=dict)
    quality_score: dict = Field(default_factory=dict)
    spatial_alignment: dict = Field(default_factory=dict)
    temporal_alignment: dict = Field(default_factory=dict)
    provenance: dict


class BatchProcessRequest(BaseModel):
    tenant_id: str
    field_id: str | None = None
    raster_url: str | None = None
    indicators: list[IndicatorKind]
    source_format: SourceFormat
    bands: BandMapping
    clip_polygon_geojson: dict | None = None
    apply_cloud_mask: bool = True
    scene_id: str | None = None
    capture_datetime: str | None = None
    geometry_revision: int | None = None
    raw_qa_required: bool = True
    min_raw_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    sun_azimuth_deg: float | None = Field(default=None, ge=0.0, le=360.0)
    sun_altitude_deg: float | None = Field(default=None, ge=-90.0, le=90.0)


class SearchRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    datetime_start: str
    datetime_end: str
    max_cloud_pct: float = 30
    limit: int = 20


class HistoricalBackfillPreset(StrEnum):
    last_2_years = "last_2_years"
    auto_12_months = "auto_12_months"
    extended_3_years = "extended_3_years"
    research_5_years = "research_5_years"
    custom = "custom"


BACKFILL_PRESET_MONTHS = {
    HistoricalBackfillPreset.last_2_years: 24,
    HistoricalBackfillPreset.auto_12_months: 12,
    HistoricalBackfillPreset.extended_3_years: 36,
    HistoricalBackfillPreset.research_5_years: 60,
}


class HistoricalBackfillRequest(BaseModel):
    tenant_id: str | None = None
    preset: HistoricalBackfillPreset = HistoricalBackfillPreset.last_2_years
    from_date: str | None = None
    to_date: str | None = None
    months: int | None = Field(default=None, ge=1, le=120)
    indices: list[IndicatorKind] = Field(
        default_factory=lambda: [
            IndicatorKind.ndvi,
            IndicatorKind.ndmi,
            IndicatorKind.savi,
            IndicatorKind.evi,
        ]
    )
    max_cloud_pct: float = Field(default=50, ge=0, le=100)
    limit_per_month: int = Field(default=8, ge=1, le=8)
    geometry_revision: int | None = None
    apply_cloud_mask: bool = True
    source: str = Field(default="sentinel-2")
    clip_polygon_geojson: dict | None = None
    dry_run: bool = False


class AutoBackfillPolicy(BaseModel):
    enabled: bool = True
    default_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.last_2_years
    extended_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.extended_3_years
    research_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.research_5_years
    default_indices: list[str] = ["truecolor", "ndvi", "ndmi", "ndre", "msavi", "ndwi", "ndsi"]
    max_cloud_pct: float = 50
    note: str = (
        "Use last_2_years on field creation (two-season agronomic baseline). Core "
        "timeline imagery follows agronomic policy: Sentinel-2 scenes every 3-5 days "
        "when clear scene percentage is >=50% (cloud <=50%), with >=70% clear marked "
        "high quality. Advanced indicators remain opt-in/on-demand."
    )


class SceneCandidate(BaseModel):
    item_id: str | None = None
    datetime: str | None = None
    cloud_cover_pct: float | None = None
    aoi_cloud_pct: float | None = None
    coverage_pct: float | None = None
    view_angle: float | None = None
    provider_quality: float | None = None
    source: str | None = None
    properties: dict | None = None


class SceneRankRequest(BaseModel):
    scenes: list[SceneCandidate]
    mode: str = Field(default="best_available")
    max_cloud_pct: float = Field(default=40, ge=0, le=100)
    prefer_recent_days: int = Field(default=45, ge=1, le=3650)


class MosaicPlanRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    datetime_start: str
    datetime_end: str
    max_cloud_pct: float = Field(default=40, ge=0, le=100)
    limit: int = Field(default=20, ge=1, le=100)
    mosaic_rule: str = Field(default="least_cloud_then_recent")


class GeoParquetExportRequest(BaseModel):
    tenant_id: str | None = None
    field_ids: list[str] | None = None
    include_raster_assets: bool = True
    output_name: str = Field(default="field_analytics")


class TimeSeriesAnalyzeRequest(BaseModel):
    scene_values: list[dict]


class ManagementZonesRequest(BaseModel):
    pixel_values: list[float]
    n_zones: int = 3
    base_rate: float | None = None
    strategy: str = "compensate"


MAX_CHANGE_GRID_CELLS = 256 * 256


class ChangeDetectRequest(BaseModel):
    field_id: str
    index: str = "ndvi"
    date_before: str
    date_after: str
    grid_before: list[list[float | None]]
    grid_after: list[list[float | None]]
    slight_threshold: float = 0.1
    severe_threshold: float = 0.2


class FvcComputeRequest(BaseModel):
    field_id: str
    date: str
    ndvi_grid: list[list[float | None]]
    method: str = "cumulative_frequency"
    ndvi_soil: float | None = None
    ndvi_veg: float | None = None


class SarRviRequest(BaseModel):
    field_id: str
    date: str
    vv_grid: list[list[float | None]]
    vh_grid: list[list[float | None]]
    in_db: bool = False


class TerrainRequest(BaseModel):
    dem_url: str
    pixel_size_m: float = 30.0


class ProcessFromStacRequest(BaseModel):
    tenant_id: str | None = None
    indicator: IndicatorKind = IndicatorKind.ndvi
    band_hrefs: dict[str, str]
    scene_id: str | None = None
    capture_datetime: str | None = None
    apply_cloud_mask: bool = True
    clip_polygon_geojson: dict | None = None
    source_format: SourceFormat = SourceFormat.sentinel2_l2a
    geometry_revision: int | None = None


class ProcessCdseRequest(BaseModel):
    tenant_id: str | None = None
    indicators: list[str] = ["ndvi"]
    bbox: list[float]
    geometry: dict | None = None
    lookback_days: int = 30
    max_cloud_pct: float = 40.0
    date_from: str | None = None
    date_to: str | None = None
    geometry_revision: int | None = None


class PrescriptionRequest(BaseModel):
    index: str = "ndvi"
    date: str = "latest"
    grid: int = Field(32, ge=2, le=256)
    n_zones: int = Field(3, ge=2, le=6)
    base_rate: float | None = None
    strategy: str = "compensate"


class FieldChangeRequest(BaseModel):
    index: str = "ndvi"
    date_a: str
    date_b: str
    grid: int = Field(32, ge=2, le=256)
    slight_threshold: float = 0.1
    severe_threshold: float = 0.2


class SalinityClassifyRequest(BaseModel):
    ndsi: float


class SalinityFitRequest(BaseModel):
    samples: list[dict]
