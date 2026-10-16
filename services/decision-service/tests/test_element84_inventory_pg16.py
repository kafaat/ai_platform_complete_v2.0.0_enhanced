"""Real asyncpg query/RLS acceptance against the disposable native PG16 fixture.

Projection DDL follows inventory-selected column types; this is not the full
platform/PostGIS migration chain and is never a production tenant census.
"""

from pathlib import Path

import asyncpg
import pytest
from test_migration_033_pg16 import OTHER, TENANT
from test_migration_033_pg16 import database as database

from scripts.diagnostics.element84_legacy_inventory import (
    TABLES,
    InventoryRefused,
    collect_inventory,
)

FIXTURE = Path(__file__).resolve().parents[3] / (
    "certification/evidence/chatgpt_closure_nine_20261016/"
    "inventory_correlation/inventory_sql_fixture.sql"
)


@pytest.mark.asyncio
async def test_inventory_real_sql_rls_scope_and_truncation(database):
    await database.admin.execute(FIXTURE.read_text())
    for table in TABLES:
        await database.admin.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        await database.admin.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        await database.admin.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING "
            "(tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))"
        )
        await database.admin.execute(f'GRANT SELECT ON {table} TO "{database.role}"')
    for tenant, offset in [(TENANT, 0), (OTHER, 10)]:
        for i in (1, 2):
            await database.admin.execute(
                "INSERT INTO raster_assets(id,tenant_id,field_id,provenance) "
                "VALUES($1,$2::uuid,'ci-field',$3::jsonb)",
                i + offset,
                tenant,
                '{"provider":"element84"}' if i == 1 else "{}",
            )
    await database.admin.execute(
        "INSERT INTO backfill_runs VALUES(1,$1::uuid,'ci-field',7,'failed','HTTP 422 private-text')",
        TENANT,
    )
    await database.admin.execute(
        "INSERT INTO backfill_run_items "
        "(id,tenant_id,field_id,scene_id,index_name,provider,status,job_id,run_id,error) "
        "VALUES(1,$1::uuid,'ci-field','ci-scene','ndvi','element84','failed','ci-job',1,'HTTP 422 private-text')",
        TENANT,
    )
    app = await database.app_connection()
    try:
        report = await collect_inventory(app, TENANT, limit=10)
        assert report["snapshot_complete"] is True
        assert report["sources"]["raster_assets"]["row_count_lower_bound"] == 2
        assert len(report["sources"]) == 6
        assert report["sources"]["backfill_run_items"]["rows"][0]["geometry_revision"] == 7
        assert (
            report["sources"]["backfill_run_items"]["rows"][0]["http_422_evidence"]
            == "explicit_http_status"
        )
        assert "private-text" not in str(report)
        assert all(
            row["tenant_id"] == TENANT
            for source in report["sources"].values()
            for row in source["rows"]
        )
        assert not await app.fetchval("SELECT current_setting('app.current_tenant',true)")
        assert await app.fetchval("SELECT count(*) FROM raster_assets") == 0
        truncated = await collect_inventory(app, TENANT, limit=1)
        assert truncated["snapshot_complete"] is False
        assert truncated["sources"]["raster_assets"]["row_count_lower_bound"] == 2
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await app.execute("DELETE FROM raster_assets")
        # A correct predicate is insufficient when no permissive policy applies
        # to the actual inventory role: PostgreSQL then returns an empty table.
        await database.admin.execute(
            "ALTER POLICY tenant_isolation ON raster_assets TO CURRENT_USER"
        )
        with pytest.raises(InventoryRefused, match="applicable permissive"):
            await collect_inventory(app, TENANT)
        await database.admin.execute("ALTER POLICY tenant_isolation ON raster_assets TO PUBLIC")
        await database.admin.execute("DROP POLICY tenant_isolation ON raster_assets")
        await database.admin.execute(
            "CREATE POLICY tenant_isolation ON raster_assets AS RESTRICTIVE USING "
            "(tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))"
        )
        with pytest.raises(InventoryRefused, match="applicable permissive"):
            await collect_inventory(app, TENANT)
        await database.admin.execute("DROP POLICY tenant_isolation ON raster_assets")
        await database.admin.execute(
            "CREATE POLICY tenant_isolation ON raster_assets USING "
            "(tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))"
        )
        await database.admin.execute("ALTER TABLE raster_registry NO FORCE ROW LEVEL SECURITY")
        with pytest.raises(InventoryRefused, match="enforce row-level"):
            await collect_inventory(app, TENANT)
    finally:
        await app.close()
    with pytest.raises(InventoryRefused, match="privileged"):
        await collect_inventory(database.admin, TENANT)
