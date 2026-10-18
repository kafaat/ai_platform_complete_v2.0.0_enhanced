"""A discovered STAC item must not masquerade as a multi-band processed image.

This behavior fails on the original main: it drops item_id and sends a single
NIR href to the multi-band COG processor. The repaired scheduler records the
discovered scene without fabricating indicators.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
CORE = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"


@pytest.mark.asyncio
async def test_stac_item_id_is_discovered_without_fabricated_multiband_cog(monkeypatch):
    monkeypatch.syspath_prepend(str(CORE))
    from api import imagery_automation as mod

    # Run the real producer serializer: a hand-written consumer fixture could
    # silently preserve the very id/item_id mismatch this regression guards.
    spec = importlib.util.spec_from_file_location(
        "imagery_gap_stac_search", CORE.parent / "raster-service" / "stac_search.py"
    )
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)

    async def catalog_query(payload):
        return {
            "features": [
                {
                    "id": "S2-valid-123",
                    "properties": {"datetime": "2026-10-12T11:00:00Z"},
                    "assets": {"nir": {"href": "https://example.invalid/sentinel/B08.tif"}},
                }
            ]
        }

    monkeypatch.setattr(producer, "stac_query", catalog_query)

    async def search(**kwargs):
        return await producer.stac_search_element84(
            kwargs["bbox"], kwargs["datetime_start"], kwargs["datetime_end"], 40, kwargs["limit"]
        )

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
    assert field.last_indicator_job is None
    assert field.last_ndvi_mean is None

    duplicate = await scheduler._scan_one(
        "f1", field, "2026-10-01", "2026-10-14", asyncio.Semaphore(1)
    )
    assert duplicate == (False, None)
    assert field.new_images_found == 1
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("asset_key", ["assets", "band_urls"])
async def test_single_nir_legacy_shape_never_dispatches_multiband_batch(monkeypatch, asset_key):
    """Independent witness: old code must fail even after fixing item_id alone."""
    monkeypatch.syspath_prepend(str(CORE))
    from api import imagery_automation as mod

    calls = []

    async def batch(**kwargs):
        calls.append(kwargs)
        return {}  # No polling or network if the unsafe old path is exercised.

    monkeypatch.setattr(mod, "process_indicator_batch", batch)
    field = mod.TrackedField(field_id="f1", bbox=[44, 15, 44.1, 15.1], tenant_id="t1")
    await mod.ImageryAutomation()._trigger_indicators(
        field,
        {"id": "S2-legacy", asset_key: {"nir": "https://example.invalid/B08.tif"}},
    )

    assert calls == [], "a single NIR asset must never be treated as a seven-band COG"
    assert field.last_indicator_job is None
    assert field.last_ndvi_mean is None


@pytest.mark.asyncio
async def test_explicit_multiband_dispatch_keeps_item_identity_and_consumes_results(monkeypatch):
    """Exercise the supported batch path; raster I/O is a simulated boundary."""
    monkeypatch.syspath_prepend(str(CORE))
    from api import imagery_automation as mod

    calls = []
    reads = []

    async def batch(**kwargs):
        calls.append(kwargs)
        return {"job_id": "batch-123", "status": "completed"}

    async def result(job_id, *, tenant_id):
        reads.append((job_id, tenant_id))
        values = {"batch-123_ndvi": 0.6, "batch-123_ndmi": 0.2, "batch-123_msi": 0.7}
        return {"stats": {"mean": values[job_id], "valid_pixels": 100}}

    monkeypatch.setattr(mod, "process_indicator_batch", batch)
    monkeypatch.setattr(mod, "get_job_result", result)
    field = mod.TrackedField(field_id="f1", bbox=[44, 15, 44.1, 15.1], tenant_id="t1")
    await mod.ImageryAutomation()._trigger_indicators(
        field,
        {
            "item_id": "S2-normalized",
            "datetime": "2026-10-12T11:00:00Z",
            "raster_url": "https://example.invalid/normalized-seven-band.tif",
        },
    )

    assert len(calls) == 1
    assert calls[0]["tenant_id"] == "t1"
    assert calls[0]["payload"]["tenant_id"] == "t1"
    assert calls[0]["payload"]["field_id"] == "f1"
    assert calls[0]["payload"]["scene_id"] == "S2-normalized"
    assert reads == [(f"batch-123_{name}", "t1") for name in ("ndvi", "ndmi", "msi")]
    assert field.last_indicator_job == "batch-123"
    assert (field.last_ndvi_mean, field.last_ndmi_mean, field.last_msi_mean) == (0.6, 0.2, 0.7)
    assert field.last_ndvi_date == "2026-10-12"
