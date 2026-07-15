"""Canonical temporal baseline routes (RS-5)."""

from __future__ import annotations

import os
from typing import Any

import httpx
import main
from baseline_engine import build_baselines
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()
INDICATORS_SERVICE_URL = os.getenv(
    "INDICATORS_SERVICE_URL", "http://sahool-indicators-service:8000"
).rstrip("/")


class BaselineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    season_id: str = Field(min_length=1, max_length=128)
    indicator: str = Field(default="ndvi", min_length=1, max_length=64)
    current_stage: str | None = Field(default=None, max_length=128)
    stage_by_observation: dict[str, str] = Field(default_factory=dict)
    max_history: int = Field(default=12, ge=1, le=60)


@router.post("/v1/fields/{field_id}/baseline-comparisons")
async def baseline_comparisons(
    field_id: str,
    request: BaselineRequest,
    token: str = Depends(main.security),
):
    claims = main._verify_claims(token)
    tenant_id = main._tenant_from_claims(claims)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{INDICATORS_SERVICE_URL}/v1/fields/{field_id}/observation-timeline",
                params={"season_id": request.season_id, "indicators": request.indicator},
                headers={"X-Tenant-Id": tenant_id},
            )
        if response.status_code != 200:
            raise HTTPException(424, "canonical observation timeline unavailable")
        timeline: dict[str, Any] = response.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(424, "canonical observation timeline unavailable") from exc

    comparisons = build_baselines(
        field_id=field_id,
        indicator=request.indicator,
        entries=list(timeline.get("entries") or []),
        current_stage=request.current_stage,
        stage_by_observation=request.stage_by_observation,
        max_history=request.max_history,
    )
    if not comparisons:
        raise HTTPException(424, "insufficient canonical history for baseline")
    return {
        "field_id": field_id,
        "season_id": request.season_id,
        "indicator": request.indicator,
        "baseline_comparisons": [item.to_dict() for item in comparisons],
        "source": "vegetation-analysis-service",
        "canonical_observations_only": True,
        "phenology_context_applied": bool(request.current_stage),
    }
