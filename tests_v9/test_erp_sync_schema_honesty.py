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

الراوتران الحقيقيّان (routers/sync.py, routers/health.py) و``erp_sync_schema_status``/``run_sync_job``
الحقيقيّة. بلا قاعدة مزيّفة (``FAKE-CONNECTION-ENFORCES-NOTHING-01``): المجمّع حارسٌ معتم
(``object()``) لا يُجيب أيّ استعلام، والمُرقَّع درجةٌ فوق الاستعلام — ``absent_tables`` (سؤال
``to_regclass``: يُقاس ما سُئل عنه ويُجاب من مجموعة جداول معلومة) و``ping_database`` و
``log_sync_record`` (يُسجَّل ما كُتِب) — ومزوّد ERP سليم.
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


class _Schema:
    """ما في القاعدة من جداول — يُجيب الدرزات فوق الاستعلام ويُسجِّل ما سُئل عنه وما كُتِب."""

    def __init__(self, tables: set[str]):
        self.tables = set(tables)
        self.asked: list[list[str]] = []
        self.sync_log: list[tuple] = []

    async def absent_tables(self, pool, tables):
        assert pool is DB, "the schema probe must run on the bridge's own pool"
        self.asked.append(list(tables))
        return sorted(t for t in tables if t not in self.tables)

    async def ping_database(self, pool):
        assert pool is DB

    async def log_sync_record(self, *row):
        if "odoo_sync_log" not in self.tables:
            raise RuntimeError("relation odoo_sync_log does not exist")
        self.sync_log.append(row)


DB = object()  # مجمّع الجسر: مُعتِم — كلّ ما يصل القاعدة يمرّ بالدرزات أعلاه


def _use(monkeypatch, rt, tables: set[str] | None) -> _Schema | None:
    """يربط الجسر بقاعدة جداولُها ``tables`` — أو ``None``: لا قاعدة (لا DATABASE_URL)."""
    if tables is None:
        monkeypatch.setattr(rt, "_pool", None)
        return None
    schema = _Schema(tables)
    monkeypatch.setattr(rt, "_pool", DB)
    monkeypatch.setattr(rt, "absent_tables", schema.absent_tables)
    monkeypatch.setattr(rt, "ping_database", schema.ping_database)
    monkeypatch.setattr(rt, "log_sync_record", schema.log_sync_record)
    return schema


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
    schema = _use(monkeypatch, rt, MIGRATED_TODAY)
    calls = _record_calls(monkeypatch, main, rt)

    r = client.post("/v1/sync", json={"entity": "all"})
    # السؤال يشمل كلّ جدول تكتبه المزامنة لا الأساسيّين وحدهما.
    assert set(schema.asked[-1]) == FULL_SCHEMA

    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "erp_schema_missing"
    assert {"inventory_stock", "field_cost_ledger"} <= set(detail["missing_tables"])
    assert calls == [], "nothing may be queued for a run that cannot succeed"


def test_sync_entity_scoped_schema_check(bridge, monkeypatch):
    """costs only needs field_cost_ledger (+ core): other missing tables don't block it."""
    main, rt, client = bridge
    _use(monkeypatch, rt, MIGRATED_TODAY | {"field_cost_ledger"})
    _record_calls(monkeypatch, main, rt)
    assert client.post("/v1/sync", json={"entity": "costs"}).status_code == 200
    r = client.post("/v1/sync", json={"entity": "products"})
    assert r.status_code == 503
    assert r.json()["detail"]["missing_tables"] == ["inventory_stock"]


@pytest.mark.parametrize("entity", ["procurement", "all"])
def test_market_requests_do_not_satisfy_odoo_procurement_schema(bridge, monkeypatch, entity):
    main, rt, client = bridge
    missing_source = {"procurement_orders", "procurement_order_items"}
    market = {"market_procurement_orders", "market_procurement_items"}
    _use(monkeypatch, rt, (FULL_SCHEMA - missing_source) | market)
    monkeypatch.setattr(_HealthyProvider, "name", "odoo")

    async def unexpected_probe(self):
        pytest.fail("schema rejection must precede contact with Odoo")

    monkeypatch.setattr(_HealthyProvider, "health", unexpected_probe)
    calls = _record_calls(monkeypatch, main, rt)
    response = client.post("/v1/sync", json={"entity": entity})
    assert response.status_code == 503
    reason = response.json()["detail"]
    assert reason["error"] == "erp_schema_missing"
    assert set(reason["missing_tables"]) == missing_source
    assert "price ceilings" in reason["detail"]
    assert not calls


IMPORT_STEPS = ["products", "suppliers", "warehouses"]
ODOO_EXPORT_STEPS = ["procurement", "costs"]


