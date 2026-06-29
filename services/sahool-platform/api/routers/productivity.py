"""Productivity zones, zone sampling and daily AI brief endpoints.

These endpoints expose OneSoil-inspired precision-ag primitives without claiming
that the backend has full multi-year raster/yield data unless the caller supplies
those observations. They are intentionally transparent and deterministic:

* productivity zones classify supplied observations into high/medium/low/problem;
* zone sampling generates GPS sample targets only from provided coordinates;
* daily brief compresses grounded signals into a short action list.

Production persistence can later be added behind the same contracts. For now the
routes are computation endpoints protected by normal FIELD_VIEW semantics.
"""

from __future__ import annotations

from core.productivity_zones import (
    ProductivityObservation,
    build_daily_ai_brief,
    build_productivity_zones,
    generate_zone_sampling_plan,
)
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.main import Permission, UserSchema, require_permission

router = APIRouter()


class ProductivityObservationIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    area_ha: float = Field(..., gt=0)
    ndvi_mean: float | None = Field(default=None, ge=-1, le=1)
    ndvi_cv: float | None = Field(default=None, ge=0)
    yield_rel: float | None = Field(default=None, ge=0)
    soil_ec_dsm: float | None = Field(default=None, ge=0)
    soil_ph: float | None = Field(default=None, ge=0, le=14)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class ProductivityZonesRequest(BaseModel):
    field_id: str = Field(..., min_length=1, max_length=128)
    observations: list[ProductivityObservationIn] = Field(default_factory=list)


class ZoneSamplingRequest(ProductivityZonesRequest):
    samples_per_low_zone: int = Field(default=3, ge=1, le=20)
    samples_per_medium_zone: int = Field(default=2, ge=1, le=20)
    samples_per_high_zone: int = Field(default=1, ge=1, le=20)


class DailyBriefRequest(BaseModel):
    field_id: str | None = Field(default=None, max_length=128)
    signals: dict = Field(default_factory=dict)
    tasks: list[dict] = Field(default_factory=list)


def _to_core(rows: list[ProductivityObservationIn]) -> list[ProductivityObservation]:
    return [ProductivityObservation(**r.model_dump()) for r in rows]


@router.post("/api/v1/fields/{field_id}/productivity-zones")
def productivity_zones_endpoint(
    field_id: str,
    payload: ProductivityZonesRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """Return management zones from supplied field observations.

    This endpoint does not fabricate raster/yield history. Empty input returns a
    limited-data result, so the UI can ask the user to upload imagery, yield maps
    or lab data instead of showing false zones.
    """
    out = build_productivity_zones(_to_core(payload.observations))
    out["field_id"] = field_id
    out["tenant_id"] = str(user.tenant_id)
    out["source_policy"] = "caller_supplied_observations_only"
    return out


@router.post("/api/v1/fields/{field_id}/zone-sampling-plan")
def zone_sampling_plan_endpoint(
    field_id: str,
    payload: ZoneSamplingRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """Generate GPS sampling points by productivity zone.

    Points are generated only for observations carrying coordinates; unplaceable
    observations are reported explicitly.
    """
    out = generate_zone_sampling_plan(
        _to_core(payload.observations),
        samples_per_low_zone=payload.samples_per_low_zone,
        samples_per_medium_zone=payload.samples_per_medium_zone,
        samples_per_high_zone=payload.samples_per_high_zone,
    )
    out["field_id"] = field_id
    out["tenant_id"] = str(user.tenant_id)
    out["source_policy"] = "no_fake_coordinates"
    return out


@router.post("/api/v1/fields/{field_id}/daily-ai-brief")
def daily_ai_brief_endpoint(
    field_id: str,
    payload: DailyBriefRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """Compress grounded signals into an actionable daily brief."""
    out = build_daily_ai_brief(
        field_id=field_id or payload.field_id, signals=payload.signals, tasks=payload.tasks
    )
    out["tenant_id"] = str(user.tenant_id)
    out["source_policy"] = "rule_based_grounded_summary"
    return out
