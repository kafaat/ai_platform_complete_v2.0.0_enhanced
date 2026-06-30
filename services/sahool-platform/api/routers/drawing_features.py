"""Drawing features CRUD — tenant-scoped map drawings.

Stores agricultural drawing outputs (field zones, pivots, prescriptions, exclusion
zones) as versioned GeoJSON payloads. This is intentionally lightweight for v38:
PostGIS topology enforcement arrives in the next hardening phase, while this
router gives the frontend a real persistence contract now.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter(tags=["drawing-features"])

DrawKind = Literal[
    "field",
    "pivot",
    "management-zone",
    "prescription-zone",
    "exclusion-zone",
    "scout-pin",
    "path",
    "measurement",
]

DrawWorkflow = Literal[
    "create-field",
    "design-pivot",
    "split-field",
    "merge-fields",
    "create-management-zone",
    "create-prescription-zone",
    "create-exclusion-zone",
    "measure-area",
    "measure-distance",
]

GeometryType = Literal["Point", "LineString", "Polygon", "MultiPolygon"]


class GeoJsonGeometry(BaseModel):
    type: GeometryType
    coordinates: Any


class DrawFeatureProperties(BaseModel):
    name: str | None = None
    crop: str | None = None
    seasonId: str | None = None
    fieldId: str | None = None
    farmId: str | None = None
    operationId: str | None = None
    sourceLayer: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    engine: str | None = None
    workflow: DrawWorkflow | None = None

    model_config = {"extra": "allow"}


class DrawMeasurements(BaseModel):
    areaHa: float | None = None
    perimeterM: float | None = None
    lengthM: float | None = None
    radiusM: float | None = None
    bearingDeg: float | None = None
    sectorStartDeg: float | None = None
    sectorEndDeg: float | None = None
    ringCount: int | None = None

    model_config = {"extra": "allow"}


class DrawFeatureIn(BaseModel):
    id: str | None = None
    kind: DrawKind
    geometry: GeoJsonGeometry
    properties: DrawFeatureProperties = Field(default_factory=DrawFeatureProperties)
    measurements: DrawMeasurements | None = None
    validation: dict[str, Any] | None = None
    version: int = 1
    draft: bool = True
    createdAt: str | None = None
    updatedAt: str | None = None

    @field_validator("id")
    @classmethod
    def _reasonable_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip() or len(value) > 96:
            raise ValueError("invalid drawing feature id")
        return value


class DrawFeaturePatch(BaseModel):
    geometry: GeoJsonGeometry | None = None
    properties: DrawFeatureProperties | None = None
    measurements: DrawMeasurements | None = None
    validation: dict[str, Any] | None = None
    draft: bool | None = None


class DrawFeatureOut(DrawFeatureIn):
    id: str
    tenantId: str
    savedBy: str | int | None = None
    deletedAt: str | None = None


class DrawFeatureListResponse(BaseModel):
    features: list[DrawFeatureOut]


class PostgisTopologyValidation(BaseModel):
    valid: bool
    postgis: bool = True
    geometryType: str | None = None
    validReason: str | None = None
    areaHa: float | None = None
    withinField: bool | None = None
    overlapCount: int = 0
    overlapAreaHa: float = 0
    issues: list[dict[str, Any]] = Field(default_factory=list)


class DrawingTopologyValidateRequest(BaseModel):
    feature: DrawFeatureIn
    excludeFeatureId: str | None = None


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS drawing_features (
    feature_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NULL,
    season_id TEXT NULL,
    kind TEXT NOT NULL,
    workflow TEXT NULL,
    geometry JSONB NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    measurements JSONB NULL,
    validation JSONB NULL,
    draft BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    saved_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL
)
"""

_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_drawing_features_tenant_field ON drawing_features(tenant_id, field_id) WHERE deleted_at IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_drawing_features_tenant_kind ON drawing_features(tenant_id, kind) WHERE deleted_at IS NULL",
]


