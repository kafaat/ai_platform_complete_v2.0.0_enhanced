"""ST-02 / ST-03: دورة حياة التخزين والرفع — الأصول الدائمة لا تُعامَل كاشاً، والرفع يُتحقَّق منه.

ST-02 — كان ``raster_lifecycle.cleanup`` يصنّف **كلّ** ``.tif`` في جذر التخزين «مشتقّاً»
ويحذفه بالعمر وحده: الأصل المرفوع (``ras_*``/``drone_*``) وCOG المؤشّر الذي ما زال
``raster_assets.cog_uri`` يشير إليه (``file://`` في وضع التخزين المحلّيّ) يُحذَفان بعد ٩٠ يوماً
فيُرجِع ``layer_lookup`` «لا طبقة» لصفٍّ قائم. و``.tiff`` يُترَك بينما ``.tif`` يُحذَف — لاتماثل
امتداد لا قرار محتوى. المقيس هنا: الكاش (مؤقّت/مصغّرات/PNG عرض) يُنظَّف، وGeoTIFF بأيّ
امتداد يُحتفَظ به ويُبلَّغ عنه صراحةً.

ST-03 — كان الرفع يقرأ الجسم كاملاً في الذاكرة (``await file.read()``) ويحفظ أيّ بايتات
بامتداد ``.tif`` ويُصدِر ``raster_url`` لها. المقيس: قراءة متدفّقة بقطع محدودة وسقف بايتات،
بايتات TIFF السحريّة، فتح rasterio فعليّ مع CRS، ولا ملفّ يبقى عند الرفض.
"""

from __future__ import annotations

import asyncio
import io
import os
import time

import numpy as np
import pytest
from fastapi import HTTPException
from rasterio.transform import from_origin
from starlette.datastructures import UploadFile

rasterio = pytest.importorskip("rasterio")

import raster_lifecycle as rl  # noqa: E402
import routers.storage as storage  # noqa: E402

pytestmark = pytest.mark.unit

_TOKEN = "test-agent-token"


def _chunk() -> int:
    return getattr(storage, "_UPLOAD_CHUNK_BYTES", 0)


def _touch(path, *, age_days: float, payload: bytes = b"x" * 64) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(payload)
    ts = time.time() - age_days * 86400
    os.utime(path, (ts, ts))


# ── ST-02 ───────────────────────────────────────────────────────────────────


def test_cleanup_never_deletes_aged_geotiff_assets(tmp_path):
    """أصل مرفوع + أصل درون + COG مؤشّر (قد يشير إليه raster_assets) — كلّها تبقى."""
    root = str(tmp_path)
    durable = ["ras_original.tif", "drone_original.tif", "ndvi_asset.tif", "truecolor_ab12.TIF"]
    for name in durable:
        _touch(os.path.join(root, name), age_days=400)

    report = rl.cleanup(root, dry_run=False)

    remaining = sorted(os.listdir(root))
    assert remaining == sorted(durable), report
    assert report["removed"] == 0
    assert report["retained_durable"] == len(durable)


def test_cleanup_treats_tif_and_tiff_identically(tmp_path):
    """``.tif`` و``.tiff`` الصنف نفسه: كلاهما أصل دائم مُبلَّغ عنه، لا أحدهما محذوف والآخر مُتجاهَل."""
    root = str(tmp_path)
    _touch(os.path.join(root, "same_asset.tif"), age_days=400)
    _touch(os.path.join(root, "same_asset.tiff"), age_days=400)

    report = rl.cleanup(root, dry_run=False)

    assert sorted(os.listdir(root)) == ["same_asset.tif", "same_asset.tiff"]
    assert report["retained_durable"] == 2
    stats = rl.scan_storage(root)
    assert set(stats["by_type_mb"]) == {"tif"}  # .tiff لا يسقط في «other»


def test_cleanup_still_evicts_aged_cache(tmp_path):
    """تحكّم موجب: المؤقّت والمصغّرات وPNG العرض كاش يُعاد توليده فيُنظَّف بالعمر."""
    root = str(tmp_path)
    _touch(os.path.join(root, "tmp_partial.tmp"), age_days=5)
    _touch(os.path.join(root, "field_thumb.png"), age_days=40)
    _touch(os.path.join(root, "render_preview.png"), age_days=100)
    _touch(os.path.join(root, "fresh_preview.png"), age_days=1)
    _touch(os.path.join(root, "offline_packs", "jawf.mbtiles"), age_days=1000)

    report = rl.cleanup(root, dry_run=False)

    assert sorted(os.listdir(root)) == ["fresh_preview.png", "offline_packs"]
    assert os.path.exists(os.path.join(root, "offline_packs", "jawf.mbtiles"))
    assert report["removed"] == 3


