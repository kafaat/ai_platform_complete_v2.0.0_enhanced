"""Harvest custody integrity and the market lot link (live PG, v278).

Owner decisions 2 and 3 (2026-11-15). Drives a migrated Postgres through the restricted
NOBYPASSRLS application role, never a fake connection:

* custody_chain_events: UPDATE, DELETE and TRUNCATE are refused by v278's triggers;
* harvest_lots: identity and quantity are immutable, status stays writable; a lot with custody
  events cannot be deleted, and a field with lots cannot be deleted (ON DELETE RESTRICT, which
  used to be CASCADE and erased the chain);
* the platform's field guard (``api.field_context.refuse_if_fields_have_harvest_lots``) answers 409 before the DELETE;
* the market MCP server's ``tool_create_sales_listing`` with ``harvest_lot_id``: a listing up to
  the lot's remainder passes, beyond it 409, custody sales and active listings both count, a sold
  lot is refused and another tenant's lot is 404 (RLS).

Negative controls disable each v278 trigger inside a rolled-back owner transaction and show the
refused write then passes, so the refusals measured here come from v278. Rows are seeded by the
schema owner (the restricted role only does what the services do).
"""

from __future__ import annotations

import asyncio
import importlib
import os
import secrets
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

# Switch read before any import: on a certifying runner a missing dependency must fail the
# module, not importorskip it into a green skip (certification-switch-before-importorskip).
_CERTIFICATION_REQUIRED = os.getenv("HARVEST_CUSTODY_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
    from fastapi import HTTPException
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg")
    pytest.importorskip("fastapi")
    from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
MCP_DIR = ROOT / "services" / "mcp_servers"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", DSN)
T1 = str(uuid.uuid4())
T2 = str(uuid.uuid4())


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(ADMIN_DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        has = await conn.fetchval(
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'custody_chain_events_immutable'"
        )
        col = await conn.fetchval(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'market_sales_listings' AND column_name = 'harvest_lot_id'"
        )
        return "" if has and col else "v278 not applied"
    finally:
        await conn.close()


_SKIP = asyncio.run(_probe())
if _SKIP:
    if _CERTIFICATION_REQUIRED:
        raise RuntimeError(
            f"HARVEST_CUSTODY_CERTIFICATION_REQUIRED=1 but no v278 database: {_SKIP}"
        )
    pytest.skip(f"no migrated database with v278: {_SKIP}", allow_module_level=True)


def _run(coro):
    return asyncio.run(coro)


async def _app(tenant: str):
    conn = await asyncpg.connect(DSN)
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
    return conn


async def _seed(tenant: str, *, lot_kg: float = 1000, sales_kg: float | None = None) -> dict:
    """Owner seeds a field, a lot and its harvest event (and optionally a sale)."""
    field_id = "f_" + uuid.uuid4().hex[:12]
    lot_id = "hl_" + uuid.uuid4().hex[:16]
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(
            "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid)",
            field_id,
            tenant,
        )
        await admin.execute(
            "INSERT INTO harvest_lots (harvest_lot_id, tenant_id, field_id, harvest_date, quantity_kg) "
            "VALUES ($1, $2::uuid, $3, $4, $5)",
            lot_id,
            tenant,
            field_id,
            date(2026, 10, 1),
            lot_kg,
        )
        await admin.execute(
            "INSERT INTO custody_chain_events (tenant_id, harvest_lot_id, event_type, quantity_kg, occurred_at) "
            "VALUES ($1::uuid, $2, 'harvest', $3, $4)",
            tenant,
            lot_id,
            lot_kg,
            datetime(2026, 10, 1, tzinfo=UTC),
        )
        if sales_kg is not None:
            await admin.execute(
                "INSERT INTO custody_chain_events (tenant_id, harvest_lot_id, event_type, quantity_kg, occurred_at) "
                "VALUES ($1::uuid, $2, 'sales', $3, $4)",
                tenant,
                lot_id,
                sales_kg,
                datetime(2026, 10, 5, tzinfo=UTC),
            )
    finally:
        await admin.close()
    return {"field_id": field_id, "lot_id": lot_id}


async def _expect_sqlstate(coro, state: str) -> None:
    with pytest.raises(asyncpg.PostgresError) as err:
        await coro
    assert err.value.sqlstate == state, (err.value.sqlstate, str(err.value))


# ── custody events are append-only ──────────────────────────────────────────────────────────
def test_custody_events_cannot_be_updated_deleted_or_truncated():
    async def go():
        s = await _seed(T1)
        app = await _app(T1)
        try:
            n = await app.fetchval(
                "SELECT count(*) FROM custody_chain_events WHERE harvest_lot_id = $1", s["lot_id"]
            )
            assert n == 1  # visible to its tenant, so the refusals below are not RLS
            await _expect_sqlstate(
                app.execute(
                    "UPDATE custody_chain_events SET quantity_kg = 1 WHERE harvest_lot_id = $1",
                    s["lot_id"],
                ),
                "55000",
            )
            await _expect_sqlstate(
                app.execute(
                    "DELETE FROM custody_chain_events WHERE harvest_lot_id = $1", s["lot_id"]
                ),
                "55000",
            )
        finally:
            await app.close()
        admin = await asyncpg.connect(ADMIN_DSN)
        try:
            tr = admin.transaction()
            await tr.start()
            try:
                # Even the owner's TRUNCATE is refused by the statement trigger.
                await _expect_sqlstate(admin.execute("TRUNCATE custody_chain_events"), "55000")
            finally:
                await tr.rollback()
        finally:
            await admin.close()

    _run(go())


def test_negative_control_without_the_trigger_the_update_passes():
    async def go():
        s = await _seed(T1)
        admin = await asyncpg.connect(ADMIN_DSN)
        try:
            tr = admin.transaction()
            await tr.start()
            await admin.execute(
                "ALTER TABLE custody_chain_events DISABLE TRIGGER custody_chain_events_immutable"
            )
            status = await admin.execute(
                "UPDATE custody_chain_events SET quantity_kg = 1 WHERE harvest_lot_id = $1",
                s["lot_id"],
            )
            assert status == "UPDATE 1"
            await tr.rollback()
        finally:
            await admin.close()

    _run(go())


# ── lots: immutable identity, no cascading erasure ──────────────────────────────────────────
def test_lot_identity_is_immutable_but_status_is_writable():
    async def go():
        s = await _seed(T1)
        app = await _app(T1)
        try:
            for col, val in (
                ("quantity_kg", 5),
                ("field_id", "f_other"),
                ("harvest_date", date(2026, 9, 1)),
            ):
                await _expect_sqlstate(
                    app.execute(
                        f"UPDATE harvest_lots SET {col} = $1 WHERE harvest_lot_id = $2",
                        val,
                        s["lot_id"],
                    ),
                    "55000",
                )
            ok = await app.execute(
                "UPDATE harvest_lots SET status = 'stored' WHERE harvest_lot_id = $1", s["lot_id"]
            )
            assert ok == "UPDATE 1"
        finally:
            await app.close()
        admin = await asyncpg.connect(ADMIN_DSN)
        try:  # negative control
            tr = admin.transaction()
            await tr.start()
            await admin.execute(
                "ALTER TABLE harvest_lots DISABLE TRIGGER harvest_lots_identity_immutable"
            )
            assert (
                await admin.execute(
                    "UPDATE harvest_lots SET quantity_kg = 5 WHERE harvest_lot_id = $1", s["lot_id"]
                )
                == "UPDATE 1"
            )
            await tr.rollback()
        finally:
            await admin.close()

    _run(go())


def test_a_lot_with_custody_events_and_a_field_with_lots_are_not_deleted():
    async def go():
        s = await _seed(T1)
        app = await _app(T1)
        try:
            await _expect_sqlstate(
                app.execute("DELETE FROM harvest_lots WHERE harvest_lot_id = $1", s["lot_id"]),
                "23503",
            )
            await _expect_sqlstate(
                app.execute("DELETE FROM fields WHERE field_id = $1", s["field_id"]), "23503"
            )
            assert (
                await app.fetchval(
                    "SELECT count(*) FROM custody_chain_events WHERE harvest_lot_id = $1",
                    s["lot_id"],
                )
                == 1
            )
            fks = dict(
                await app.fetch(
                    "SELECT conname, confdeltype::text FROM pg_constraint WHERE conname IN "
                    "('harvest_lots_field_id_fkey', 'custody_chain_events_harvest_lot_id_fkey')"
                )
            )
            assert set(fks.values()) == {"r"}, fks  # RESTRICT, was CASCADE ('c')
        finally:
            await app.close()

    _run(go())


def test_the_platform_field_guard_answers_409_before_the_delete():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    from api.field_context import refuse_if_fields_have_harvest_lots

    async def go():
        s = await _seed(T1)
        empty = "f_" + uuid.uuid4().hex[:12]
        app = await _app(T1)
        try:
            with pytest.raises(HTTPException) as err:
                await refuse_if_fields_have_harvest_lots(app, [s["field_id"]], "الحذف")
            assert err.value.status_code == 409
            await refuse_if_fields_have_harvest_lots(app, [empty], "الحذف")  # no lots: passes
        finally:
            await app.close()
        # Another tenant cannot probe this tenant's lots through the guard (RLS).
        other = await _app(T2)
        try:
            await refuse_if_fields_have_harvest_lots(other, [s["field_id"]], "الحذف")
        finally:
            await other.close()

    _run(go())


# ── market listings are checked against the lot ─────────────────────────────────────────────
@pytest.fixture()
def market():
    path_before = list(sys.path)
    shared_before = {
        k: v for k, v in sys.modules.items() if k == "shared" or k.startswith("shared.")
    }
    for p in (str(ROOT), str(MCP_DIR)):
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    for name in [n for n in sys.modules if n == "shared" or n.startswith("shared.")]:
        mod_file = getattr(sys.modules.get(name), "__file__", "") or ""
        if mod_file and str(MCP_DIR) not in mod_file:
            sys.modules.pop(name, None)
    os.environ.setdefault("JWT_SECRET", secrets.token_hex(32))  # importable config only
    try:
        ms = importlib.import_module("market_server")
    except Exception:
        if _CERTIFICATION_REQUIRED:
            raise
        pytest.skip("market_server not importable here")
    saved = ms.get_pool
    try:
        yield ms
    finally:
        ms.get_pool = saved
        sys.path[:] = path_before
        for k in [k for k in sys.modules if k == "shared" or k.startswith("shared.")]:
            sys.modules.pop(k, None)
        sys.modules.update(shared_before)


def _listing(ms, tenant: str, lot_id: str, qty: float):
    async def go():
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)

        async def _pool():
            return pool

        ms.get_pool = _pool
        try:
            return await ms.tool_create_sales_listing(
                {
                    "tenant_id": tenant,
                    "crop_type": "wheat",
                    "quantity_kg": qty,
                    "price_per_kg_usd": 0.5,
                    "harvest_lot_id": lot_id,
                }
            )
        finally:
            await pool.close()

    return _run(go())


def test_a_listing_cannot_offer_more_than_the_lot_still_holds(market):
    s = _run(_seed(T1, lot_kg=1000, sales_kg=300))  # 700 left after the custody sale
    first = _listing(market, T1, s["lot_id"], 500)
    assert first["harvest_lot_id"] == s["lot_id"]
    with pytest.raises(HTTPException) as err:
        _listing(market, T1, s["lot_id"], 250)  # 700 - 500 active = 200 left
    assert err.value.status_code == 409
    assert _listing(market, T1, s["lot_id"], 200)["status"] == "active"


def test_a_sold_lot_and_another_tenants_lot_are_refused(market):
    s = _run(_seed(T1))

    async def mark_sold():
        app = await _app(T1)
        try:
            await app.execute(
                "UPDATE harvest_lots SET status = 'sold' WHERE harvest_lot_id = $1", s["lot_id"]
            )
        finally:
            await app.close()

    other = _run(_seed(T1))
    with pytest.raises(HTTPException) as err:
        _listing(market, T2, other["lot_id"], 1)
    assert err.value.status_code == 404  # RLS: invisible, same answer as missing
    _run(mark_sold())
    with pytest.raises(HTTPException) as err:
        _listing(market, T1, s["lot_id"], 1)
    assert err.value.status_code == 409
