from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import raster_batch_job_store as store

# جذر المستودع مثبَّت على __file__ كي تعمل الفحوص الساكنة من أيّ cwd (بوّابة raster
# تُشغّل pytest من داخل services/raster-service، والمسارات أدناه جذر-مستودعيّة).
_ROOT = Path(__file__).resolve().parents[2]


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _Conn:
    def __init__(self, row=None, execute_result="UPDATE 1"):
        self.row = row or {}
        self.execute_result = execute_result
        self.calls = []
        self.closed = False

    def transaction(self):
        return _Tx()

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return self.execute_result

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return self.row

    async def close(self):
        self.closed = True


def test_v154_replaces_underspecified_unique_index():
    sql = (_ROOT / "migrations/v154_raster_product_identity_batch_leases.sql").read_text()
    assert "DROP INDEX IF EXISTS uq_raster_assets_product" in sql
    assert "uq_raster_assets_product_identity" in sql
    for column in (
        "algorithm_version",
        "qa_mask_version",
        "field_geometry_hash",
        "product_identity_key",
    ):
        assert column in sql
    assert "CREATE TABLE IF NOT EXISTS raster_batch_jobs" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql


def test_db_writer_conflicts_on_full_product_identity():
    source = (_ROOT / "services/raster-service/db_persist.py").read_text()
    assert "ON CONFLICT (product_identity_key)" in source
    assert "ON CONFLICT (tenant_id, field_id, index_name, acquisition_date, scene_id)" not in source


def test_durable_claim_returns_database_lease_token(monkeypatch):
    row = {
        "job_id": "batch_1",
        "status": "processing",
        "lease_owner": "w1",
        "lease_token": "tok",
        "acquired": True,
        "recovered": False,
    }
    conn = _Conn(row=row)

    async def connect():
        return conn

    monkeypatch.setattr(store, "_connect", connect)
    req = SimpleNamespace(model_dump=lambda mode="json": {"tenant_id": "t"})
    result = asyncio.run(
        store.claim_or_recover(
            claim_key="rib_x",
            job_id="batch_1",
            tenant_id="00000000-0000-0000-0000-000000000001",
            field_id="fld_1",
            req=req,
            worker_id="w1",
        )
    )
    assert result.available and result.acquired
    assert result.lease_token == "tok"
    fetch_sql, fetch_args = conn.calls[1]
    assert "ON CONFLICT (claim_key)" in fetch_sql
    assert "lease_token=$8" in fetch_sql
    assert len(fetch_args) == 8


def test_terminal_write_requires_current_lease_token(monkeypatch):
    conn = _Conn(execute_result="UPDATE 1")

    async def connect():
        return conn

    monkeypatch.setattr(store, "_connect", connect)
    ok = asyncio.run(
        store.finish(
            claim_key="rib_x",
            tenant_id="00000000-0000-0000-0000-000000000001",
            lease_token="tok-current",
            status="completed",
            result_payload={"ok": True},
            worker_id="w1",
        )
    )
    assert ok
    update_sql, args = conn.calls[1]
    assert "lease_token=$6" in update_sql
    assert args[-1] == "tok-current"


def test_product_identity_is_written_by_persistence_adapter():
    source = (_ROOT / "services/raster-service/raster_asset_persistence.py").read_text()
    assert "ProductIdentity(" in source
    assert "product_identity_key=_product_identity.key()" in source
    assert "algorithm_version=raster_quality.ALGORITHM_VERSION" in source
    assert "field_geometry_hash=_field_geometry_hash" in source


def test_lease_token_is_not_persisted_in_public_job_payload():
    source = (_ROOT / "services/raster-service/routers/processing.py").read_text()
    assert '"lease_token": lease_token' not in source
    assert "raster_batch_runtime_leases.set_token(job_id, lease_token)" in source
