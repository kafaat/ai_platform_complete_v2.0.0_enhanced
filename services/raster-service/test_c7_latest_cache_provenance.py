from __future__ import annotations

import logging
import os

import cdse_singleflight
import pytest
import raster_cdse_tile_runtime as runtime
import tile_render

pytestmark = pytest.mark.unit
_LOGGER = logging.getLogger(__name__)
_BBOX = [44.10, 15.30, 44.12, 15.32]


class _LatestClient:
    def __init__(self, *, search_error: bool = False):
        self.search_error = search_error
        self.search_calls = 0
        self.process_calls = 0

    def search_scenes(self, **_kwargs):
        self.search_calls += 1
        if self.search_error:
            raise RuntimeError("catalog unavailable")
        return [
            {
                "id": "S1",
                "datetime": "2026-08-17T10:00:00Z",
                "properties": {"eo:cloud_cover": 3.0},
            }
        ]

    def process_index(self, **_kwargs):
        self.process_calls += 1
        return b"synthetic-geotiff-payload"


@pytest.fixture(autouse=True)
def _clean_cache():
    paths = []
    cdse_singleflight.cdse_tile_cache.clear()
    cdse_singleflight.cdse_key_locks.clear()
    yield paths
    for _expires, path in list(cdse_singleflight.cdse_tile_cache.values()):
        try:
            os.unlink(path)
        except OSError:
            pass
    cdse_singleflight.cdse_tile_cache.clear()
    cdse_singleflight.cdse_key_locks.clear()


def _args():
    return dict(
        field_id="fld-c7",
        internal="ndvi",
        today="2026-08-18",
        date_from="2026-01-01T00:00:00Z",
        date_to="2026-08-18T23:59:59Z",
        field_bbox=_BBOX,
        field_geom=None,
        has_poly=False,
        logger=_LOGGER,
    )


def test_scene_receipt_contains_provenance_identity():
    s = runtime.scene_policy.SelectedScene(
        scene_id="S1",
        acquisition_datetime="2026-08-17T10:00:00Z",
        acquisition_day="2026-08-17",
        cloud_pct=3.0,
        cloud_source="eo:cloud_cover",
        policy="latest_acceptable",
    )
    r = s.as_receipt()
    assert r["scene_id"] == "S1"
    assert r["acquisition_day"] == "2026-08-17"
    assert r["source"] == "cdse"


def test_bind_scene_day_window_returns_none_when_no_eligible_scene():
    _a, _b, selected = runtime.bind_scene_day_window(
        [], "2026-01-01T00:00:00Z", "2026-08-18T23:59:59Z"
    )
    assert selected is None


@pytest.mark.asyncio
async def test_latest_cache_is_scene_bound_and_reused(monkeypatch):
    client = _LatestClient()
    monkeypatch.setattr(runtime._cdse, "get_client", lambda: client)
    monkeypatch.setattr(runtime._cdse, "is_truecolor", lambda _index: False)
    monkeypatch.setattr(tile_render, "raster_has_observable_content", lambda _path: True)

    first = await runtime.ensure_field_cog(**_args())
    second = await runtime.ensure_field_cog(**_args())

    assert first is not None and second == first
    # A catalogue check is intentionally required on each latest request so the
    # cache identity cannot mask the arrival of a newer scene.
    assert client.search_calls == 2
    # The expensive raster processing is single-scene cached.
    assert client.process_calls == 1
    keys = list(cdse_singleflight.cdse_tile_cache)
    assert len(keys) == 1
    assert ":scene:S1:2026-08-17:" in keys[0]
    assert ":request:" not in keys[0]


@pytest.mark.asyncio
async def test_latest_catalog_failure_is_fail_closed(monkeypatch):
    client = _LatestClient(search_error=True)
    monkeypatch.setattr(runtime._cdse, "get_client", lambda: client)

    result = await runtime.ensure_field_cog(**_args())

    assert result is None
    assert client.search_calls == 1
    assert client.process_calls == 0
    assert cdse_singleflight.cdse_tile_cache == {}
