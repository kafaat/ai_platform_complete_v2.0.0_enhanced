"""Regression guard for the raster-service DATE-binding bug (diagnostic Finding 2).

asyncpg infers ``$3`` in ``fetch_latest_asset`` as ``date`` (from ``$3::date``), so
passing a raw ISO string raised ``'str' object has no attribute 'toordinal'`` — the
error was swallowed as a warning, and *any* specific historical date returned no row
(→ transparent tile → blank historical timeline). These tests pin the fix: the shared
``_iso_date_or_none`` helper coerces strings, and ``fetch_latest_asset`` binds a
``datetime.date`` (never a ``str``) to the date parameter.
"""

from __future__ import annotations

import asyncio
import importlib.util
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DB_PERSIST = ROOT / "services" / "raster-service" / "db_persist.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("raster_db_persist_under_test", DB_PERSIST)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_iso_date_or_none_coerces_strings_and_rejects_garbage():
    m = _load_module()
    assert m._iso_date_or_none("2026-07-23") == date(2026, 7, 23)
    # tolerates a full ISO timestamp (first 10 chars)
    assert m._iso_date_or_none("2026-07-23T10:11:12Z") == date(2026, 7, 23)
    # passthrough for an already-normalized date object
    assert m._iso_date_or_none(date(2026, 7, 23)) == date(2026, 7, 23)
    # empty / None / sentinel / malformed → None (no filter / no crash)
    assert m._iso_date_or_none(None) is None
    assert m._iso_date_or_none("") is None
    assert m._iso_date_or_none("latest") is None
    assert m._iso_date_or_none("not-a-date") is None


@pytest.mark.unit
def test_fetch_latest_asset_binds_date_object_not_string():
    """The $3 date parameter must reach asyncpg as datetime.date, never str."""
    m = _load_module()
    captured: dict[str, tuple] = {}

    class _FakeConn:
        async def execute(self, *args):
            return None

        async def fetchrow(self, _sql, *args):
            captured["args"] = args
            return None  # no row → function returns None; we only assert the bind

        async def close(self):
            return None

    async def _fake_connect():
        return _FakeConn()

    m._connect = _fake_connect  # type: ignore[assignment]

    asyncio.run(m.fetch_latest_asset("fld_x", "truecolor", date="2026-07-23", tenant_id="t-1"))
    # positional args to fetchrow: (field_id, index_name, d, tenant) → d is index 2
    bound_date = captured["args"][2]
    assert isinstance(bound_date, date), f"expected datetime.date, got {type(bound_date)}"
    assert bound_date == date(2026, 7, 23)


@pytest.mark.unit
def test_fetch_latest_asset_latest_binds_none():
    """'latest'/empty selects the newest asset (NULL date filter), not a crash."""
    m = _load_module()
    captured: dict[str, tuple] = {}

    class _FakeConn:
        async def execute(self, *args):
            return None

        async def fetchrow(self, _sql, *args):
            captured["args"] = args
            return None

        async def close(self):
            return None

    async def _fake_connect():
        return _FakeConn()

    m._connect = _fake_connect  # type: ignore[assignment]

    asyncio.run(m.fetch_latest_asset("fld_x", "truecolor", date="latest", tenant_id="t-1"))
    assert captured["args"][2] is None
