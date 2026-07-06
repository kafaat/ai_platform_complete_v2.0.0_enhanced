"""routers/imagery.py — سياسات الصور والترتيب والـmosaic وسجلّ COG (Imagery Policy/Registry)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

import os

import raster_api_models as api_models
import scene_policy
import stac_search as stac_search_helpers
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/v1/imagery/backfill/policy")
async def historical_backfill_policy():
    """Return switchable historical imagery presets used by the UI/admin policy.

    This makes the behavior explicit instead of hard-coding a costly global window.
    """
    policy = api_models.AutoBackfillPolicy()
    return {
        **policy.model_dump(),
        "presets": {
            "last_2_years": {
                "months": 24,
                "recommended_for": "new_field_auto_bootstrap_season_comparison",
            },
            "auto_12_months": {"months": 12, "recommended_for": "lighter_single_season_bootstrap"},
            "extended_3_years": {"months": 36, "recommended_for": "season_comparison"},
            "research_5_years": {"months": 60, "recommended_for": "enterprise_research_prediction"},
            "custom": {"months": "1..120", "recommended_for": "explicit_user_selection"},
        },
    }


@router.get("/v1/imagery/quality/policy")
async def imagery_quality_policy():
    """Document the active enterprise imagery policy used by Sahool.

    This exposes the operational rules to frontend/admin tooling so behavior is
    explicit: combine SCL+CLM/CLP where available, rank scenes by quality, and use
    COG+tile-cache for interactive maps.
    """
    return {
        "cloud_mask": {
            "preferred": ["CLM", "CLP", "SCL"],
            "fallback": "warn_and_unmasked_when_no_quality_band",
            "clp_threshold": "0.40 or 40 depending on encoding",
        },
        "scene_ranking": {
            "weights": {"cloud": 0.50, "recency": 0.20, "coverage": 0.20, "provider_quality": 0.10},
            "rule": "AOI cloud percentage overrides scene-level cloud cover when present",
        },
        "mosaic": {
            "default_rule": "least_cloud_then_recent",
            "recommended_for": "latest clear view when one scene is cloudy",
        },
        "tiles": {
            "format": "TileJSON + XYZ",
            "source": "COG",
            "cache": os.getenv("TILE_CACHE_ENABLED", "true"),
        },
        "geometry_history": {"enabled": True, "table": "field_geometry_versions"},
        "analytics_export": {
            "format": "GeoParquet when pyarrow/shapely are installed; NDJSON fallback otherwise"
        },
    }


@router.post("/v1/imagery/scenes/rank")
async def rank_imagery_scenes(req: api_models.SceneRankRequest):
    ranked = scene_policy.rank_scenes(
        req.scenes, max_cloud_pct=req.max_cloud_pct, prefer_recent_days=req.prefer_recent_days
    )
    return {
        "mode": req.mode,
        "count": len(ranked),
        "best_scene": ranked[0] if ranked else None,
        "ranked": ranked,
    }


@router.post("/v1/imagery/mosaic/plan")
async def imagery_mosaic_plan(req: api_models.MosaicPlanRequest):
    """Build a least-cloud mosaic plan from STAC search results.

    The endpoint plans rather than silently rendering a fabricated mosaic. The
    selected scenes are the ranked candidates; processing can then call CDSE with
    leastCC or schedule Element84 VRT processing.
    """
    search = await stac_search_helpers.stac_search(
        req.bbox, req.datetime_start, req.datetime_end, req.max_cloud_pct, req.limit
    )
    ranked = scene_policy.rank_scenes(search.get("items", []), max_cloud_pct=req.max_cloud_pct)
    return {
        "mosaic_rule": req.mosaic_rule,
        "bbox": req.bbox,
        "datetime": {"from": req.datetime_start, "to": req.datetime_end},
        "scenes_found": search.get("count", len(search.get("items", []))),
        "scenes_ranked": len(ranked),
        "selected": ranked[: min(5, len(ranked))],
        "recommendation": "use_cdse_leastCC_when_credentials_available_else_element84_ranked_vrt",
    }


@router.post("/v1/scenes/quality-score")
async def scene_quality_score(payload: dict) -> dict:
    """Score scene quality from cloud/shadow/nodata metadata before processing."""
    import cloud_native_catalog as _cnc

    q = _cnc.score_scene_quality(
        cloud_pct=payload.get("cloud_pct"),
        shadow_pct=payload.get("shadow_pct", 0),
        nodata_pct=payload.get("nodata_pct", 0),
        haze_pct=payload.get("haze_pct", 0),
        resolution_m=payload.get("resolution_m", 10),
        max_cloud_pct=float(payload.get("max_cloud_pct", 35)),
    )
    return q.__dict__


@router.post("/v1/cog/registry/preview")
async def cog_registry_preview(payload: dict) -> dict:
    """Preview the canonical COG registry record without writing to DB."""
    import cloud_native_catalog as _cnc

    required = ["tenant_id", "field_id", "date", "index_type", "cog_url"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise HTTPException(status_code=422, detail={"missing": missing})
    return _cnc.cog_registry_record(
        tenant_id=str(payload["tenant_id"]),
        field_id=str(payload["field_id"]),
        date=str(payload["date"]),
        index_type=str(payload["index_type"]),
        cog_url=str(payload["cog_url"]),
        scene_id=payload.get("scene_id"),
        cloud_pct=payload.get("cloud_pct"),
        resolution_m=payload.get("resolution_m", 10),
    )