@pytest.mark.parametrize(
    "provider,direction,expected",
    [
        ("odoo", "odoo_to_sahool", IMPORT_STEPS),
        ("odoo", "sahool_to_odoo", ODOO_EXPORT_STEPS),
        ("odoo", "bidirectional", IMPORT_STEPS + ODOO_EXPORT_STEPS),
        ("odoo", None, IMPORT_STEPS + ODOO_EXPORT_STEPS),
        ("erpnext", "odoo_to_sahool", IMPORT_STEPS),
        ("erpnext", "sahool_to_odoo", ["costs"]),
        ("erpnext", "bidirectional", IMPORT_STEPS + ["costs"]),
    ],
)
def test_manual_sync_queues_only_the_requested_direction(
    bridge, monkeypatch, provider, direction, expected
):
    main, rt, client = bridge
    monkeypatch.setattr(_HealthyProvider, "name", provider)
    tables = MIGRATED_TODAY.union(*(rt.ERP_SYNC_ENTITY_TABLES[step] for step in expected))
    _use(monkeypatch, rt, tables)
    calls = _record_calls(monkeypatch, main, rt)

    request = {"entity": "all"}
    if direction is not None:
        request["direction"] = direction
    response = client.post("/v1/sync", json=request)
    assert response.status_code == 200, response.text
    assert response.json()["steps"] == expected
    assert response.json()["direction"] == (direction or "bidirectional")
    functions = {
        "products": "sync_products",
        "suppliers": "sync_suppliers",
        "warehouses": "sync_warehouses",
        "procurement": "sync_procurement_orders_to_odoo",
        "costs": "sync_field_costs_to_odoo",
    }
    assert calls == [functions[step] for step in expected]


@pytest.mark.parametrize(
    "entity,direction",
    [(step, "sahool_to_odoo") for step in IMPORT_STEPS]
    + [(step, "odoo_to_sahool") for step in ODOO_EXPORT_STEPS],
)
def test_incompatible_manual_direction_rejected_before_io(bridge, monkeypatch, entity, direction):
    main, rt, client = bridge
    schema = _use(monkeypatch, rt, FULL_SCHEMA)
    monkeypatch.setattr(_HealthyProvider, "name", "odoo")

    async def unexpected(*args, **kwargs):
        pytest.fail("incompatible direction reached a provider probe or a sync job")

    monkeypatch.setattr(_HealthyProvider, "health", unexpected)
    monkeypatch.setattr(main, "run_sync_job", unexpected)
    response = client.post("/v1/sync", json={"entity": entity, "direction": direction})
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "error": "erp_sync_direction_unsupported",
        "entity": entity,
        "direction": direction,
    }
    assert schema.asked == []


def test_procurement_export_still_requires_odoo_provider(bridge, monkeypatch):
    _, rt, client = bridge
    schema = _use(monkeypatch, rt, FULL_SCHEMA)
    response = client.post(
        "/v1/sync", json={"entity": "procurement", "direction": "sahool_to_odoo"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "procurement_sync_requires_odoo_provider"
    assert schema.asked == []


def test_sync_without_database_is_not_queued(bridge, monkeypatch):
    main, rt, client = bridge
    _use(monkeypatch, rt, None)
    r = client.post("/v1/sync", json={"entity": "products"})
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "erp_sync_database_unavailable"


def test_accepted_run_has_id_and_step_failures_are_recorded_not_silent(bridge, monkeypatch, caplog):
    main, rt, client = bridge
    schema = _use(monkeypatch, rt, FULL_SCHEMA)
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
    assert any(run_id in str(row) and "failed" in row for row in schema.sync_log), schema.sync_log


def test_readyz_reports_schema_missing_instead_of_constant_true(bridge, monkeypatch):
    _, rt, client = bridge
    _use(monkeypatch, rt, MIGRATED_TODAY)
    r = client.get("/readyz")
    assert r.status_code == 503, r.text
    db = r.json()["detail"]["database"]
    assert db["schema_ready"] is False
    assert db["reason"] == "erp_schema_missing"
    assert "procurement_orders" in db["missing_tables"]
    assert client.get("/healthz").status_code == 200  # الحياة مستقلّة


def test_readyz_ready_when_schema_present(bridge, monkeypatch):
    _, rt, client = bridge
    _use(monkeypatch, rt, FULL_SCHEMA)
    r = client.get("/readyz")
    assert r.status_code == 200, r.text
    assert r.json()["database"]["schema_ready"] is True


def test_run_sync_job_isolates_steps_and_skips_missing_schema(bridge, monkeypatch):
    _, rt, _ = bridge
    _use(monkeypatch, rt, MIGRATED_TODAY | {"field_cost_ledger", "suppliers"})
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
