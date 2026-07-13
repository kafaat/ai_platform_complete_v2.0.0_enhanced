"""Governed P1 soil products: spatial baseline, sampling, hydraulics and water."""
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

class EvidenceOrigin(StrEnum):
    MEASURED='measured'; PEDOTRANSFER='pedotransfer'; MODELLED='modelled'

class SoilGridsLayerSummary(BaseModel):
    model_config=ConfigDict(extra='forbid')
    property: str
    depth_from_cm: float = Field(ge=0)
    depth_to_cm: float = Field(gt=0)
    mean: float|str
    unit: str
    p05: float|None=None
    p95: float|None=None
    uncertainty: float|None=Field(default=None, ge=0)
    @model_validator(mode='after')
    def valid_depth(self):
        if self.depth_to_cm<=self.depth_from_cm: raise ValueError('invalid_depth')
        return self

class SoilGridsSpatialProduct(BaseModel):
    model_config=ConfigDict(extra='forbid')
    product_id: str
    tenant_id: str
    field_id: str
    dataset_version: str
    geometry_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    resolution_m: float = Field(gt=0)
    generated_at: datetime
    source_uri: str|None=None
    layers: list[SoilGridsLayerSummary]=Field(min_length=1)
    provenance: dict[str,Any]=Field(default_factory=dict)

class SamplingCandidate(BaseModel):
    id: str
    lon: float=Field(ge=-180,le=180)
    lat: float=Field(ge=-90,le=90)
    zone_id: str
    uncertainty: float=Field(ge=0,le=1)
    anomaly: float=Field(default=0,ge=0,le=1)
    transition: float=Field(default=0,ge=0,le=1)
    stability: float=Field(default=0.5,ge=0,le=1)
    accessible: bool=True
    boundary_distance_m: float=Field(default=9999,ge=0)

class SamplingPlanRequest(BaseModel):
    tenant_id: str; field_id: str
    mode: str=Field(default='balanced', pattern='^(economic|balanced|high_accuracy)$')
    candidates: list[SamplingCandidate]=Field(min_length=1)
    target_count: int|None=Field(default=None,ge=1,le=200)
    min_boundary_buffer_m: float=Field(default=10,ge=0)
    depths_cm: list[tuple[float,float]]=Field(default_factory=lambda:[(0,30)])
    require_approval: bool=True

class SamplingPoint(BaseModel):
    candidate_id: str; lon: float; lat: float; zone_id: str
    rank: int; score: float; reasons: list[str]
    depths_cm: list[tuple[float,float]]

class SamplingPlan(BaseModel):
    plan_id: str; tenant_id: str; field_id: str; mode: str
    status: str='draft'; created_at: datetime
    points: list[SamplingPoint]
    excluded: dict[str,int]=Field(default_factory=dict)
    approval_required: bool=True
    policy_version: str='soil-sampling.v2'

class HydraulicValue(BaseModel):
    value: float; unit: str; origin: EvidenceOrigin
    confidence: float=Field(ge=0,le=1)
    source_observation_ids: list[str]=Field(default_factory=list)

class SoilHydraulicLayer(BaseModel):
    depth_from_cm: float=Field(ge=0); depth_to_cm: float=Field(gt=0)
    field_capacity: HydraulicValue|None=None
    wilting_point: HydraulicValue|None=None
    saturation: HydraulicValue|None=None
    available_water_capacity: HydraulicValue|None=None
    bulk_density: HydraulicValue|None=None
    coarse_fragments: HydraulicValue|None=None
    ksat: HydraulicValue|None=None
    infiltration: HydraulicValue|None=None
    root_restriction: HydraulicValue|None=None
    van_genuchten: dict[str,HydraulicValue]=Field(default_factory=dict)

class SoilHydraulicProfile(BaseModel):
    profile_id: str; tenant_id: str; field_id: str; generated_at: datetime
    layers: list[SoilHydraulicLayer]=Field(min_length=1)
    completeness_score: float=Field(ge=0,le=1)
    executable: bool
    reasons: list[str]=Field(default_factory=list)
    source_soil_profile_hash: str
    policy_version: str='soil-hydraulics.v1'

class IrrigationWaterSample(BaseModel):
    sample_id: str; tenant_id: str; field_id: str|None=None; source_id: str
    sampled_at: datetime; approved: bool=False
    ecw_ds_m: float|None=Field(default=None,ge=0)
    ph: float|None=Field(default=None,ge=0,le=14)
    na_meq_l: float|None=Field(default=None,ge=0)
    ca_meq_l: float|None=Field(default=None,ge=0)
    mg_meq_l: float|None=Field(default=None,ge=0)
    cl_meq_l: float|None=Field(default=None,ge=0)
    so4_meq_l: float|None=Field(default=None,ge=0)
    hco3_meq_l: float|None=Field(default=None,ge=0)
    co3_meq_l: float|None=Field(default=None,ge=0)
    boron_mg_l: float|None=Field(default=None,ge=0)
    lab_method: str|None=None
    detection_limits: dict[str,float]=Field(default_factory=dict)

class IrrigationWaterProfile(BaseModel):
    profile_id: str; tenant_id: str; source_id: str; field_id: str|None=None
    effective_at: datetime; sample_id: str; approval_status: str
    values: dict[str,float|None]
    sar: float|None=None; rsc_meq_l: float|None=None
    salinity_class: str|None=None; sodium_class: str|None=None; alkalinity_class: str|None=None
    allowed_use: list[str]=Field(default_factory=list)
    blocked_use: list[str]=Field(default_factory=list)
    policy_version: str='irrigation-water.v1'
