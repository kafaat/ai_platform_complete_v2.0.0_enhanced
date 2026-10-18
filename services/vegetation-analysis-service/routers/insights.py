"""Read-only multi-field report built from authenticated canonical observations."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import main
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from routers.baselines import INDICATORS_SERVICE_URL
from weekly_insights import build_weekly_insights

router = APIRouter()


class ReportField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_id: str = Field(pattern=r"^fld_[A-Za-z0-9_-]+$", max_length=128)
    season_id: str = Field(min_length=1, max_length=128)


class WeeklyInsightsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[ReportField] = Field(min_length=1, max_length=100)
    week_end: datetime

    @field_validator("week_end")
    @classmethod
    def aware_past_time(cls, value):
        if value.tzinfo is None or value > datetime.now(UTC):
            raise ValueError("week_end_must_be_aware_and_not_in_future")
        return value

    @field_validator("fields")
    @classmethod
    def unique_fields(cls, values):
        if len({(v.field_id, v.season_id) for v in values}) != len(values):
            raise ValueError("duplicate_field_season")
        return values


@router.post("/v1/reports/weekly-field-insights")
async def weekly_field_insights(
    request: WeeklyInsightsRequest, token: str = Depends(main.security)
):
    tenant = main._tenant_from_claims(main._verify_claims(token))
    limit = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=20) as client:

        async def fetch(field):
            async with limit:
                try:
                    response = await client.get(
                        f"{INDICATORS_SERVICE_URL}/v1/fields/{field.field_id}/observation-timeline",
                        params={"season_id": field.season_id, "indicators": "ndvi"},
                        headers={
                            "Authorization": f"Bearer {token.credentials}",
                            "X-Tenant-Id": tenant,
                        },
                    )
                    if response.status_code in {401, 403, 404}:
                        raise HTTPException(403, "report field authorization unavailable")
                    response.raise_for_status()
                    return {**field.model_dump(), "entries": response.json().get("entries", [])}
                except httpx.HTTPError:
                    return {
                        **field.model_dump(),
                        "entries": [],
                        "reason_codes": ["canonical_source_unavailable"],
                    }

        fields = await asyncio.gather(*(fetch(field) for field in request.fields))
    return build_weekly_insights(tenant_id=tenant, week_end=request.week_end, fields=fields)
