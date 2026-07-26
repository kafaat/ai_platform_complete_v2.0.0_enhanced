"""Static contract for PA-003 v215 yield-map persistence and route boundary."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "v215_yield_map_ingestion.sql"
ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "yield_map_ingestion.py"
PARSER = ROOT / "services" / "sahool-platform" / "api" / "yield_map_ingestion.py"


def test_v215_has_real_geospatial_persistence_provenance_and_idempotency():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS yield_map_ingestions" in sql
    assert "CREATE TABLE IF NOT EXISTS yield_map_records" in sql
    assert "geometry(Point, 4326)" in sql
    assert "UNIQUE (tenant_id, idempotency_key)" in sql
    assert "source_sha256" in sql and "record_sha256" in sql
    assert "FOREIGN KEY (tenant_id, field_id)" in sql
    assert "REFERENCES fields (tenant_id, field_id)" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert sql.count("WITH CHECK") >= 2
    assert "BEFORE UPDATE OR DELETE ON yield_map_records" in sql
    assert "trg_yield_map_validate_scope" in sql
    assert "trg_yield_map_validate_record_batch" in sql
    assert "REFERENCING NEW TABLE AS new_yield_records" in sql
    assert "NOT ST_Covers(f.geom, r.geom)" in sql
    assert "i.season_id IS DISTINCT FROM r.season_id" in sql


def test_v215_is_before_final_rls_catalog_assertion():
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    assert manifest.index("v215_yield_map_ingestion.sql") < manifest.index(
        "v206_rls_final_hardening.sql"
    )


def test_pa003_boundary_contains_full_required_chain():
    router = ROUTER.read_text(encoding="utf-8")
    parser = PARSER.read_text(encoding="utf-8")
    assert "YieldMapIngestRequest" in parser
    assert "parse_yield_map" in parser
    assert "_assert_field_in_tenant" in router
    assert "INSERT INTO yield_map_ingestions" in router
    assert "INSERT INTO yield_map_records" in router
    assert "ST_Covers" in router
    assert "idempotency_key" in router
    assert "YIELD_MAP_INGESTED" in router
    main = (ROOT / "services" / "sahool-platform" / "api" / "main.py").read_text(encoding="utf-8")
    assert (
        '"YIELD_MAP_INGESTED"'
        in main[main.index("CRITICAL_EVENT_TYPES") : main.index("async def _emit_domain_event")]
    )
    assert "@router.get" in router and "yield-map-records" in router