def test_cleanup_reports_only_files_it_can_remove(tmp_path):
    """مجلّد اسمه ``tmp_*`` لا يُحذَف (الحذف للملفّات فقط) فلا يجوز عدّه «محذوفاً»."""
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "tmp_dir"))
    ts = time.time() - 10 * 86400
    os.utime(os.path.join(root, "tmp_dir"), (ts, ts))

    report = rl.cleanup(root, dry_run=False)

    assert os.path.isdir(os.path.join(root, "tmp_dir"))
    assert report["removed"] == 0


# ── ST-03 ───────────────────────────────────────────────────────────────────


class _RecordingUpload(UploadFile):
    """UploadFile يسجّل أحجام القراءة: ``read()`` بلا حدّ = تحميل الجسم كاملاً في الذاكرة."""

    def __init__(self, payload: bytes, filename: str) -> None:
        super().__init__(file=io.BytesIO(payload), filename=filename)
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return await super().read(size)


def _geotiff_bytes(tmp_path, *, crs: str | None = "EPSG:4326") -> bytes:
    path = tmp_path / "src.tif"
    profile = {
        "driver": "GTiff",
        "height": 16,
        "width": 16,
        "count": 1,
        "dtype": "float32",
        "transform": from_origin(44.0, 16.0, 0.0001, 0.0001),
    }
    if crs:
        profile["crs"] = crs
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.full((1, 16, 16), 0.5, dtype="float32"))
    return path.read_bytes()


@pytest.fixture
def upload_root(tmp_path, monkeypatch):
    import raster_settings

    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(raster_settings, "AGENT_TOKEN", _TOKEN)
    monkeypatch.setattr(storage, "UPLOAD_DIR", str(root))
    return root


def _upload_raster(payload: bytes, filename: str = "in.tif"):
    up = _RecordingUpload(payload, filename)
    return up, asyncio.run(storage.upload_raster(file=up, x_agent_token=_TOKEN))


def _upload_drone(payload: bytes, filename: str = "ortho.tif"):
    up = _RecordingUpload(payload, filename)
    return up, asyncio.run(
        storage.upload_drone(file=up, tenant_id="t-1", field_id=None, x_agent_token=_TOKEN)
    )


def test_upload_rejects_non_raster_bytes(upload_root):
    with pytest.raises(HTTPException) as exc:
        _upload_raster(b"not a raster", "invalid.txt")
    assert exc.value.status_code == 415
    assert os.listdir(upload_root) == []


def test_upload_rejects_tiff_magic_that_does_not_open_as_raster(upload_root):
    with pytest.raises(HTTPException) as exc:
        _upload_raster(b"II*\x00" + b"\x00" * 64)
    assert exc.value.status_code == 422
    assert os.listdir(upload_root) == []


def test_upload_rejects_raster_without_crs(upload_root, tmp_path):
    with pytest.raises(HTTPException) as exc:
        _upload_drone(_geotiff_bytes(tmp_path, crs=None))
    assert exc.value.status_code == 422
    assert os.listdir(upload_root) == []


def test_upload_enforces_streamed_byte_cap(upload_root, tmp_path, monkeypatch):
    payload = _geotiff_bytes(tmp_path)
    monkeypatch.setattr(storage, "RASTER_UPLOAD_MAX_BYTES", len(payload) - 1, raising=False)
    up = _RecordingUpload(payload, "big.tif")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(storage.upload_raster(file=up, x_agent_token=_TOKEN))
    assert exc.value.status_code == 413
    assert os.listdir(upload_root) == []
    assert up.read_sizes and all(0 < s <= _chunk() for s in up.read_sizes)


def test_valid_georeferenced_upload_is_streamed_and_persisted(upload_root, tmp_path):
    up, out = _upload_raster(_geotiff_bytes(tmp_path))
    assert up.read_sizes and all(0 < s <= _chunk() for s in up.read_sizes)
    path = out["raster_url"].removeprefix("file://")
    assert os.path.dirname(path) == str(upload_root)
    assert os.path.basename(path).startswith("ras_") and path.endswith(".tif")
    assert os.listdir(upload_root) == [os.path.basename(path)]  # لا ملفّ جزئيّ متبقٍّ
    with rasterio.open(path) as ds:
        assert ds.crs is not None and ds.count == 1

    _up, drone = _upload_drone(_geotiff_bytes(tmp_path))
    assert os.path.basename(drone["raster_url"]).startswith("drone_")
