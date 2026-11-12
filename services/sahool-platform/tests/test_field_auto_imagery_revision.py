"""A field task must carry the commit it came from, even after another edit."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api import imagery_automation as automation
from api.routers import fields

GEOM = {
    "type": "Polygon",
    "coordinates": [
        [
            [44.75, 16.15],
            [44.76, 16.15],
            [44.76, 16.16],
            [44.75, 16.16],
            [44.75, 16.15],
        ]
    ],
}


@pytest.mark.asyncio
async def test_create_task_preserves_committed_revision_in_raster_request(monkeypatch):
    from types import SimpleNamespace

    result = {"field_id": "fld_one", "geometry": GEOM, "geometry_revision": 7}
    monkeypatch.setattr(fields, "_persist_field", AsyncMock(return_value=result))
    dispatch = AsyncMock(return_value={"queued": True})
    monkeypatch.setattr(automation.imagery_automation, "trigger_field_imagery_processing", dispatch)
    tasks = BackgroundTasks()
    await fields.create_field(None, tasks, user=SimpleNamespace(tenant_id="tenant"), idem=None)
    await tasks()
    assert dispatch.await_args.kwargs["geometry_revision"] == 7
    assert dispatch.await_args.kwargs["field_id"] == "fld_one"
    assert dispatch.await_args.kwargs["tenant_id"] == "tenant"


@pytest.mark.asyncio
@pytest.mark.parametrize("found", [11, None])
async def test_legacy_receipt_needs_matching_current_geometry(monkeypatch, found):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import api.main

    @asynccontextmanager
    async def txn():
        yield

    conn = SimpleNamespace(
        fetchval=AsyncMock(return_value=found), execute=AsyncMock(), transaction=txn
    )

    @asynccontextmanager
    async def acquire():
        yield conn

    monkeypatch.setattr(api.main, "get_pool", lambda: SimpleNamespace(acquire=acquire))
    dispatch = AsyncMock(return_value={"queued": True})
    monkeypatch.setattr(automation.imagery_automation, "trigger_field_imagery_processing", dispatch)
    await automation._kick_imagery_processing(
        field_id="fld_one", tenant_id="tenant", geometry=GEOM, reason="field.created"
    )
    sql, field, tenant, _ = conn.fetchval.await_args.args
    assert (field, tenant) == ("fld_one", "tenant")
    assert "f.geometry::jsonb = $3::jsonb" in sql and "HAVING count(*) = 1" in sql
    if found is None:
        dispatch.assert_not_awaited()
    else:
        assert dispatch.await_args.kwargs["geometry_revision"] == found
