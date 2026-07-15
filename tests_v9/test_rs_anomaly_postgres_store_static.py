"""Static guard for the RS-6 durable Postgres anomaly store (v191).

Source-scan only (no live DB) so it runs in the unit gate. It proves the
horizontal-scale store is wired correctly and safely: FORCE RLS migration,
ownership registration, sqlite default (no silent behaviour change), and a
tenant-scoped, transaction-local RLS store implementation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "v191_rs_signal_anomalies_store.sql"
OWNERSHIP = ROOT / "docs" / "architecture" / "db_ownership.yml"
PG_STORE = ROOT / "services" / "vegetation-analysis-service" / "anomaly_store_pg.py"
RUNTIME = ROOT / "services" / "vegetation-analysis-service" / "anomaly_runtime.py"


def test_migration_creates_force_rls_tenant_policy():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS signal_anomalies" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY signal_anomalies_tenant" in sql
    # Both read and write scoped to the connection's tenant.
    assert "USING (tenant_id = current_setting('app.current_tenant', true)::uuid)" in sql
    assert "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)" in sql


def test_table_registered_in_db_ownership():
    doc = yaml.safe_load(OWNERSHIP.read_text(encoding="utf-8"))
    entry = doc["tables"].get("signal_anomalies")
    assert entry is not None, "signal_anomalies must be registered in db_ownership.yml"
    assert entry["owner"] == "vegetation-analysis-service"
    assert "v191_rs_signal_anomalies_store.sql" in entry["source"]


def test_sqlite_remains_the_default_backend():
    src = RUNTIME.read_text(encoding="utf-8")
    # Default must be sqlite so the switch never silently changes behaviour.
    assert 'os.getenv("VEGETATION_ANOMALY_STORE", "sqlite")' in src
    assert 'if backend == "postgres"' in src


def test_pg_store_is_tenant_scoped_and_transaction_local():
    src = PG_STORE.read_text(encoding="utf-8")
    # Tenant is set transaction-locally (is_local=true) so pooled connections
    # cannot leak a tenant across requests.
    assert "set_config('app.current_tenant', $1, true)" in src
    # Every state read/write goes through the tenant-setting helper.
    assert src.count("await self._tenant_conn(conn") >= 4
    # Optimistic concurrency preserved (row lock + version-guarded update).
    assert "FOR UPDATE" in src
    assert "AND version = $6" in src
    assert 'raise InvalidTransition("aggregate_version_conflict")' in src
    # Reads/writes are never issued without a tenant argument.
    assert "def get(self, anomaly_ref: str, *, tenant_id: str)" in src
    assert "tenant_id: str," in src  # transition requires tenant_id (keyword-only, no default)
