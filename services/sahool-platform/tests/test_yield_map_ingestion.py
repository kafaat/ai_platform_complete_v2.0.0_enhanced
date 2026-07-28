"""PA-003 unit and HTTP-boundary tests for real yield-map ingestion."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import api.main  # noqa: F401 — initialize shared platform symbols before router import
import pytest
from api.routers.yield_map_ingestion import (
    ingest_yield_map,
    list_yield_map_ingestions,
    query_yield_map_records,
)
from api.yield_map_ingestion import (
    PARSER_VERSION,
    YieldMapColumnMapping,
    YieldMapFormat,
    YieldMapIngestRequest,
    parse_yield_map,
)
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="user-pa003",
    tenant_id="00000000-0000-0000-0000-000000000003",
    role=UserRole.OWNER,
    name_ar="PA-003 tester",
)


def _geojson_request(**overrides):
    base = {
        "source_name": "combine-2026.geojson",
        "source_format": YieldMapFormat.GEOJSON,
        "idempotency_key": "combine-2026-field-1",
        "payload": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "p-1",
                    "geometry": {"type": "Point", "coordinates": [44.20, 15.40]},
                    "properties": {
                        "yield_kg_ha": 4200,
                        "moisture_pct": 12.5,
                        "harvested_at": "2026-06-01T08:00:00Z",
                        "machine": "combine-a",
                    },
                },
                {
                    "type": "Feature",
                    "id": "p-2",
                    "geometry": {"type": "Point", "coordinates": [44.21, 15.41]},
                    "properties": {"yield_kg_ha": 5100},
                },
            ],
        },
    }
    base.update(overrides)
    return YieldMapIngestRequest(**base)


def test_geojson_parser_produces_canonical_records_and_digests():
    parsed = parse_yield_map(_geojson_request())
    assert parsed.parser_version == PARSER_VERSION
    assert len(parsed.records) == 2
    assert len(parsed.source_sha256) == 64
    assert parsed.records[0].source_record_id == "p-1"
    assert parsed.records[0].yield_kg_ha == 4200
    assert parsed.records[0].attributes == {"machine": "combine-a"}
    assert parsed.records[0].harvested_at == datetime(2026, 6, 1, 8, tzinfo=UTC)
    assert len(parsed.records[0].record_sha256) == 64


def test_parser_is_deterministic_for_same_geojson():
    first = parse_yield_map(_geojson_request())
    second = parse_yield_map(_geojson_request())
    assert first.source_sha256 == second.source_sha256
    assert [r.record_sha256 for r in first.records] == [r.record_sha256 for r in second.records]


def test_csv_parser_honors_explicit_column_mapping():
    request = YieldMapIngestRequest(
        source_name="monitor.csv",
        source_format="csv",
        idempotency_key="monitor-1",
        payload=(
            "lon,lat,yield,moisture,timestamp,row_id,variety\n"
            "44.20,15.40,4000,11.2,2026-06-01T08:00:00Z,r1,wheat-a\n"
        ),
        column_mapping=YieldMapColumnMapping(
            longitude="lon",
            latitude="lat",
            yield_kg_ha="yield",
            moisture_pct="moisture",
            harvested_at="timestamp",
            source_record_id="row_id",
        ),
    )
    parsed = parse_yield_map(request)
    assert len(parsed.records) == 1
    assert parsed.records[0].source_record_id == "r1"
    assert parsed.records[0].attributes == {"variety": "wheat-a"}


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": []},
                        "properties": {"yield_kg_ha": 1},
                    }
                ],
            },
            "geometry must be Point",
        ),
        (
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [181, 15]},
                        "properties": {"yield_kg_ha": 1},
                    }
                ],
            },
            "longitude",
        ),
        (
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [44, 15]},
                        "properties": {"yield_kg_ha": 0},
                    }
                ],
            },
            "yield_kg_ha",
        ),
    ],
)
def test_geojson_parser_rejects_invalid_measurements(payload, message):
    with pytest.raises(ValueError, match=message):
        parse_yield_map(_geojson_request(payload=payload))


def test_parser_rejects_duplicate_source_record_ids():
    request = _geojson_request()
    request.payload["features"][1]["id"] = "p-1"
    with pytest.raises(ValueError, match="duplicate source_record_id"):
        parse_yield_map(request)


class _FakeConn:
    def __init__(self, *, existing=None, outside=0, rows=None, records=None):
        self.existing = existing
        self.outside = outside
        self.rows = rows or []
        self.records = records or []
        self.fetchval_calls = []
        self.fetchrow_calls = []
        self.fetch_calls = []
        self.execute_calls = []

    async def execute(self, sql, *args):
        self.execute_calls.append((sql, args))
        if "pg_advisory_xact_lock" in sql:
            return "SELECT 1"
        raise AssertionError(f"unexpected execute SQL: {sql}")

    async def fetchval(self, sql, *args):
        self.fetchval_calls.append((sql, args))
        if "SELECT 1 FROM fields" in sql:
            return 1
        if "geom IS NOT NULL" in sql:
            return True
        if "COUNT(*)" in sql and "ST_Covers" in sql:
            return self.outside
        if "SELECT 1 FROM seasons" in sql:
            return 1
        raise AssertionError(f"unexpected fetchval SQL: {sql}")

    async def fetchrow(self, sql, *args):
        self.fetchrow_calls.append((sql, args))
        if "WHERE idempotency_key=$1" in sql:
            return self.existing
        if "INSERT INTO yield_map_ingestions" in sql:
            return self.rows[0]
        raise AssertionError(f"unexpected fetchrow SQL: {sql}")

    async def fetch(self, sql, *args):
        self.fetch_calls.append((sql, args))
        if "FROM yield_map_records" in sql:
            return self.records
        return self.rows


def _row(**overrides):
    base = {
        "ingestion_id": "10000000-0000-0000-0000-000000000001",
        "field_id": "field-1",
        "season_id": None,
        "source_name": "combine-2026.geojson",
        "source_format": "geojson",
        "source_crs": "EPSG:4326",
        "source_sha256": parse_yield_map(_geojson_request()).source_sha256,
        "parser_version": PARSER_VERSION,
        "idempotency_key": "combine-2026-field-1",
        "record_count": 2,
        "min_yield_kg_ha": 4200,
        "max_yield_kg_ha": 5100,
        "mean_yield_kg_ha": 4650,
        "created_at": datetime(2026, 6, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return base


def _patch_connection(monkeypatch, conn):
    @asynccontextmanager
    async def _tenant_connection(user):
        assert user.tenant_id == _USER.tenant_id
        yield conn

    async def _event(*args, **kwargs):
        return None

    monkeypatch.setattr("api.routers.yield_map_ingestion.tenant_connection", _tenant_connection)
    monkeypatch.setattr("api.routers.yield_map_ingestion._emit_domain_event", _event)


async def test_ingest_endpoint_authorizes_validates_persists_and_returns_summary(monkeypatch):
    conn = _FakeConn(rows=[_row()])
    _patch_connection(monkeypatch, conn)
    result = await ingest_yield_map("field-1", _geojson_request(), user=_USER)
    assert result.record_count == 2
    assert result.mean_yield_kg_ha == 4650
    assert "pg_advisory_xact_lock" in conn.execute_calls[0][0]
    assert result.replayed is False
    insert_sql, insert_args = conn.fetchrow_calls[-1]
    assert "INSERT INTO yield_map_records" in insert_sql
    assert "ST_MakePoint" in insert_sql
    assert insert_args[1] == str(_USER.tenant_id)
    assert insert_args[11] == 2  # persisted record_count


async def test_ingest_endpoint_replays_same_idempotency_key_without_reinsert(monkeypatch):
    conn = _FakeConn(existing=_row())
    _patch_connection(monkeypatch, conn)
    result = await ingest_yield_map("field-1", _geojson_request(), user=_USER)
    assert result.replayed is True
    assert len(conn.fetchrow_calls) == 1


async def test_ingest_endpoint_rejects_idempotency_key_with_different_source(monkeypatch):
    conn = _FakeConn(existing=_row(source_sha256="f" * 64))
    _patch_connection(monkeypatch, conn)
    with pytest.raises(HTTPException) as error:
        await ingest_yield_map("field-1", _geojson_request(), user=_USER)
    assert error.value.status_code == 409


async def test_ingest_endpoint_rejects_points_outside_field(monkeypatch):
    conn = _FakeConn(outside=1)
    _patch_connection(monkeypatch, conn)
    with pytest.raises(HTTPException) as error:
        await ingest_yield_map("field-1", _geojson_request(), user=_USER)
    assert error.value.status_code == 422
    assert "خارج حدود الحقل" in error.value.detail


async def test_list_endpoint_returns_tenant_scoped_summaries(monkeypatch):
    conn = _FakeConn(rows=[_row()])
    _patch_connection(monkeypatch, conn)
    result = await list_yield_map_ingestions(
        "field-1", season_id=None, limit=20, offset=0, user=_USER
    )
    assert len(result) == 1
    assert result[0].ingestion_id == _row()["ingestion_id"]
    assert "WHERE field_id=$1" in conn.fetch_calls[0][0]


async def test_query_endpoint_returns_geojson_feature_collection(monkeypatch):
    conn = _FakeConn(
        records=[
            {
                "record_id": "20000000-0000-0000-0000-000000000001",
                "ingestion_id": _row()["ingestion_id"],
                "season_id": "season-1",
                "source_record_id": "p-1",
                "longitude": 44.2,
                "latitude": 15.4,
                "yield_kg_ha": 4200,
                "moisture_pct": 12.5,
                "harvested_at": datetime(2026, 6, 1, tzinfo=UTC),
                "attributes": {"machine": "combine-a"},
                "record_sha256": "a" * 64,
            }
        ]
    )
    _patch_connection(monkeypatch, conn)
    result = await query_yield_map_records(
        "field-1",
        ingestion_id=None,
        season_id=None,
        min_yield_kg_ha=None,
        max_yield_kg_ha=None,
        bbox="44,15,45,16",
        limit=100,
        offset=0,
        # Called directly, so FastAPI never resolves the parameter defaults and an
        # unpassed `summary` would arrive as the truthy Query(False) object itself.
        summary=False,
        user=_USER,
    )
    assert result["type"] == "FeatureCollection"
    assert result["features"][0]["geometry"]["coordinates"] == [44.2, 15.4]
    assert result["features"][0]["properties"]["yield_kg_ha"] == 4200
    assert result["query"]["returned"] == 1
    # The summary is opt-in: the default response shape carries no extra key.
    assert "intelligence" not in result


async def test_query_endpoint_rejects_invalid_bbox():
    with pytest.raises(HTTPException) as error:
        await query_yield_map_records(
            "field-1",
            ingestion_id=None,
            season_id=None,
            min_yield_kg_ha=None,
            max_yield_kg_ha=None,
            bbox="44,15,43,16",
            limit=100,
            offset=0,
            summary=False,
            user=_USER,
        )
    assert error.value.status_code == 422


async def test_ingest_endpoint_propagates_tenant_field_authorization_failure(monkeypatch):
    conn = _FakeConn(rows=[_row()])
    _patch_connection(monkeypatch, conn)

    async def _deny_field(_conn, _field_id):
        raise HTTPException(status_code=404, detail="الحقل غير موجود")

    monkeypatch.setattr("api.routers.yield_map_ingestion._assert_field_in_tenant", _deny_field)
    with pytest.raises(HTTPException) as error:
        await ingest_yield_map("field-other-tenant", _geojson_request(), user=_USER)
    assert error.value.status_code == 404
    assert conn.fetchrow_calls == []


def test_parser_rejects_payload_type_that_does_not_match_declared_format():
    with pytest.raises(ValueError, match="CSV payload must be text"):
        parse_yield_map(_geojson_request(source_format=YieldMapFormat.CSV))


def test_yield_map_routes_are_registered():
    from api.main import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/v1/fields/{field_id}/yield-maps/ingestions" in paths
    assert "/api/v1/fields/{field_id}/yield-map-records" in paths
