"""Cloud-native GIS runtime API.

DB-backed endpoints for STAC, MosaicJSON, TileJSON, COG registry, GeoParquet export,
editing sessions and geometry locks.  This turns the Phase 4 facade into an executable
adapter over the durable tables from migrations v96/v97.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.main import Permission, UserSchema, _db_unavailable, require_permission, tenant_connection
from shared.gis.cloud_native_gis import score_scene_quality
from shared.gis.cloud_native_runtime import (
    export_records_to_geoparquet,
    mosaicjson_from_records,
    record_from_db_row,
    stac_collection,
    stac_item_from_record,
    tilejson_for_cog,
)
from shared.gis.phase5_runtime import (
    OGC_CONFORMANCE,
    STAC_CONFORMANCE,
    ai_boundary_extraction_plan,
    apply_undo_redo,
    build_scene_processing_plan,
    filter_records_for_stac,
    management_zone_summary,
    ogc_collections,
    ogc_feature_collection,
    ogc_landing_page,
    rank_scenes,
    stac_collections_response,
    stac_landing_page,
    stac_queryables,
    tile_cache_plan,
)
from shared.precision_agriculture.phase6_intelligence import (
    compose_digital_twin_snapshot,
    compute_profitability_map,
    compute_yield_stability,
    extract_boundary,
    generate_management_zones,
    generate_prescription_map,
)

router = APIRouter(prefix="/api/v1/gis/cloud-native", tags=["gis-cloud-native"])


class Phase6BoundaryExtractRequest(BaseModel):
    field_id: str
    seed_geometry: dict[str, Any] | None = None
    imagery_id: str | None = None
    imagery_bbox: list[float] | None = None
    model: str = "sam2-geosam"
    simplify_tolerance_m: float = Field(default=2.0, ge=0, le=50)
    human_review_required: bool = True


class ManagementZonesGenerateRequest(BaseModel):
    samples: list[dict[str, Any]]
    n_zones: int = Field(default=3, ge=2, le=7)
    feature_keys: list[str] | None = None
    weights: dict[str, float] | None = None


class PrescriptionGenerateRequest(BaseModel):
    zone_features: list[dict[str, Any]]
    crop: str
    prescription_type: str
    target_yield_t_ha: float | None = Field(default=None, ge=0)


class YieldStabilityRequest(BaseModel):
    history: dict[str, list[float]] | list[dict[str, Any]]


class ProfitabilityMapRequest(BaseModel):
    zones: list[dict[str, Any]]
    market_price_per_t: float = Field(gt=0)
    variable_costs_per_ha: dict[str, float] = Field(default_factory=dict)


class DigitalTwinSnapshotRequest(BaseModel):
    farm: dict[str, Any]
    fields: list[dict[str, Any]] = Field(default_factory=list)
    weather: dict[str, Any] = Field(default_factory=dict)
    soil: dict[str, Any] = Field(default_factory=dict)
    irrigation: dict[str, Any] = Field(default_factory=dict)
    equipment: list[dict[str, Any]] = Field(default_factory=list)
    economics: dict[str, Any] = Field(default_factory=dict)
    ai: dict[str, Any] = Field(default_factory=dict)


class CogRegistryRequest(BaseModel):
    field_id: str | None = None
    scene_id: str | None = None
    product_date: str
    index_type: str = Field(min_length=1)
    cog_url: str = Field(min_length=1)
    cloud_pct: float = 0
    shadow_pct: float = 0
    nodata_pct: float = 0
    haze_pct: float = 0
    resolution_m: float = 10
    bbox: list[float] | dict[str, Any] | None = None
    bands: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditingSessionRequest(BaseModel):
    field_id: str
    viewport: dict[str, Any] = Field(default_factory=dict)
    enabled_layers: list[str] = Field(default_factory=list)
    active_tool: str | None = None
    undo_stack: list[dict[str, Any]] = Field(default_factory=list)
    redo_stack: list[dict[str, Any]] = Field(default_factory=list)


class LockRequest(BaseModel):
    field_id: str
    ttl_seconds: int = Field(default=900, ge=60, le=7200)
    reason: str | None = None


class StacSearchRequest(BaseModel):
    field_id: str | None = None
    index_type: str | None = None
    min_quality: int | None = Field(default=None, ge=0, le=100)
    max_cloud: float | None = Field(default=None, ge=0, le=100)
    bbox: list[float] | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class UndoRedoRequest(BaseModel):
    field_id: str
    action: str = Field(pattern="^(push|undo|redo)$")
    event: dict[str, Any] | None = None


class BoundaryPlanRequest(BaseModel):
    field_id: str
    input_type: str = "sentinel2"
    bbox: list[float] | None = None
    model: str = "sam2-geosam"


class ManagementZoneRequest(BaseModel):
    values: list[float]
    n_zones: int = Field(default=3, ge=2, le=7)


async def _records(conn, *, field_id: str | None, index_type: str | None, limit: int):
    rows = await conn.fetch(
        """
        SELECT id, tenant_id, field_id, scene_id, product_date, index_type, cog_url,
               cloud_pct, quality_score, resolution_m, bbox, bands, metadata
          FROM raster_registry
         WHERE ($1::text IS NULL OR field_id = $1)
           AND ($2::text IS NULL OR index_type = $2)
         ORDER BY product_date DESC, quality_score DESC NULLS LAST
         LIMIT $3
        """,
        field_id,
        index_type,
        limit,
    )
    return [record_from_db_row(r) for r in rows]


@router.get("/stac")
async def stac_root(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return stac_landing_page()


@router.get("/stac/conformance")
async def stac_conformance(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return {"conformsTo": STAC_CONFORMANCE}


@router.get("/stac/queryables")
async def get_stac_queryables(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return stac_queryables()


@router.get("/stac/collections")
async def list_stac_collections(
    limit: int = Query(default=500, ge=1, le=2000),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            records = await _records(conn, field_id=None, index_type=None, limit=limit)
        return stac_collections_response(records)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.post("/stac/search")
async def stac_search_post(
    req: StacSearchRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            records = await _records(
                conn, field_id=req.field_id, index_type=req.index_type, limit=req.limit
            )
        records = filter_records_for_stac(
            records,
            field_id=req.field_id,
            index_type=req.index_type,
            min_quality=req.min_quality,
            max_cloud=req.max_cloud,
            bbox=req.bbox,
        )
        return {
            "type": "FeatureCollection",
            "features": [stac_item_from_record(r) for r in records],
            "numberMatched": len(records),
            "numberReturned": len(records),
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.get("/scene-ranking")
async def scene_ranking(
    field_id: str | None = None,
    index_type: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            records = await _records(conn, field_id=field_id, index_type=index_type, limit=limit)
        return {"ranked": rank_scenes(records), "count": len(records)}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.get("/scene-processing-plan")
async def scene_processing_plan(
    field_id: str | None = None,
    index_type: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            records = await _records(conn, field_id=field_id, index_type=index_type, limit=limit)
        return build_scene_processing_plan(records, field_id=field_id, index_type=index_type)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.get("/tile-cache-plan")
async def get_tile_cache_plan(
    field_id: str | None = None,
    index_type: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            records = await _records(conn, field_id=field_id, index_type=index_type, limit=1000)
        return tile_cache_plan(records)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.get("/ogc")
async def ogc_root(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return ogc_landing_page()


@router.get("/ogc/conformance")
async def ogc_conformance(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return {"conformsTo": OGC_CONFORMANCE}


@router.get("/ogc/collections")
async def get_ogc_collections(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return ogc_collections()


@router.get("/ogc/collections/fields/items")
async def ogc_field_items(
    limit: int = Query(default=100, ge=1, le=1000),
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                """
                SELECT field_id, name, crop, area_ha, ST_AsGeoJSON(geom)::json AS geometry
                  FROM fields
                 WHERE ($1::text IS NULL OR field_id = $1)
                 ORDER BY field_id
                 LIMIT $2
                """,
                field_id,
                limit,
            )
        return ogc_feature_collection([dict(r) for r in rows])
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.post("/ai-boundary/plan")
async def plan_ai_boundary_extraction(
    req: BoundaryPlanRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return ai_boundary_extraction_plan(
        field_id=req.field_id, input_type=req.input_type, bbox=req.bbox, model=req.model
    )


@router.post("/management-zones/summary")
async def summarize_management_zones(
    req: ManagementZoneRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return management_zone_summary(req.values, n_zones=req.n_zones)


@router.post("/editing-sessions/undo-redo")
async def editing_session_undo_redo(
    req: UndoRedoRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """
                SELECT undo_stack, redo_stack, viewport, enabled_layers, active_tool
                  FROM geometry_editing_sessions
                 WHERE tenant_id=$1::uuid AND field_id=$2 AND user_id=$3::uuid
                """,
                str(user.tenant_id),
                req.field_id,
                str(user.user_id),
            )
            current = (
                dict(row)
                if row
                else {
                    "undo_stack": [],
                    "redo_stack": [],
                    "viewport": {},
                    "enabled_layers": [],
                    "active_tool": None,
                }
            )
            updated = apply_undo_redo(current, action=req.action, event=req.event)
            saved = await conn.fetchrow(
                """
                INSERT INTO geometry_editing_sessions
                    (tenant_id, field_id, user_id, viewport, enabled_layers, active_tool, undo_stack, redo_stack, updated_at)
                VALUES ($1::uuid, $2, $3::uuid, $4::jsonb, $5::jsonb, $6, $7::jsonb, $8::jsonb, now())
                ON CONFLICT (tenant_id, field_id, user_id)
                DO UPDATE SET undo_stack = EXCLUDED.undo_stack,
                              redo_stack = EXCLUDED.redo_stack,
                              updated_at = now()
                RETURNING field_id, undo_stack, redo_stack, updated_at
                """,
                str(user.tenant_id),
                req.field_id,
                str(user.user_id),
                json.dumps(updated.get("viewport") or {}),
                json.dumps(updated.get("enabled_layers") or []),
                updated.get("active_tool"),
                json.dumps(updated["undo_stack"]),
                json.dumps(updated["redo_stack"]),
            )
        return {
            **dict(saved),
            "can_undo": bool(updated["undo_stack"]),
            "can_redo": bool(updated["redo_stack"]),
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.post("/cog-registry")
async def register_cog(
    req: CogRegistryRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    quality = score_scene_quality(
        cloud_pct=req.cloud_pct,
        shadow_pct=req.shadow_pct,
        nodata_pct=req.nodata_pct,
        haze_pct=req.haze_pct,
        resolution_m=req.resolution_m,
    )
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO raster_registry
                    (tenant_id, field_id, scene_id, product_date, index_type, cog_url,
                     cloud_pct, quality_score, resolution_m, bbox, bands, metadata)
                VALUES ($1::uuid, $2, $3, $4::date, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb, $12::jsonb)
                ON CONFLICT (tenant_id, field_id, product_date, index_type, cog_url)
                DO UPDATE SET scene_id = EXCLUDED.scene_id,
                              cloud_pct = EXCLUDED.cloud_pct,
                              quality_score = EXCLUDED.quality_score,
                              resolution_m = EXCLUDED.resolution_m,
                              bbox = EXCLUDED.bbox,
                              bands = EXCLUDED.bands,
                              metadata = raster_registry.metadata || EXCLUDED.metadata
                RETURNING id, tenant_id, field_id, scene_id, product_date, index_type, cog_url,
                          cloud_pct, quality_score, resolution_m, bbox, bands, metadata
                """,
                str(user.tenant_id),
                req.field_id,
                req.scene_id,
                req.product_date,
                req.index_type,
                req.cog_url,
                req.cloud_pct,
                quality.score,
                req.resolution_m,
                json.dumps(req.bbox),
                json.dumps(req.bands),
                json.dumps({**req.metadata, "quality": quality.__dict__}),
            )
            rec = record_from_db_row(row)
            return {
                "registered": True,
                "quality": quality.__dict__,
                "stac_item": stac_item_from_record(rec),
            }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.get("/stac/search")