async def _ensure_table(conn) -> None:
    await conn.execute(_CREATE_TABLE_SQL)
    for sql in _INDEX_SQL:
        await conn.execute(sql)


def _field_id_from(feature: DrawFeatureIn | DrawFeaturePatch) -> str | None:
    props = feature.properties
    return props.fieldId if props else None


def _season_id_from(feature: DrawFeatureIn | DrawFeaturePatch) -> str | None:
    props = feature.properties
    return props.seasonId if props else None


def _workflow_from(feature: DrawFeatureIn | DrawFeaturePatch) -> str | None:
    props = feature.properties
    return props.workflow if props else None


def _dump_model(value: BaseModel | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value.model_dump(mode="json", exclude_none=True), ensure_ascii=False)


def _json_value(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


def _row_to_feature(row: Any) -> DrawFeatureOut:
    props = _json_value(row["properties"], {}) or {}
    created = row["created_at"]
    updated = row["updated_at"]
    deleted = row["deleted_at"]
    return DrawFeatureOut(
        id=row["feature_id"],
        kind=row["kind"],
        geometry=_json_value(row["geometry"], {"type": "Polygon", "coordinates": []}),
        properties=props,
        measurements=_json_value(row["measurements"], None),
        validation=_json_value(row["validation"], None),
        version=row["version"],
        draft=row["draft"],
        createdAt=created.isoformat() if hasattr(created, "isoformat") else str(created),
        updatedAt=updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
        tenantId=str(row["tenant_id"]),
        savedBy=row["saved_by"],
        deletedAt=deleted.isoformat() if hasattr(deleted, "isoformat") else None,
    )


def _topology_issue(code: str, severity: str, message_ar: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "severity": severity, "message_ar": message_ar}
    payload.update(extra)
    return payload


def _requires_strict_field_containment(kind: str) -> bool:
    return kind in {"pivot", "management-zone", "prescription-zone", "exclusion-zone"}


def _requires_overlap_guard(kind: str) -> bool:
    return kind in {"management-zone", "prescription-zone", "exclusion-zone"}


def _geometry_payload(feature: DrawFeatureIn | DrawFeaturePatch) -> str | None:
    if not feature.geometry:
        return None
    return json.dumps(feature.geometry.model_dump(mode="json"), ensure_ascii=False)


def _merge_validation(
    existing: dict[str, Any] | None, topology: PostgisTopologyValidation
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing or {})
    merged["postgis"] = topology.model_dump(mode="json", exclude_none=True)
    merged["valid"] = bool(topology.valid and merged.get("valid", True))
    issues = list(merged.get("issues") or [])
    issues.extend(topology.issues)
    merged["issues"] = issues
    return merged


async def _validate_topology_postgis(
    conn,
    *,
    user: UserSchema,
    feature: DrawFeatureIn,
    field_id: str | None,
    exclude_feature_id: str | None = None,
) -> PostgisTopologyValidation:
    """Validate drawing geometry using PostGIS before persistence.

    This is the authoritative backend guard for persisted agricultural drawings.
    Client-side topology checks remain feedback only; this guard checks validity,
    geodetic area, optional containment inside the parent field, and overlap with
    existing zones for workflows where overlap is unsafe.
    """
    geometry_json = _geometry_payload(feature)
    if not geometry_json:
        return PostgisTopologyValidation(
            valid=False,
            postgis=True,
            issues=[_topology_issue("empty-geometry", "error", "الهندسة فارغة ولا يمكن حفظها.")],
        )

    row = await conn.fetchrow(
        """
        WITH input AS (
          SELECT ST_SetSRID(ST_GeomFromGeoJSON($1::text), 4326) AS geom
        ), parent_field AS (
          SELECT
            CASE
              WHEN $2::text IS NULL THEN NULL::boolean
              WHEN f.geometry IS NULL THEN NULL::boolean
              ELSE ST_Covers(
                ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(f.geometry::text), 4326)),
                ST_MakeValid((SELECT geom FROM input))
              )
            END AS within_field
          FROM fields f
          WHERE f.tenant_id = $3::uuid AND f.field_id = $2
          LIMIT 1
        ), overlaps AS (
          SELECT
            COUNT(*)::int AS overlap_count,
            COALESCE(SUM(ST_Area(ST_Intersection(
              ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(df.geometry::text), 4326)),
              ST_MakeValid((SELECT geom FROM input))
            )::geography)), 0)::float AS overlap_area_m2
          FROM drawing_features df
          WHERE df.tenant_id = $3::uuid
            AND ($2::text IS NULL OR df.field_id = $2)
            AND df.deleted_at IS NULL
            AND df.kind IN ('management-zone', 'prescription-zone', 'exclusion-zone')
            AND ($4::text IS NULL OR df.feature_id <> $4)
            AND ST_Intersects(
              ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(df.geometry::text), 4326)),
              ST_MakeValid((SELECT geom FROM input))
            )
        )
        SELECT
          ST_IsValid((SELECT geom FROM input)) AS is_valid,
          ST_IsValidReason((SELECT geom FROM input)) AS valid_reason,
          GeometryType((SELECT geom FROM input)) AS geometry_type,
          ST_Area(ST_MakeValid((SELECT geom FROM input))::geography)::float AS area_m2,
          (SELECT within_field FROM parent_field) AS within_field,
          (SELECT overlap_count FROM overlaps) AS overlap_count,
          (SELECT overlap_area_m2 FROM overlaps) AS overlap_area_m2
        """,
        geometry_json,
        field_id,
        str(user.tenant_id),
        exclude_feature_id,
    )

    issues: list[dict[str, Any]] = []
    is_valid = bool(row["is_valid"])
    valid_reason = row["valid_reason"]
    geometry_type = row["geometry_type"]
    area_ha = float(row["area_m2"] or 0) / 10000
    within_field = row["within_field"]
    overlap_count = int(row["overlap_count"] or 0)
    overlap_area_ha = float(row["overlap_area_m2"] or 0) / 10000

    if not is_valid:
        issues.append(
            _topology_issue(
                "postgis-invalid-geometry",
                "error",
                "PostGIS رفض الهندسة لأنها غير صالحة.",
                reason=valid_reason,
            )
        )
    if geometry_type not in {"POINT", "LINESTRING", "POLYGON", "MULTIPOLYGON"}:
        issues.append(
            _topology_issue(
                "postgis-unsupported-geometry",
                "error",
                "نوع الهندسة غير مدعوم في أدوات الرسم الزراعية.",
                geometryType=geometry_type,
            )
        )
    if _requires_strict_field_containment(feature.kind) and within_field is False:
        issues.append(
            _topology_issue(
                "postgis-outside-parent-field",
                "error",
                "الهندسة خارج حدود الحقل الأب ولا يمكن حفظها لهذا workflow.",
            )
        )
    if _requires_overlap_guard(feature.kind) and overlap_count > 0 and overlap_area_ha > 0.0001:
        issues.append(
            _topology_issue(
                "postgis-zone-overlap",
                "error",
                "توجد منطقة مرسومة متداخلة مع منطقة محفوظة أخرى.",
                overlapCount=overlap_count,
                overlapAreaHa=overlap_area_ha,
            )
        )

    return PostgisTopologyValidation(
        valid=not any(i["severity"] == "error" for i in issues),
        postgis=True,
        geometryType=geometry_type,
        validReason=valid_reason,
        areaHa=area_ha,
        withinField=within_field,
        overlapCount=overlap_count,
        overlapAreaHa=overlap_area_ha,
        issues=issues,
    )


async def _assert_field_owner(conn, *, user: UserSchema, field_id: str | None) -> None:
    if not field_id:
        return
    row = await conn.fetchrow(
        "SELECT 1 FROM fields WHERE tenant_id = $1::uuid AND field_id = $2 LIMIT 1",
        str(user.tenant_id),
        field_id,
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "field_not_found", "message_ar": "الحقل غير موجود أو ليس ضمن مستأجرك"},
        )


