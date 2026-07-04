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


def _asset_kwargs(**over):
    base = dict(
        field_id="fld_b1c8ff30d02c",
        tenant_id="00000000-0000-4000-8000-000000000001",
        scene_id=None,
        acquisition_date="2026-07-04",
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
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_platform_field_id_passes_validation(monkeypatch):
    """انحدار بلاغ 2026-07-04: fld_<hex> هو المعرّف القانونيّ والعمود VARCHAR(50) —
    فرض UUID عليه أسقط حفظ raster_assets لكلّ حقل حقيقيّ. العقد: fld_* يجتاز
    التحقّق ويصل إلى الاتّصال (غياب القاعدة بعدها ⇒ False بصدق، لا رفض تحقّق)."""
    reached = {"connect": False}

    async def fake_connect():
        reached["connect"] = True
        return None  # لا قاعدة في بيئة الاختبار — يُبتلع بصدق

    monkeypatch.setattr(db_persist, "_connect", fake_connect)
    ok = await db_persist.insert_raster_asset(**_asset_kwargs())
    assert reached["connect"] is True, "fld_* رُفض في التحقّق — انحدار التصليب الزائد عاد"
    assert ok is False  # لا قاعدة ⇒ False، لكن بعد اجتياز التحقّق


@pytest.mark.asyncio
async def test_garbage_field_id_still_rejected_before_connect(monkeypatch):
    """التصليب باقٍ: محارف غريبة/طول يتجاوز العمود تُرفض قبل أيّ اتّصال."""

    async def boom_connect():
        raise AssertionError("_connect must not be called for invalid field_id")

    monkeypatch.setattr(db_persist, "_connect", boom_connect)
    for bad in ("fld'; DROP TABLE raster_assets;--", "fld_" + "a" * 60, "   "):
        ok = await db_persist.insert_raster_asset(**_asset_kwargs(field_id=bad))
        assert ok is False, f"field_id غير صالح قُبل: {bad!r}"
