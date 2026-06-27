from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_RASTER = Path(__file__).resolve().parent.parent / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import db_persist  # noqa: E402


@pytest.mark.asyncio
async def test_insert_raster_asset_rejects_empty_field_id_before_connect(monkeypatch):
    async def boom_connect():
        raise AssertionError("_connect must not be called for invalid UUID")

    monkeypatch.setattr(db_persist, "_connect", boom_connect)
    ok = await db_persist.insert_raster_asset(
        field_id="",
        tenant_id="",
        scene_id=None,
        acquisition_date="2026-06-26",
        satellite="sentinel-2-l2a",
        index_name="ndvi",
        cloud_pct=None,
        srid=4326,
        cog_uri="/tmp/x.tif",
        bands=None,
        nodata=0.0,
        footprint=None,
        provenance=None,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_insert_raster_asset_rejects_invalid_tenant_before_connect(monkeypatch):
    async def boom_connect():
        raise AssertionError("_connect must not be called for invalid UUID")

    monkeypatch.setattr(db_persist, "_connect", boom_connect)
    ok = await db_persist.insert_raster_asset(
        field_id="00000000-0000-4000-8000-000000000001",
        tenant_id="not-a-uuid",
        scene_id=None,
        acquisition_date="2026-06-26",
        satellite="sentinel-2-l2a",
        index_name="ndvi",
        cloud_pct=None,
        srid=4326,
        cog_uri="/tmp/x.tif",
        bands=None,
        nodata=0.0,
        footprint=None,
        provenance=None,
    )
    assert ok is False
