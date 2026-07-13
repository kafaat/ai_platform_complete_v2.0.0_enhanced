"""Governed P2 spatial-soil product contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class BareSoilScene(BaseModel):
    scene_id: str
    acquired_at: datetime
    cloud_fraction: float = Field(ge=0, le=1)
    shadow_fraction: float = Field(ge=0, le=1)
    vegetation_fraction: float = Field(ge=0, le=1)
    bare_fraction: float = Field(ge=0, le=1)
    moisture_proxy: float = Field(ge=0, le=1)
    band_means: dict[str, float]
    source_uri: str | None = None


class BareSoilCompositeRequest(BaseModel):
    tenant_id: str
    field_id: str
    geometry_hash: str
    algorithm_version: str = "bare-soil-v1"
    scenes: list[BareSoilScene]
    min_bare_fraction: float = 0.35
    max_cloud_fraction: float = 0.2
    max_shadow_fraction: float = 0.15
    max_vegetation_fraction: float = 0.25


class BareSoilComposite(BaseModel):
    product_id: str = Field(default_factory=lambda: f"bsc_{uuid4().hex}")
    tenant_id: str
    field_id: str
    geometry_hash: str
    algorithm_version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    selected_scene_ids: list[str]
    rejected_scenes: dict[str, list[str]]
    normalized_band_medians: dict[str, float]
    confidence_score: float = Field(ge=0, le=1)
    confidence_mask_summary: dict[str, float]
    provenance: dict


class TerrainRequest(BaseModel):
    tenant_id: str
    field_id: str
    geometry_hash: str
    dem_version: str
    cell_size_m: float = Field(gt=0)
    elevation_m: list[list[float]]

    @model_validator(mode="after")
    def rectangular(self):
        if len(self.elevation_m) < 3 or any(len(r) < 3 for r in self.elevation_m):
            raise ValueError("DEM must be at least 3x3")
        w = len(self.elevation_m[0])
        if any(len(r) != w for r in self.elevation_m):
            raise ValueError("DEM rows must have equal width")
        return self


class TerrainDerivativesProduct(BaseModel):
    product_id: str = Field(default_factory=lambda: f"tdp_{uuid4().hex}")
    tenant_id: str
    field_id: str
    geometry_hash: str
    dem_version: str
    algorithm_version: str = "terrain-v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    shape: list[int]
    summaries: dict[str, dict[str, float]]
    drainage_paths: list[dict]
    depressions: list[dict]
    landform_counts: dict[str, int]
    provenance: dict


class TextureFeatureVector(BaseModel):
    zone_id: str
    bare_bands: dict[str, float]
    sentinel1: dict[str, float] = {}
    terrain: dict[str, float] = {}
    soilgrids: dict[str, float] = {}
    geology_class: str | None = None


class TextureCalibrationSample(BaseModel):
    feature: TextureFeatureVector
    clay_pct: float = Field(ge=0, le=100)
    sand_pct: float = Field(ge=0, le=100)
    silt_pct: float = Field(ge=0, le=100)


class TextureProbabilityRequest(BaseModel):
    tenant_id: str
    field_id: str
    geometry_hash: str
    model_version: str = "texture-prob-v1"
    features: list[TextureFeatureVector]
    calibration_samples: list[TextureCalibrationSample] = []
    validation_folds: int = Field(default=5, ge=2, le=10)


class TextureZoneProbability(BaseModel):
    zone_id: str
    clay_probability: float = Field(ge=0, le=1)
    sand_probability: float = Field(ge=0, le=1)
    silt_probability: float = Field(ge=0, le=1)
    texture_class: str
    uncertainty: float = Field(ge=0, le=1)
    estimated_clay_pct: float
    estimated_sand_pct: float
    estimated_silt_pct: float


class TextureProbabilityProduct(BaseModel):
    product_id: str = Field(default_factory=lambda: f"txp_{uuid4().hex}")
    tenant_id: str
    field_id: str
    geometry_hash: str
    model_version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    zones: list[TextureZoneProbability]
    spatial_cv: dict
    provenance: dict


class SalinityZoneEvidence(BaseModel):
    zone_id: str
    salinity_index: float = Field(ge=0, le=1)
    brightness: float = Field(ge=0, le=1)
    gypsum_index: float = Field(ge=0, le=1)
    carbonate_index: float = Field(ge=0, le=1)
    persistence: float = Field(ge=0, le=1)
    drainage_risk: float = Field(ge=0, le=1)
    ec_lab_ds_m: float | None = None
    esp_pct: float | None = None
    sar: float | None = None
    ecw_ds_m: float | None = None


class SalinityAssessmentRequest(BaseModel):
    tenant_id: str
    field_id: str
    geometry_hash: str
    model_version: str = "salinity-v1"
    zones: list[SalinityZoneEvidence]


class SalinityZoneAssessment(BaseModel):
    zone_id: str
    salinity_probability: float = Field(ge=0, le=1)
    sodicity_probability: float = Field(ge=0, le=1)
    gypsum_probability: float = Field(ge=0, le=1)
    carbonate_probability: float = Field(ge=0, le=1)
    bright_sand_probability: float = Field(ge=0, le=1)
    uncertainty: float = Field(ge=0, le=1)
    classification: str
    evidence_level: Literal["screening", "locally_calibrated", "lab_verified"]
    allowed_use: list[str]
    blocked_use: list[str]


class SalinityAssessmentProduct(BaseModel):
    product_id: str = Field(default_factory=lambda: f"sap_{uuid4().hex}")
    tenant_id: str
    field_id: str
    geometry_hash: str
    model_version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    zones: list[SalinityZoneAssessment]
    provenance: dict