@router.get("/api/v1/fields/{field_id}/drawing-features", response_model=DrawFeatureListResponse)
async def list_field_drawing_features(
    field_id: str,
    kind: DrawKind | None = Query(default=None),
    include_drafts: bool = True,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    try:
        async with tenant_connection(user) as conn:
            await _ensure_table(conn)
            await _assert_field_owner(conn, user=user, field_id=field_id)
            rows = await conn.fetch(
                """
                SELECT * FROM drawing_features
                WHERE tenant_id = $1::uuid AND field_id = $2
                  AND deleted_at IS NULL
                  AND ($3::text IS NULL OR kind = $3)
                  AND ($4::boolean OR draft = FALSE)
                ORDER BY updated_at DESC, created_at DESC
                """,
                str(user.tenant_id),
                field_id,
                kind,
                include_drafts,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("قراءة هندسات الرسم", exc) from exc
    return DrawFeatureListResponse(features=[_row_to_feature(r) for r in rows])


@router.post("/api/v1/drawing-features/validate", response_model=PostgisTopologyValidation)
async def validate_drawing_feature_topology(
    req: DrawingTopologyValidateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    field_id = _field_id_from(req.feature)
    try:
        async with tenant_connection(user) as conn:
            await _ensure_table(conn)
            await _assert_field_owner(conn, user=user, field_id=field_id)
            return await _validate_topology_postgis(
                conn,
                user=user,
                feature=req.feature,
                field_id=field_id,
                exclude_feature_id=req.excludeFeatureId,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("تحقق PostGIS لهندسة الرسم", exc) from exc


@router.post("/api/v1/drawing-features", status_code=201, response_model=DrawFeatureOut)
async def create_drawing_feature(
    req: DrawFeatureIn,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    feature_id = req.id or f"draw_{uuid.uuid4().hex[:16]}"
    now = datetime.now(UTC)
    field_id = _field_id_from(req)
    try:
        async with tenant_connection(user) as conn:
            await _ensure_table(conn)
            await _assert_field_owner(conn, user=user, field_id=field_id)
            topology = await _validate_topology_postgis(
                conn, user=user, feature=req, field_id=field_id, exclude_feature_id=feature_id
            )
            if not topology.valid:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "drawing_topology_invalid",
                        "message_ar": "فشل تحقق PostGIS للهندسة.",
                        "validation": topology.model_dump(mode="json"),
                    },
                )
            validation_payload = _merge_validation(req.validation, topology)
            row = await conn.fetchrow(
                """
                INSERT INTO drawing_features (
                    feature_id, tenant_id, field_id, season_id, kind, workflow,
                    geometry, properties, measurements, validation, draft, version,
                    saved_by, created_at, updated_at
                ) VALUES (
                    $1, $2::uuid, $3, $4, $5, $6,
                    $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb, $11, 1,
                    $12, $13, $13
                )
                ON CONFLICT (feature_id) DO UPDATE SET
                    geometry = EXCLUDED.geometry,
                    properties = EXCLUDED.properties,
                    measurements = EXCLUDED.measurements,
                    validation = EXCLUDED.validation,
                    draft = EXCLUDED.draft,
                    version = drawing_features.version + 1,
                    updated_at = EXCLUDED.updated_at,
                    deleted_at = NULL
                RETURNING *
                """,
                feature_id,
                str(user.tenant_id),
                field_id,
                _season_id_from(req),
                req.kind,
                _workflow_from(req),
                json.dumps(req.geometry.model_dump(mode="json"), ensure_ascii=False),
                _dump_model(req.properties) or "{}",
                _dump_model(req.measurements),
                json.dumps(validation_payload, ensure_ascii=False),
                req.draft,
                str(user.user_id),
                now,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("حفظ هندسة الرسم", exc) from exc
    return _row_to_feature(row)


@router.patch("/api/v1/drawing-features/{feature_id}", response_model=DrawFeatureOut)
async def update_drawing_feature(
    feature_id: str,
    req: DrawFeaturePatch,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    try:
        async with tenant_connection(user) as conn:
            await _ensure_table(conn)
            existing = await conn.fetchrow(
                "SELECT * FROM drawing_features WHERE feature_id = $1 AND tenant_id = $2::uuid AND deleted_at IS NULL",
                feature_id,
                str(user.tenant_id),
            )
            if existing is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "drawing_feature_not_found",
                        "message_ar": "هندسة الرسم غير موجودة",
                    },
                )
            field_id = _field_id_from(req) or existing["field_id"]
            await _assert_field_owner(conn, user=user, field_id=field_id)
            existing_props = _json_value(existing["properties"], {}) or {}
            existing_measurements = _json_value(existing["measurements"], None)
            existing_validation = _json_value(existing["validation"], None)
            validation_payload = req.validation
            if req.geometry is not None:
                topology_feature = DrawFeatureIn(
                    id=feature_id,
                    kind=existing["kind"],
                    geometry=req.geometry,
                    properties=req.properties or DrawFeatureProperties(**existing_props),
                    measurements=req.measurements
                    or (
                        DrawMeasurements(**existing_measurements)
                        if isinstance(existing_measurements, dict)
                        else None
                    ),
                    validation=req.validation or existing_validation,
                    draft=req.draft if req.draft is not None else existing["draft"],
                )
                topology = await _validate_topology_postgis(
                    conn,
                    user=user,
                    feature=topology_feature,
                    field_id=field_id,
                    exclude_feature_id=feature_id,
                )
                if not topology.valid:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "drawing_topology_invalid",
                            "message_ar": "فشل تحقق PostGIS للهندسة.",
                            "validation": topology.model_dump(mode="json"),
                        },
                    )
                validation_payload = _merge_validation(
                    req.validation or existing_validation, topology
                )
            row = await conn.fetchrow(
                """
                UPDATE drawing_features SET
                    field_id = COALESCE($3, field_id),
                    season_id = COALESCE($4, season_id),
                    workflow = COALESCE($5, workflow),
                    geometry = COALESCE($6::jsonb, geometry),
                    properties = COALESCE($7::jsonb, properties),
                    measurements = COALESCE($8::jsonb, measurements),
                    validation = COALESCE($9::jsonb, validation),
                    draft = COALESCE($10, draft),
                    version = version + 1,
                    updated_at = now()
                WHERE feature_id = $1 AND tenant_id = $2::uuid AND deleted_at IS NULL
                RETURNING *
                """,
                feature_id,
                str(user.tenant_id),
                field_id,
                _season_id_from(req),
                _workflow_from(req),
                json.dumps(req.geometry.model_dump(mode="json"), ensure_ascii=False)
                if req.geometry
                else None,
                _dump_model(req.properties),
                _dump_model(req.measurements),
                json.dumps(validation_payload, ensure_ascii=False)
                if validation_payload is not None
                else None,
                req.draft,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("تعديل هندسة الرسم", exc) from exc
    return _row_to_feature(row)


@router.delete("/api/v1/drawing-features/{feature_id}")
async def delete_drawing_feature(
    feature_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    try:
        async with tenant_connection(user) as conn:
            await _ensure_table(conn)
            row = await conn.fetchrow(
                """
                UPDATE drawing_features
                SET deleted_at = now(), updated_at = now(), version = version + 1
                WHERE feature_id = $1 AND tenant_id = $2::uuid AND deleted_at IS NULL
                RETURNING feature_id
                """,
                feature_id,
                str(user.tenant_id),
            )
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "drawing_feature_not_found",
                        "message_ar": "هندسة الرسم غير موجودة",
                    },
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("حذف هندسة الرسم", exc) from exc
    return {"deleted": True, "feature_id": feature_id}
