"""R4 (تدقيق 2026-11-01): مزامنة ERP لا تقول «queued» لتشغيلٍ سيفشل حتماً.

``erp_runtime`` يكتب/يقرأ ``inventory_stock`` و``procurement_orders`` و``field_cost_ledger``
(وغيرها) التي لا تُنشئها أيّ هجرة في المستودع. قبل الإصلاح: ``POST /v1/sync`` يردّ 200
«queued» ثمّ يفشل كلّ تشغيل بـUndefinedTableError في مهمّة خلفيّة بلا أثر، و``/readyz``
يُعلن ``schema_ready: true`` ثابتاً بلا فحص.

بعد الإصلاح:
  (أ) ``/v1/sync`` ⇒ 503 ``erp_schema_missing`` (بأسماء الجداول) ولا شيء يُضاف للطابور.
  (ب) ``/readyz`` ⇒ 503 ``erp_schema_missing`` حين قاعدة البيانات متاحة لكنّ الجداول غائبة.
  (ج) التشغيل المقبول يحمل ``run_id``؛ فشل أيّ خطوة يُسجَّل ERROR بـrun_id وفي odoo_sync_log،
      ولا يُسقط بقيّة الخطوات.

الراوتران الحقيقيّان (routers/sync.py, routers/health.py)؛ المُستبدَل: مجمّع اتّصال مزيّف
يُجيب ``to_regclass`` من مجموعة جداول معلومة، ومزوّد ERP سليم.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="integration job installs minimal deps (no fastapi)")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tests_v9 import service_module  # noqa: E402

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services/odoo-bridge"

# ما تُنشئه الهجرات فعلاً اليوم (migrations/v9_odoo_bridge.sql) — لا جداول البيانات.
MIGRATED_TODAY = {"odoo_sync_state", "odoo_sync_log"}
FULL_SCHEMA = MIGRATED_TODAY | {
    "inventory_stock",
    "suppliers",
    "inventory_locations",
    "procurement_orders",
    "procurement_order_items",
    "field_cost_ledger",
}


class _Conn:
    def __init__(self, tables: set[str], log: list):
        self.tables = tables
        self.log = log

    async def fetch(self, sql, *args):
        assert "to_regclass" in sql
        return [{"table_name": t, "present": t in self.tables} for t in args[0]]

    async def fetchval(self, sql, *args):
        return 1

    async def execute(self, sql, *args):
        if "INSERT INTO odoo_sync_log" in sql:
            if "odoo_sync_log" not in self.tables:
                raise RuntimeError("relation odoo_sync_log does not exist")
            self.log.append(args)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, tables: set[str]):
        self.tables = set(tables)
        self.sync_log: list = []

    def acquire(self):
        return _Conn(self.tables, self.sync_log)


class _HealthyProvider:
    name = "erpnext"
    odoo = None

    async def health(self):
        return {"status": "connected"}


@pytest.fixture
def bridge(monkeypatch):
    for var in ("ERPNEXT_URL", "ERPNEXT_API_KEY", "ERPNEXT_API_SECRET", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    service_module.purge_generic_modules()
    main = service_module.load_service_main(
        str(SERVICE), required_attrs=("app", "get_active_erp_provider", "OdooClient")
    )
    sync = importlib.import_module("routers.sync")
    health = importlib.import_module("routers.health")
    rt = health._erp_rt
    monkeypatch.setattr(rt, "_odoo", None)
    monkeypatch.setattr(main, "get_active_erp_provider", lambda: _HealthyProvider())
    monkeypatch.setattr(rt, "get_active_erp_provider", lambda: _HealthyProvider())
    app = FastAPI()
    app.include_router(sync.router)
    app.include_router(health.router)
    app.dependency_overrides[main.require_auth] = lambda: {"sub": "test"}
    yield main, rt, TestClient(app)
    service_module.purge_generic_modules()


def _record_calls(monkeypatch, main, rt, *, fail: set[str] = frozenset()):
    calls: list[str] = []

    def _fake(name):
        async def _run():
            calls.append(name)
            if name in fail:
                raise RuntimeError(f"{name} exploded")

        return _run

    for name in (
        "sync_products",
        "sync_suppliers",
        "sync_warehouses",
        "sync_procurement_orders_to_odoo",
        "sync_field_costs_to_odoo",
    ):
        monkeypatch.setattr(main, name, _fake(name))
        monkeypatch.setattr(rt, name, _fake(name))
    return calls


def test_sync_rejects_with_503_when_erp_tables_were_never_migrated(bridge, monkeypatch):
    main, rt, client = bridge
    monkeypatch.setattr(rt, "_pool", _Pool(MIGRATED_TODAY))
    calls = _record_calls(monkeypatch, main, rt)

    r = client.post("/v1/sync", json={"entity": "all"})

    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "erp_schema_missing"
    assert {"inventory_stock", "field_cost_ledger"} <= set(detail["missing_tables"])
    assert calls == [], "nothing may be queued for a run that cannot succeed"


def test_sync_entity_scoped_schema_check(bridge, monkeypatch):
    """costs only needs field_cost_ledger (+ core): other missing tables don't block it."""
    main, rt, client = bridge
    monkeypatch.setattr(rt, "_pool", _Pool(MIGRATED_TODAY | {"field_cost_ledger"}))
    _record_calls(monkeypatch, main, rt)
    assert client.post("/v1/sync", json={"entity": "costs"}).status_code == 200
    r = client.post("/v1/sync", json={"entity": "products"})
    assert r.status_code == 503
    assert r.json()["detail"]["missing_tables"] == ["inventory_stock"]


