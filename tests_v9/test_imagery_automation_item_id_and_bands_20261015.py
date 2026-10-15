"""A discovered STAC item must not masquerade as a multi-band processed image.

This behavior fails on the original main: it drops item_id and sends a single
NIR href to the multi-band COG processor.  The repaired scheduler records the
discovered scene without fabricating indicators.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
CORE = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"


@pytest.mark.asyncio
async def test_stac_item_id_is_discovered_without_fabricated_multiband_cog(monkeypatch):
    monkeypatch.syspath_prepend(str(CORE))
    from api import imagery_automation as mod

    async def search(**kwargs):
        return {"items": [{
            "item_id": "S2-valid-123",
            "datetime": "2026-10-12T11:00:00Z",
            "provider": "cdse",
            "bands_urls": {"nir": "https://example.invalid/sentinel/B08.tif"},
        }]}

    calls = []
    persisted = []
    async def fake_batch(*, tenant_id, payload, **kwargs):
        calls.append(payload)
        return {"job_id": "fake", "status": "pending"}

    async def persist(self, tracked):
        persisted.append(tracked.last_image_id)

    monkeypatch.setattr(mod, "search_imagery_scenes", search)
    monkeypatch.setattr(mod, "process_indicator_batch", fake_batch)
    monkeypatch.setattr(mod.ImageryAutomation, "_persist_field", persist)
    scheduler = mod.ImageryAutomation()
    field = mod.TrackedField(field_id="f1", bbox=[44.0, 15.0, 44.1, 15.1], tenant_id="t1")

    first = await scheduler._scan_one("f1", field, "2026-10-01", "2026-10-14", asyncio.Semaphore(1))
    assert first == (True, None)
    assert field.last_image_id == "S2-valid-123"
    assert field.new_images_found == 1
    assert persisted == ["S2-valid-123"]
    assert calls == [], "a single NIR href cannot supply all multi-band inputs"

    duplicate = await scheduler._scan_one("f1", field, "2026-10-01", "2026-10-14", asyncio.Semaphore(1))
    assert duplicate == (False, None)
    assert field.new_images_found == 1
    assert calls == []
