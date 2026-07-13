"""Governed P3 contracts: mobile imaging, analog fields, drainage and reclamation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class MobileImageQuality(BaseModel):
    blur_score: float = Field(ge=0, le=1)
    exposure_score: float = Field(ge=0, le=1)
    shadow_fraction: float = Field(ge=0, le=1)
    reference_card_detected: bool
    scale_marker_detected: bool
    gps_accuracy_m: float = Field(gt=0)


class SoilVisualPrediction(BaseModel):
    salt_crust_probability: float = Field(ge=0, le=1)
    surface_crack_probability: float = Field(ge=0, le=1)
    coarse_fragment_probability: float = Field(ge=0, le=1)
    waterlogging_probability: float = Field(ge=0, le=1)
    color_class: str | None = None
    segmentation_confidence: float = Field(ge=0, le=1)


class MobileSoilImageRequest(BaseModel):
    tenant_id: str
    field_id: str
    image_id: str = Field(default_factory=lambda: f"simg_{uuid4().hex}")
    object_uri: str
    captured_at: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    depth_cm: float = Field(ge=0, le=500)
    surface_moisture_state: Literal["dry", "moist", "wet", "unknown"]
    quality: MobileImageQuality
    prediction: SoilVisualPrediction
    model_version: str = "soil-vision-v1"
    reviewer_id: str | None = None
    review_status: Literal["not_required", "pending", "approved", "rejected"] = "not_required"


class SoilVisualObservation(BaseModel):
    visual_observation_id: str = Field(default_factory=lambda: f"svo_{uuid4().hex}")
    tenant_id: str
    field_id: str
    image_id: str
    object_uri: str
    captured_at: datetime
    depth_cm: float
    quality_gate_passed: bool
    quality_reasons: list[str]
    review_required: bool
    review_status: str
    accepted_predictions: dict[str, float | str]
    blocked_use: list[str]
    evidence_class: Literal["field_observed"] = "field_observed"
    confidence: float = Field(ge=0, le=1)
    provenance: dict


class AnalogFieldCandidate(BaseModel):
    field_id: str
    tenant_group: str | None = None
    terrain: dict[str, float] = {}
    climate: dict[str, float] = {}
    soilgrids: dict[str, float] = {}
    spectral: dict[str, float] = {}
    crop_history: dict[str, float] = {}
    irrigation_water: dict[str, float] = {}
    trusted_properties: dict[str, float]
    evidence_quality: float = Field(ge=0, le=1)


class AnalogFieldRequest(BaseModel):
    tenant_id: str
    field_id: str
    target_features: dict[str, dict[str, float]]
    candidates: list[AnalogFieldCandidate]
    requested_properties: list[str]
    model_version: str = "analog-fields-v1"
    minimum_cohort_size: int = Field(default=3, ge=2, le=50)
    max_candidates: int = Field(default=8, ge=2, le=50)
    max_distance: float = Field(default=0.65, gt=0, le=2)


class AnalogPropertyEstimate(BaseModel):
    property_name: str
    estimated_value: float | None
    uncertainty: float = Field(ge=0, le=1)
    cohort_size: int
    status: Literal["estimated", "insufficient_cohort", "out_of_domain"]


class AnalogFieldProduct(BaseModel):
    product_id: str = Field(default_factory=lambda: f"afp_{uuid4().hex}")
    tenant_id: str
    field_id: str
    model_version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    anonymized_cohort: list[dict]
    estimates: list[AnalogPropertyEstimate]
    out_of_domain: bool
    blocked_use: list[str]
    provenance: dict


class DrainageAssessmentRequest(BaseModel):
    tenant_id: str
    field_id: str
    geometry_hash: str
    assessment_version: str = "drainage-v1"
    natural_outlet_score: float = Field(ge=0, le=1)
    water_table_depth_m: float | None = Field(default=None, ge=0)
    impermeable_layer_depth_m: float | None = Field(default=None, ge=0)
    depression_fraction: float = Field(ge=0, le=1)
    mean_drainage_gradient_pct: float = Field(ge=0)
    ksat_mm_h: float | None = Field(default=None, ge=0)
    flood_risk: float = Field(ge=0, le=1)
    wadi_risk: float = Field(ge=0, le=1)
    salinity_persistence: float = Field(ge=0, le=1)
    surveyed_elevations: bool = False


class DrainageAssessmentProduct(BaseModel):
    product_id: str = Field(default_factory=lambda: f"dap_{uuid4().hex}")
    tenant_id: str
    field_id: str
    geometry_hash: str
    assessment_version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    drainage_need: Literal["none", "monitor", "surface", "subsurface", "combined"]
    waterlogging_risk: float = Field(ge=0, le=1)
    engineering_confidence: float = Field(ge=0, le=1)
    prerequisites: list[str]
    recommendations: list[str]
    blocked_actions: list[str]
    provenance: dict


class ReclamationAssessmentRequest(BaseModel):
    tenant_id: str
    field_id: str
    geometry_hash: str
    assessment_version: str = "reclamation-v1"
    salinity_probability: float = Field(ge=0, le=1)
    sodicity_probability: float = Field(ge=0, le=1)
    gypsum_probability: float = Field(ge=0, le=1)
    stoniness_fraction: float = Field(ge=0, le=1)
    compaction_risk: float = Field(ge=0, le=1)
    leveling_need: float = Field(ge=0, le=1)
    drainage_need: Literal["none", "monitor", "surface", "subsurface", "combined"]
    crop_suitability_score: float = Field(ge=0, le=1)
    ec_lab_ds_m: float | None = Field(default=None, ge=0)
    esp_pct: float | None = Field(default=None, ge=0)
    irrigation_water_profile_approved: bool = False
    drainage_engineering_verified: bool = False
    lab_verified: bool = False


class ReclamationAssessmentProduct(BaseModel):
    product_id: str = Field(default_factory=lambda: f"rap_{uuid4().hex}")
    tenant_id: str
    field_id: str
    geometry_hash: str
    assessment_version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    suitability_class: Literal[
        "suitable", "conditionally_suitable", "marginal", "not_currently_suitable"
    ]
    reclamation_priority: Literal["low", "medium", "high", "critical"]
    interventions: list[dict]
    phased_plan: list[dict]
    allowed_actions: list[str]
    blocked_actions: list[str]
    confidence: float = Field(ge=0, le=1)
    provenance: dict


class ReclamationEconomicsRequest(BaseModel):
    tenant_id: str
    field_id: str
    area_ha: float = Field(gt=0)
    currency: str = "USD"
    water_cost_per_m3: float = Field(ge=0)
    energy_cost_per_kwh: float = Field(ge=0)
    gypsum_cost_per_tonne: float = Field(ge=0)
    drainage_cost_per_ha: float = Field(ge=0)
    leveling_cost_per_ha: float = Field(ge=0)
    stone_removal_cost_per_ha: float = Field(ge=0)
    expected_annual_margin_per_ha: float = Field(ge=0)
    discount_rate: float = Field(default=0.1, ge=0, le=1)
    horizon_years: int = Field(default=10, ge=1, le=30)
    water_m3_per_ha: float = Field(default=0, ge=0)
    energy_kwh_per_ha: float = Field(default=0, ge=0)
    gypsum_t_per_ha: float = Field(default=0, ge=0)
    drainage_required: bool = False
    leveling_required: bool = False
    stone_removal_required: bool = False


class ReclamationScenario(BaseModel):
    name: Literal["minimum", "balanced", "full"]
    capex: float
    annual_opex: float
    expected_annual_benefit: float
    payback_years: float | None
    npv: float
    risk_adjusted_npv: float
    implementation_years: float
    assumptions: dict


class ReclamationEconomicsProduct(BaseModel):
    product_id: str = Field(default_factory=lambda: f"rep_{uuid4().hex}")
    tenant_id: str
    field_id: str
    currency: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    scenarios: list[ReclamationScenario]
    recommended_scenario: str | None
    provenance: dict