def test_sync_without_database_is_not_queued(bridge, monkeypatch):
    main, rt, client = bridge
    monkeypatch.setattr(rt, "_pool", None)
    r = client.post("/v1/sync", json={"entity": "products"})
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "erp_sync_database_unavailable"


def test_accepted_run_has_id_and_step_failures_are_recorded_not_silent(bridge, monkeypatch, caplog):
    main, rt, client = bridge
    pool = _Pool(FULL_SCHEMA)
    monkeypatch.setattr(rt, "_pool", pool)
    calls = _record_calls(monkeypatch, main, rt, fail={"sync_products"})

    with caplog.at_level(logging.ERROR):
        r = client.post("/v1/sync", json={"entity": "all"})

    assert r.status_code == 200, r.text
    body = r.json()
    run_id = body["run_id"]
    assert body["status"] == "queued" and run_id
    # فشل products لا يُسقط بقيّة الخطوات (المزوّد ليس odoo ⇒ لا procurement).
    assert calls == [
        "sync_products",
        "sync_suppliers",
        "sync_warehouses",
        "sync_field_costs_to_odoo",
    ]
    errors = [rec.getMessage() for rec in caplog.records if rec.levelno >= logging.ERROR]
    assert any(run_id in m and "products" in m for m in errors), errors
    assert any(run_id in str(row) and "failed" in row for row in pool.sync_log), pool.sync_log


def test_readyz_reports_schema_missing_instead_of_constant_true(bridge, monkeypatch):
    _, rt, client = bridge
    monkeypatch.setattr(rt, "_pool", _Pool(MIGRATED_TODAY))
    r = client.get("/readyz")
    assert r.status_code == 503, r.text
    db = r.json()["detail"]["database"]
    assert db["schema_ready"] is False
    assert db["reason"] == "erp_schema_missing"
    assert "procurement_orders" in db["missing_tables"]
    assert client.get("/healthz").status_code == 200  # الحياة مستقلّة


def test_readyz_ready_when_schema_present(bridge, monkeypatch):
    _, rt, client = bridge
    monkeypatch.setattr(rt, "_pool", _Pool(FULL_SCHEMA))
    r = client.get("/readyz")
    assert r.status_code == 200, r.text
    assert r.json()["database"]["schema_ready"] is True


def test_run_sync_job_isolates_steps_and_skips_missing_schema(bridge, monkeypatch):
    _, rt, _ = bridge
    monkeypatch.setattr(rt, "_pool", _Pool(MIGRATED_TODAY | {"field_cost_ledger", "suppliers"}))
    ran: list[str] = []

    async def ok(name="x"):
        ran.append(name)

    async def boom():
        raise ValueError("bad row")

    result = asyncio.run(
        rt.run_sync_job(
            "run-1",
            [
                ("products", lambda: ok("products")),  # inventory_stock غائب ⇒ لا يُنفَّذ
                ("suppliers", boom),
                ("costs", lambda: ok("costs")),
            ],
            trigger="test",
        )
    )
    assert ran == ["costs"]
    assert result["status"] == "partial"
    assert result["steps"]["products"]["error"] == "erp_schema_missing"
    assert result["steps"]["suppliers"] == {"status": "failed", "error": "ValueError"}
    assert result["steps"]["costs"] == {"status": "succeeded"}
