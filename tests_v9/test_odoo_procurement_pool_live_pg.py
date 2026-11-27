"""Exercise the legacy PO adapter with private fixture tables and a one-connection pool."""

import asyncio
import importlib.util
import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

RUNTIME = Path(__file__).resolve().parents[1] / "services/odoo-bridge/erp_runtime.py"


@pytest.mark.parametrize("audit_available", [True, False])
async def test_procurement_releases_pool_and_keeps_confirmed_orders(monkeypatch, audit_available):
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for the PostgreSQL pool regression")
    import asyncpg

    spec = importlib.util.spec_from_file_location("odoo_procurement_test_runtime", RUNTIME)
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    async with asyncpg.create_pool(
        dsn, min_size=1, max_size=1, server_settings={"search_path": "pg_temp"}
    ) as pool:
        # Temporary tables simulate a deployment-supplied source. The bridge's official
        # migrations only create its audit/cursor tables. No fixture writes to public tables.
        await pool.execute("""
            CREATE TEMP TABLE procurement_orders (
                order_id text PRIMARY KEY, tenant_id text, status text, notes text,
                created_at timestamptz, odoo_sync_status text, odoo_document_id text,
                odoo_sync_error text
            );
            CREATE TEMP TABLE procurement_order_items (
                order_id text, item_name text, supplier text, quantity int, unit_cost_usd int
            );
            CREATE TEMP TABLE odoo_sync_log (
                direction text, entity text, odoo_id int, sahool_id text, status text, details text
            );
            INSERT INTO procurement_orders VALUES
                ('A', 'tenant', 'approved', '', '2026-01-01', 'pending', NULL, NULL),
                ('B', 'tenant', 'approved', '', '2026-01-02', 'pending', NULL, NULL);
            INSERT INTO procurement_order_items VALUES
                ('A', 'first', 'supplier', 1, 7), ('B', 'second', 'supplier', 1, 9);
        """)
        if not audit_available:
            await pool.execute("ALTER TABLE pg_temp.odoo_sync_log ADD CHECK (status <> 'success')")

        class Remote:
            def __init__(self):
                self.calls = []
                self.prices = []

            async def search_read(self, model, *args, **kwargs):
                # A real checkout must be possible at every remote call, including lookups.
                async with pool.acquire(timeout=0.5) as conn:
                    assert await conn.fetchval("SELECT 1") == 1
                self.calls.append(model)
                return [{"id": 23}]

            async def create(self, model, values):
                async with pool.acquire(timeout=0.5) as conn:
                    if model == "purchase.order.line":
                        self.prices.append(values["price_unit"])
                        if values["name"] == "first":
                            await conn.execute("""
                                UPDATE pg_temp.procurement_order_items SET unit_cost_usd=11
                                WHERE order_id='B'
                            """)
                self.calls.append(model)
                return len(self.calls)

        remote = Remote()
        monkeypatch.setattr(runtime, "_pool", pool)
        monkeypatch.setattr(runtime, "get_odoo", lambda: remote)
        if audit_available:
            await asyncio.wait_for(runtime.sync_procurement_orders_to_odoo(), timeout=5)
        else:
            with pytest.raises(asyncpg.CheckViolationError):
                await asyncio.wait_for(runtime.sync_procurement_orders_to_odoo(), timeout=5)
        assert (
            remote.calls
            == [
                "res.partner",
                "product.product",
                "purchase.order",
                "purchase.order.line",
            ]
            * 2
        )
        assert remote.prices == [7, 11]
        orders = await pool.fetch("""
            SELECT order_id, odoo_sync_status, odoo_document_id FROM pg_temp.procurement_orders
            ORDER BY order_id
        """)
        assert [tuple(row) for row in orders] == [("A", "synced", "3"), ("B", "synced", "7")]
        audit = await pool.fetch(
            "SELECT sahool_id, status FROM pg_temp.odoo_sync_log ORDER BY sahool_id"
        )
        assert [tuple(row) for row in audit] == (
            [("A", "success"), ("B", "success")] if audit_available else []
        )
        await asyncio.wait_for(runtime.sync_procurement_orders_to_odoo(), timeout=3)
        assert len(remote.calls) == 8
