"""PA-003 yield-map ingestion HTTP and persistence boundary.

This router is intentionally distinct from yield analysis.  It accepts actual
spatial harvest measurements, validates them through the pure parser, enforces
field ownership under tenant RLS, persists immutable PostGIS point records with
source provenance/idempotency, and exposes tenant-scoped read/query surfaces.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated
from uuid import UUID

from core.yield_intelligence import assess_yield_scope, summarize_yield_scope
from fastapi import APIRouter, Depends, HTTPException, Query

from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    _emit_domain_event,
    require_permission,
    tenant_connection,
)
from api.yield_map_ingestion import (
    PARSER_VERSION,
    ParsedYieldMap,
    YieldMapIngestionSummary,
    YieldMapIngestRequest,
    parse_yield_map,
)

router = APIRouter()

_INGESTION_SELECT = """
    ingestion_id::text AS ingestion_id, field_id, season_id, source_name,
    source_format, source_crs, source_sha256, parser_version, idempotency_key,
    record_count, min_yield_kg_ha, max_yield_kg_ha, mean_yield_kg_ha, created_at
"""


def _summary(row, *, replayed: bool = False) -> YieldMapIngestionSummary:
    return YieldMapIngestionSummary(
        ingestion_id=str(row["ingestion_id"]),
        field_id=row["field_id"],
        season_id=row["season_id"],
        source_name=row["source_name"],
        source_format=row["source_format"],
        source_crs=row["source_crs"],
        source_sha256=row["source_sha256"],
        parser_version=row["parser_version"],
        idempotency_key=row["idempotency_key"],
        record_count=int(row["record_count"]),
        min_yield_kg_ha=(
            float(row["min_yield_kg_ha"]) if row["min_yield_kg_ha"] is not None else None
        ),
        max_yield_kg_ha=(
            float(row["max_yield_kg_ha"]) if row["max_yield_kg_ha"] is not None else None
        ),
        mean_yield_kg_ha=(
            float(row["mean_yield_kg_ha"]) if row["mean_yield_kg_ha"] is not None else None
        ),
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
        replayed=replayed,
    )


def _records_json(parsed: ParsedYieldMap) -> str:
    return json.dumps(
        [record.model_dump(mode="json") for record in parsed.records],
        ensure_ascii=False,
        separators=(",", ":"),
    )


@router.post(
    "/api/v1/fields/{field_id}/yield-maps/ingestions",
    status_code=201,
    response_model=YieldMapIngestionSummary,
)
async def ingest_yield_map(
    field_id: str,
    request: YieldMapIngestRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """Persist a validated CSV/GeoJSON yield map for one authorized field.

    ``idempotency_key`` is domain-scoped and mandatory.  Replaying the same key
    with the same source digest returns the original ingestion; the same key with
    different content fails with 409.  All points must be covered by the current
    field geometry, preventing cross-field spatial contamination.
    """

    try:
        parsed = parse_yield_map(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    ingestion_id = str(uuid.uuid4())
    records_json = _records_json(parsed)
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"{user.tenant_id}:{request.idempotency_key}",
            )
            if request.season_id is not None:
                season_ok = await conn.fetchval(
                    "SELECT 1 FROM seasons WHERE season_id=$1 AND field_id=$2",
                    request.season_id,
                    field_id,
                )
                if not season_ok:
                    raise HTTPException(status_code=404, detail="الموسم غير موجود لهذا الحقل")

            existing = await conn.fetchrow(
                f"SELECT {_INGESTION_SELECT} FROM yield_map_ingestions WHERE idempotency_key=$1",
                request.idempotency_key,
            )
            if existing is not None:
                same_source = (
                    existing["field_id"] == field_id
                    and existing["source_sha256"] == parsed.source_sha256
                    and existing["source_format"] == request.source_format.value
                )
                if not same_source:
                    raise HTTPException(
                        status_code=409,
                        detail="idempotency_key مستخدم لمصدر أو حقل مختلف",
                    )
                return _summary(existing, replayed=True)

            geometry_ready = await conn.fetchval(
                "SELECT geom IS NOT NULL FROM fields WHERE field_id=$1",
                field_id,
            )
            if not geometry_ready:
                raise HTTPException(
                    status_code=422,
                    detail="هندسة الحقل مطلوبة للتحقق المكاني من خريطة الإنتاجية",
                )

            outside = await conn.fetchval(
                """
                WITH points AS (
                    SELECT longitude, latitude
                    FROM jsonb_to_recordset($2::jsonb) AS p(
                        longitude double precision,
                        latitude double precision
                    )
                )
                SELECT COUNT(*)
                  FROM points p
                  JOIN fields f ON f.field_id=$1
                 WHERE NOT ST_Covers(
                     f.geom,
                     ST_SetSRID(ST_MakePoint(p.longitude, p.latitude), 4326)
                 )
                """,
                field_id,
                records_json,
            )
            if int(outside or 0) > 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"{int(outside)} سجل إنتاجية خارج حدود الحقل",
                )

            row = await conn.fetchrow(
                f"""
                WITH inserted_ingestion AS (
                    INSERT INTO yield_map_ingestions (
                        ingestion_id, tenant_id, field_id, season_id, source_name,
                        source_format, source_crs, source_sha256, parser_version,
                        idempotency_key, metadata, record_count, min_yield_kg_ha,
                        max_yield_kg_ha, mean_yield_kg_ha, created_by
                    ) VALUES (
                        $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11::jsonb, $12, $13, $14, $15, $16
                    )
                    RETURNING *
                ), inserted_records AS (
                    INSERT INTO yield_map_records (
                        tenant_id, ingestion_id, field_id, season_id, source_record_id,
                        geom, yield_kg_ha, moisture_pct, harvested_at, attributes,
                        record_sha256
                    )
                    SELECT $2::uuid, i.ingestion_id, $3, $4, p.source_record_id,
                           ST_SetSRID(ST_MakePoint(p.longitude, p.latitude), 4326),
                           p.yield_kg_ha, p.moisture_pct, p.harvested_at,
                           COALESCE(p.attributes, '{{}}'::jsonb), p.record_sha256
                      FROM inserted_ingestion i
                      CROSS JOIN jsonb_to_recordset($17::jsonb) AS p(
                          source_record_id text,
                          longitude double precision,
                          latitude double precision,
                          yield_kg_ha double precision,
                          moisture_pct double precision,
                          harvested_at timestamptz,
                          attributes jsonb,
                          record_sha256 text
                      )
                    RETURNING record_id
                )
                SELECT {_INGESTION_SELECT} FROM inserted_ingestion
                """,
                ingestion_id,
                str(user.tenant_id),
                field_id,
                request.season_id,
                request.source_name,
                request.source_format.value,
                request.source_crs,
                parsed.source_sha256,
                PARSER_VERSION,
                request.idempotency_key,
                json.dumps(request.metadata, ensure_ascii=False, separators=(",", ":")),
                len(parsed.records),
                min(record.yield_kg_ha for record in parsed.records),
                max(record.yield_kg_ha for record in parsed.records),
                sum(record.yield_kg_ha for record in parsed.records) / len(parsed.records),
                str(user.user_id),
                records_json,
            )
            if row is None:
                raise RuntimeError("yield-map ingestion did not return a persisted row")
            await _emit_domain_event(
                conn,
                user,
                "YIELD_MAP_INGESTED",
                "yield_map_ingestion",
                ingestion_id,
                {
                    "field_id": field_id,
                    "season_id": request.season_id,
                    "source_sha256": parsed.source_sha256,
                    "record_count": len(parsed.records),
                },
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("استيراد خريطة الإنتاجية", exc) from exc
    return _summary(row)


@router.get(
    "/api/v1/fields/{field_id}/yield-maps/ingestions",
    response_model=list[YieldMapIngestionSummary],
)
async def list_yield_map_ingestions(
    field_id: str,
    season_id: str | None = Query(default=None, max_length=50),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """List immutable ingestion batches for an authorized field."""

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                f"""
                SELECT {_INGESTION_SELECT}
                  FROM yield_map_ingestions
                 WHERE field_id=$1
                   AND ($2::text IS NULL OR season_id=$2)
                 ORDER BY created_at DESC, ingestion_id DESC
                 LIMIT $3 OFFSET $4
                """,
                field_id,
                season_id,
                limit,
                offset,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("قراءة دفعات خرائط الإنتاجية", exc) from exc
    return [_summary(row) for row in rows]


@router.get("/api/v1/fields/{field_id}/yield-map-records")
async def query_yield_map_records(
    field_id: str,
    ingestion_id: UUID | None = Query(default=None),
    season_id: str | None = Query(default=None, max_length=50),
    min_yield_kg_ha: float | None = Query(default=None, gt=0),
    max_yield_kg_ha: float | None = Query(default=None, gt=0),
    bbox: str | None = Query(
        default=None,
        description="Optional WGS84 min_lon,min_lat,max_lon,max_lat bounding box",
    ),
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
    summary: bool = Query(
        False,
        description=(
            "Attach the canonical_yield_state summary for the queried scope. "
            "Reports not_evaluated when the scope spans more than one ingestion or "
            "season, or when the page is truncated."
        ),
    ),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """Query persisted yield points and return a GeoJSON FeatureCollection.

    With ``summary=true`` the response also carries the governed
    ``canonical_yield_state`` for the queried scope. It is folded into this existing
    route rather than added as a new one, so the platform domain-route budget is
    untouched (the INT-004A precedent).

    The summary is deliberately conservative: a canonical yield state is identified by
    (field, season, source_sha256), so it is only computed over exactly one ingestion of
    one season, and never over a truncated page. Averaging a page of points would
    produce a number that looks like the field's yield without being it.
    """

    if min_yield_kg_ha is not None and max_yield_kg_ha is not None:
        if min_yield_kg_ha > max_yield_kg_ha:
            raise HTTPException(status_code=422, detail="min_yield_kg_ha exceeds max_yield_kg_ha")
    bbox_values: tuple[float, float, float, float] | None = None
    if bbox:
        try:
            values = tuple(float(part.strip()) for part in bbox.split(","))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="bbox must contain four numbers") from exc
        if len(values) != 4:
            raise HTTPException(status_code=422, detail="bbox must contain four numbers")
        min_lon, min_lat, max_lon, max_lat = values
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
            raise HTTPException(status_code=422, detail="bbox coordinates are invalid")
        bbox_values = values

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                """
                SELECT r.record_id::text, r.ingestion_id::text, r.season_id,
                       r.source_record_id, ST_X(r.geom) AS longitude,
                       ST_Y(r.geom) AS latitude, r.yield_kg_ha, r.moisture_pct,
                       r.harvested_at, r.attributes, r.record_sha256
                  FROM yield_map_records r
                 WHERE r.field_id=$1
                   AND ($2::uuid IS NULL OR r.ingestion_id=$2::uuid)
                   AND ($3::text IS NULL OR r.season_id=$3)
                   AND ($4::double precision IS NULL OR r.yield_kg_ha >= $4)
                   AND ($5::double precision IS NULL OR r.yield_kg_ha <= $5)
                   AND (
                       $6::double precision IS NULL OR
                       ST_Intersects(
                           r.geom,
                           ST_MakeEnvelope($6, $7, $8, $9, 4326)
                       )
                   )
                 ORDER BY r.harvested_at DESC NULLS LAST, r.record_id
                 LIMIT $10 OFFSET $11
                """,
                field_id,
                ingestion_id,
                season_id,
                min_yield_kg_ha,
                max_yield_kg_ha,
                *(bbox_values or (None, None, None, None)),
                limit,
                offset,
            )
            yield_summary = None
            if summary:
                # Scope soundness is decided in core (pure); only the provenance
                # lookup is I/O, and it is skipped entirely for an unsound scope.
                record_rows = [dict(row) for row in rows]
                scope = assess_yield_scope(rows=record_rows, truncated=len(rows) >= limit)
                source_sha256 = (
                    await conn.fetchval(
                        "SELECT source_sha256 FROM yield_map_ingestions "
                        "WHERE ingestion_id = $1::uuid",
                        scope.ingestion_id,
                    )
                    if scope.evaluable
                    else None
                )
                yield_summary = summarize_yield_scope(
                    field_id=field_id,
                    rows=record_rows,
                    scope=scope,
                    source_sha256=source_sha256,
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("قراءة سجلات خريطة الإنتاجية", exc) from exc

    features = []
    for row in rows:
        attributes = row["attributes"]
        if isinstance(attributes, str):
            attributes = json.loads(attributes)
        features.append(
            {
                "type": "Feature",
                "id": row["record_id"],
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["longitude"]), float(row["latitude"])],
                },
                "properties": {
                    "ingestion_id": row["ingestion_id"],
                    "season_id": row["season_id"],
                    "source_record_id": row["source_record_id"],
                    "yield_kg_ha": float(row["yield_kg_ha"]),
                    "moisture_pct": (
                        float(row["moisture_pct"]) if row["moisture_pct"] is not None else None
                    ),
                    "harvested_at": (
                        row["harvested_at"].isoformat() if row["harvested_at"] else None
                    ),
                    "record_sha256": row["record_sha256"],
                    "attributes": attributes or {},
                },
            }
        )
    response = {
        "type": "FeatureCollection",
        "features": features,
        "query": {
            "field_id": field_id,
            "ingestion_id": str(ingestion_id) if ingestion_id is not None else None,
            "season_id": season_id,
            "limit": limit,
            "offset": offset,
            "returned": len(features),
        },
    }
    if yield_summary is not None:
        response["intelligence"] = yield_summary
    return response
