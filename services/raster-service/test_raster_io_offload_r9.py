"""R9: عمل GDAL/rasterio المتزامن لا يُجمّد حلقة الأحداث، وقراءات GDAL HTTP محدودة المهلة.

الخدمة تعمل بعامل uvicorn واحد؛ تصيير بلاطة أو قراءة شبكة من COG بعيد بطيء كان يجري
داخل معالج ``async`` مباشرةً فيحجب **كلّ** الطلبات الأخرى حتّى ينتهي. الإصلاح: ``run_raster_io``
(خيط + محدِّد تزامن) في ``raster_field_runtime``، ومهلات ``GDAL_HTTP_*`` افتراضيّة يغلبها المشغّل.

تكذيب: إعادة أيّ استدعاء ``render_tile_png``/``_grid_from_cog`` إلى الحلقة مباشرةً يُحمِّر
اختبار الاستجابة المسمّى هنا (الحلقة تتجمّد ~ثانيتين بدل أجزاء من الثانية).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_BLOCK_S = 2.0  # مدّة حجب GDAL المُحاكى (يُحرَّر مبكّراً حين يبقى المسار مستجيباً)


async def _noop_async(*_args, **_kwargs):
    return None


class _BlockingGdal:
    """نداء GDAL مُحاكى يحجب خيطه حتّى يُحرَّر أو تنقضي ``_BLOCK_S``."""

    def __init__(self, result):
        self.result = result
        self.release = threading.Event()

    def __call__(self, *_args, **_kwargs):
        self.release.wait(_BLOCK_S)
        return self.result


async def _assert_loop_stays_responsive(handler_coro, blocker: _BlockingGdal, cheap):
    """يُشغّل المعالج الحاجب ويقيس كمون طلب رخيص متزامن معه على الحلقة نفسها."""
    task = asyncio.create_task(handler_coro)
    t0 = time.monotonic()
    await asyncio.sleep(0.05)  # يُسلِّم الحلقة للمعالج الحاجب
    cheap_result = await cheap()
    latency = time.monotonic() - t0
    blocker.release.set()
    result = await asyncio.wait_for(task, timeout=_BLOCK_S + 5)
    assert latency < _BLOCK_S / 2, (
        f"R9: حلقة الأحداث تجمّدت {latency:.2f}s خلف نداء GDAL متزامن — "
        "يجب أن يمرّ عبر run_raster_io (خيط + محدِّد)"
    )
    return result, cheap_result


async def _cheap_cached_tile(fields):
    """طلب رخيص حقيقيّ: بلاطة من الذاكرة المؤقّتة (لا GDAL)."""
    return await fields.field_tile("fld-cheap", 10, 1, 1, index="ndvi", date="latest", v=None)


def _patch_field_router(monkeypatch, fields):
    async def layer(*_a, **_k):
        return {"cog_url": "file:///slow/remote.tif", "acquisition_date": "2026-10-01"}

    monkeypatch.setattr(fields, "_require_field_tenant", _noop_async)
    monkeypatch.setattr(fields, "_resolve_field_layer", layer)
    # البلاطة الرخيصة مخزّنة؛ الحاجبة ليست كذلك.
    monkeypatch.setattr(fields, "_read_tile_cache", lambda p: _PNG if "fld-cheap" in p else None)
    monkeypatch.setattr(fields, "_write_tile_cache", lambda *_a: None)


@pytest.mark.asyncio
async def test_field_tile_slow_gdal_render_does_not_block_concurrent_request(monkeypatch):
    import tile_render
    from routers import fields

    _patch_field_router(monkeypatch, fields)
    blocker = _BlockingGdal(_PNG)
    monkeypatch.setattr(tile_render, "render_tile_png", blocker)

    slow, cheap = await _assert_loop_stays_responsive(
        fields.field_tile("fld-slow", 10, 1, 1, index="ndvi", date="latest", v=None),
        blocker,
        lambda: _cheap_cached_tile(fields),
    )
    assert slow.body == _PNG and slow.headers["X-Sahool-Tile-Cache"] == "miss"
    assert cheap.headers["X-Sahool-Tile-Cache"] == "hit"


@pytest.mark.asyncio
async def test_field_indicator_grid_slow_cog_read_does_not_block_loop(monkeypatch):
    from routers import fields

    _patch_field_router(monkeypatch, fields)
    blocker = _BlockingGdal({"real_data": True, "grid": [[0.5]]})
    monkeypatch.setattr(fields, "_grid_from_cog", blocker)

    slow, _ = await _assert_loop_stays_responsive(
        fields.field_indicator_grid("fld-slow", index="ndvi", date="latest", grid=8),
        blocker,
        lambda: _cheap_cached_tile(fields),
    )
    assert slow["real_data"] is True


@pytest.mark.asyncio
async def test_cdse_tile_slow_gdal_render_does_not_block_loop(monkeypatch):
    import tile_render
    from routers import cdse_tiles, fields

    _patch_field_router(monkeypatch, fields)

    async def params(*_a, **_k):
        return {
            "internal": "ndvi",
            "field_bbox": None,
            "today": "2026-10-01",
            "date_from": "2026-09-01",
            "date_to": "2026-10-01",
            "field_geom": None,
            "has_poly": False,
        }

    async def cog(*_a, **_k):
        return "/slow/cdse.tif"

    monkeypatch.setattr(cdse_tiles, "_require_field", _noop_async)
    monkeypatch.setattr(cdse_tiles, "_normalize_cdse_request", params)
    monkeypatch.setattr(cdse_tiles, "_ensure_field_cog", cog)
    blocker = _BlockingGdal(_PNG)
    monkeypatch.setattr(tile_render, "render_tile_png", blocker)

    slow, _ = await _assert_loop_stays_responsive(
        cdse_tiles.field_cdse_tile("fld-slow", 10, 1, 1, index="ndvi", date="latest"),
        blocker,
        lambda: _cheap_cached_tile(fields),
    )
    assert slow.body == _PNG


@pytest.mark.asyncio
async def test_raster_io_concurrency_is_bounded(monkeypatch):
    import raster_field_runtime as rt

    monkeypatch.setenv("RASTER_IO_CONCURRENCY", "2")  # محدِّد جديد لكلّ حلقة (RunVar)
    lock = threading.Lock()
    active = peak = 0

    def work(i):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return i

    results = await asyncio.gather(*(rt.run_raster_io(work, i) for i in range(6)))
    assert results == list(range(6))
    assert peak == 2, f"run_raster_io تجاوز RASTER_IO_CONCURRENCY=2 (ذروة {peak})"


def test_raster_io_concurrency_env_is_sane(monkeypatch):
    import raster_field_runtime as rt

    monkeypatch.setenv("RASTER_IO_CONCURRENCY", "0")
    assert rt.raster_io_concurrency() == 1
    monkeypatch.setenv("RASTER_IO_CONCURRENCY", "not-a-number")
    assert rt.raster_io_concurrency() == 8


def test_gdal_http_reads_have_timeouts_by_default(monkeypatch):
    import object_store

    for key in object_store.GDAL_HTTP_DEFAULTS:
        monkeypatch.setenv(key, "placeholder")  # يسجّل الأصل كي يُستعاد بعد الاختبار
        monkeypatch.delenv(key)
    object_store.gdal_http_defaults()
    assert os.environ["GDAL_HTTP_TIMEOUT"] == "30"
    assert os.environ["GDAL_HTTP_CONNECTTIMEOUT"] == "10"
    assert os.environ["GDAL_HTTP_MAX_RETRY"] == "2"
    rasterio_env = pytest.importorskip("rasterio._env")
    # GDAL نفسه يرى المهلة (CPLGetConfigOption يسقط إلى البيئة) — لا مجرّد قاموس بايثون.
    assert str(rasterio_env.get_gdal_config("GDAL_HTTP_TIMEOUT")) == "30"


def test_operator_gdal_http_settings_win(monkeypatch):
    import object_store

    monkeypatch.setenv("GDAL_HTTP_TIMEOUT", "90")
    monkeypatch.setenv("GDAL_HTTP_MAX_RETRY", "0")
    object_store.gdal_http_defaults()
    assert os.environ["GDAL_HTTP_TIMEOUT"] == "90"
    assert os.environ["GDAL_HTTP_MAX_RETRY"] == "0"


def test_gdal_http_defaults_applied_at_import():
    """عمليّة نظيفة بلا GDAL_HTTP_*: مجرّد استيراد object_store (التطبيق والعمّال) يضبطها."""
    here = Path(__file__).resolve().parent
    env = {k: v for k, v in os.environ.items() if not k.startswith("GDAL_HTTP_")}
    env["PYTHONPATH"] = os.pathsep.join([str(here), str(here.parents[1])])
    probe = (
        "import os, object_store; "
        "print(','.join(os.environ.get(k, '') for k in "
        "('GDAL_HTTP_TIMEOUT', 'GDAL_HTTP_CONNECTTIMEOUT', 'GDAL_HTTP_MAX_RETRY')))"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "30,10,2"
