"""ERP reads must not turn outages into empty-success or advance a cursor."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1] / "services/odoo-bridge"


def load(name):
    spec = importlib.util.spec_from_file_location(f"review_{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Connection:
    def __init__(self):
        self.marker = datetime(2026, 9, 1, tzinfo=UTC)
        self.writes = []
        self.inside_transaction = False

    def transaction(self):
        connection = self

        class Transaction:
            async def __aenter__(self):
                self.before = connection.marker, list(connection.writes)
                connection.inside_transaction = True

            async def __aexit__(self, kind, value, traceback):
                if kind:
                    connection.marker, connection.writes = self.before
                connection.inside_transaction = False

        return Transaction()

    async def fetchrow(self, sql, *args):
        assert self.inside_transaction
        return {"last_sync_at": self.marker}

    async def execute(self, sql, *args):
        assert self.inside_transaction
        if "INSERT INTO odoo_sync_state" in sql:
            self.marker = args[2]
        else:
            self.writes.append((sql, args))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize("entity", ["products", "suppliers"])
async def test_real_provider_outage_rolls_back_cursor(entity, monkeypatch):
    provider_mod, runtime = load("erp_provider"), load("erp_runtime")
    provider = provider_mod.ERPNextProvider("https://erp.example.test", "synthetic", "synthetic")
    provider._client = SimpleNamespace(get=AsyncMock(side_effect=RuntimeError("outage")))
    conn = Connection()
    monkeypatch.setattr(runtime, "get_active_erp_provider", lambda: provider)
    monkeypatch.setattr(
        runtime, "get_pool", AsyncMock(return_value=SimpleNamespace(acquire=lambda: conn))
    )
    log = AsyncMock()
    monkeypatch.setattr(runtime, "log_sync_record", log)
    with pytest.raises(provider_mod.ERPReadUnavailable):
        await getattr(runtime, f"sync_{entity}")()
    assert conn.marker == datetime(2026, 9, 1, tzinfo=UTC)
    assert conn.writes == []
    log.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [{}, {"data": None}, {"data": {}}, {"data": [3]}])
async def test_malformed_provider_body_is_not_empty_success(response):
    mod = load("erp_provider")
    provider = mod.ERPNextProvider("https://erp.example.test", "synthetic", "synthetic")
    provider._client = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(raise_for_status=lambda: None, json=lambda: response)
        )
    )
    with pytest.raises(mod.ERPReadUnavailable):
        await provider.list_products()


@pytest.mark.asyncio
async def test_successful_empty_batch_uses_start_cursor_and_inclusive_filter(monkeypatch):
    mod, runtime = load("erp_provider"), load("erp_runtime")
    provider = mod.ERPNextProvider("https://erp.example.test", "synthetic", "synthetic")
    conn = Connection()
    monkeypatch.setattr(runtime, "get_active_erp_provider", lambda: provider)
    monkeypatch.setattr(
        runtime, "get_pool", AsyncMock(return_value=SimpleNamespace(acquire=lambda: conn))
    )
    monkeypatch.setattr(runtime, "log_sync_record", AsyncMock())
    with freeze_time("2026-09-13T10:00:00Z") as clock:
        monkeypatch.setattr(runtime, "datetime", datetime)

        async def fetch(*args, **kwargs):
            import json

            assert json.loads(kwargs["params"]["filters"])[0][1] == ">="
            clock.tick(90)
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": []})

        provider._client = SimpleNamespace(get=fetch)
        await runtime.sync_products()
    assert conn.marker == datetime(2026, 9, 13, 10, tzinfo=UTC)


@pytest.mark.asyncio
async def test_row_write_failure_preserves_cursor_and_rolls_back(monkeypatch):
    runtime = load("erp_runtime")
    conn = Connection()
    provider = SimpleNamespace(
        name="erpnext",
        list_products=AsyncMock(return_value=[{"external_id": "item-1", "cost": "not-a-number"}]),
    )
    monkeypatch.setattr(runtime, "get_active_erp_provider", lambda: provider)
    monkeypatch.setattr(
        runtime, "get_pool", AsyncMock(return_value=SimpleNamespace(acquire=lambda: conn))
    )
    with pytest.raises(ValueError):
        await runtime.sync_products()
    assert conn.marker == datetime(2026, 9, 1, tzinfo=UTC)
    assert conn.writes == []