async def stac_search(
    field_id: str | None = None,
    index_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            records = await _records(conn, field_id=field_id, index_type=index_type, limit=limit)
        return {
            "type": "FeatureCollection",
            "features": [stac_item_from_record(r) for r in records],
            "numberMatched": len(records),
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.get("/stac/collections/{collection_id}")
async def get_collection(
    collection_id: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    index_type = collection_id.removeprefix("sahool-")
    try:
        async with tenant_connection(user) as conn:
            records = await _records(conn, field_id=None, index_type=index_type, limit=500)
        return stac_collection(records, index_type=index_type)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.get("/mosaicjson")
async def mosaicjson(
    field_id: str | None = None,
    index_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            records = await _records(conn, field_id=field_id, index_type=index_type, limit=limit)
        return mosaicjson_from_records(
            records, name=f"sahool-{field_id or 'tenant'}-{index_type or 'all'}"
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.get("/rasters/{raster_id}/tilejson.json")
async def raster_tilejson(
    raster_id: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, field_id, scene_id, product_date, index_type, cog_url,
                       cloud_pct, quality_score, resolution_m, bbox, bands, metadata
                  FROM raster_registry
                 WHERE id::text = $1
                """,
                raster_id,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="Raster not found")
        return tilejson_for_cog(record_from_db_row(row))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.post("/editing-sessions")
async def upsert_editing_session(
    req: EditingSessionRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO geometry_editing_sessions
                    (tenant_id, field_id, user_id, viewport, enabled_layers, active_tool, undo_stack, redo_stack, updated_at)
                VALUES ($1::uuid, $2, $3::uuid, $4::jsonb, $5::jsonb, $6, $7::jsonb, $8::jsonb, now())
                ON CONFLICT (tenant_id, field_id, user_id)
                DO UPDATE SET viewport = EXCLUDED.viewport,
                              enabled_layers = EXCLUDED.enabled_layers,
                              active_tool = EXCLUDED.active_tool,
                              undo_stack = EXCLUDED.undo_stack,
                              redo_stack = EXCLUDED.redo_stack,
                              updated_at = now()
                RETURNING id, field_id, viewport, enabled_layers, active_tool, updated_at
                """,
                str(user.tenant_id),
                req.field_id,
                str(user.user_id),
                json.dumps(req.viewport),
                json.dumps(req.enabled_layers),
                req.active_tool,
                json.dumps(req.undo_stack),
                json.dumps(req.redo_stack),
            )
        return dict(row)
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.post("/locks")
async def acquire_geometry_lock(
    req: LockRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO geometry_locks (tenant_id, field_id, locked_by, locked_at, expires_at, reason)
                VALUES ($1::uuid, $2, $3::uuid, now(), now() + ($4::int || ' seconds')::interval, $5)
                ON CONFLICT (tenant_id, field_id) DO UPDATE
                    SET locked_by = EXCLUDED.locked_by,
                        locked_at = now(),
                        expires_at = EXCLUDED.expires_at,
                        reason = EXCLUDED.reason
                  WHERE geometry_locks.expires_at < now() OR geometry_locks.locked_by = EXCLUDED.locked_by
                RETURNING field_id, locked_by, locked_at, expires_at, reason
                """,
                str(user.tenant_id),
                req.field_id,
                str(user.user_id),
                req.ttl_seconds,
                req.reason,
            )
        if row is None:
            raise HTTPException(
                status_code=409, detail="Geometry is locked by another active editor"
            )
        return {"locked": True, **dict(row)}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.delete("/locks/{field_id}")
async def release_geometry_lock(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            deleted = await conn.fetchval(
                "DELETE FROM geometry_locks WHERE tenant_id=$1::uuid AND field_id=$2 AND locked_by=$3::uuid RETURNING 1",
                str(user.tenant_id),
                field_id,
                str(user.user_id),
            )
        return {"released": bool(deleted)}
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


@router.post("/geoparquet/export")
async def export_geoparquet(
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    out_dir = Path(os.getenv("GEOEXPORT_DIR", "/tmp/sahool-geoparquet")) / str(user.tenant_id)
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                """
                SELECT field_id, name, crop, area_ha, ST_AsGeoJSON(geom)::json AS geometry
                  FROM fields
                 WHERE ($1::text IS NULL OR field_id = $1)
                 ORDER BY field_id
                """,
                field_id,
            )
        payload = [dict(r) for r in rows]
        return export_records_to_geoparquet(payload, out_dir / "fields.geoparquet")
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc


# ---------------- Phase 6: Precision Agriculture Intelligence ----------------


@router.post("/phase6/boundaries/extract")
async def phase6_extract_boundary(
    req: Phase6BoundaryExtractRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        return extract_boundary(
            field_id=req.field_id,
            seed_geometry=req.seed_geometry,
            imagery_id=req.imagery_id,
            imagery_bbox=req.imagery_bbox,
            model=req.model,
            simplify_tolerance_m=req.simplify_tolerance_m,
            human_review_required=req.human_review_required,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/phase6/management-zones/generate")
async def phase6_generate_management_zones(
    req: ManagementZonesGenerateRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    try:
        return generate_management_zones(
            req.samples,
            n_zones=req.n_zones,
            feature_keys=req.feature_keys,
            weights=req.weights,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/phase6/prescriptions/generate")
async def phase6_generate_prescription_map(
    req: PrescriptionGenerateRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return generate_prescription_map(
        req.zone_features,
        crop=req.crop,
        prescription_type=req.prescription_type,
        target_yield_t_ha=req.target_yield_t_ha,
    )


@router.post("/phase6/yield-stability")
async def phase6_yield_stability(
    req: YieldStabilityRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return compute_yield_stability(req.history)


@router.post("/phase6/profitability-map")
async def phase6_profitability_map(
    req: ProfitabilityMapRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return compute_profitability_map(
        req.zones,
        market_price_per_t=req.market_price_per_t,
        variable_costs_per_ha=req.variable_costs_per_ha,
    )


@router.post("/phase6/digital-twin/snapshot")
async def phase6_digital_twin_snapshot(
    req: DigitalTwinSnapshotRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    return compose_digital_twin_snapshot(
        farm=req.farm,
        fields=req.fields,
        weather=req.weather,
        soil=req.soil,
        irrigation=req.irrigation,
        equipment=req.equipment,
        economics=req.economics,
        ai=req.ai,
    )
