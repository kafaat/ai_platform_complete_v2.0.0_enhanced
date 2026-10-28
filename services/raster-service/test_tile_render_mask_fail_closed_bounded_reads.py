"""حارس انحدار: صلاحيّة البكسل في تصيير البلاطات/المصغّرات — fail-closed + قراءة محدودة.

``P2-REN-1``: حين يفشل ``read_masks`` لمصدر RGB ثلاثيّ الحزم (بلا نطاق ألفا) كان
``_reproject_dataset_mask`` يبتلع الاستثناء ويُرجِع ``None``، فيبقى ألفا ``255`` المُصنَّع
لكلّ البلاطة: بكسلات خارج المصدر/القناع تصير **معتمة سوداء** (8128 ⇒ 65536 من 65536).
تعذّر تحديد الصلاحيّة يجب أن يُغلِق (لا PNG / شفّاف)، لا أن يُلفِّق عتامة.

``P2-REN-2`` / ``EXTRA-10``: القناع والقيم كانا يُقرآن **للمجموعة كلّها** (``read_masks(1)``
و``read(1, masked=True)`` و``read(4)``) لبلاطة 256×256 تغطّي جزءاً صغيراً من المصدر.
القراءة الآن عبر نافذة المصدر التي تغطّي حدود الخرج نفسها (قناعاً وقيماً معاً) ومسقوفة
بـ``MAX_READ_DIM``؛ و``apply_polygon_mask`` (العدديّ) صار يحمل نفس سقف الحجم الذي يحمله
نظيره ``apply_polygon_mask_rgba``.

التحقّق بفكّ PNG وقراءة قناة ألفا بكسلاً بكسلاً — لا توقيع PNG فقط. نقيّة بلا شبكة.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
import rasterio
import tile_render
from fastapi import HTTPException
from PIL import Image
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

pytestmark = pytest.mark.unit

SIZE = 512
# المصدر في الربع الأوسط من بلاطة z1/x1/y1 (EPSG:3857) — نفس مخطّط شاهد التدقيق.
SRC_BOUNDS = (5_000_000.0, -15_000_000.0, 15_000_000.0, -5_000_000.0)
# بلاطة z2/x2/y2 تغطّي ربع المصدر تقريباً (الركن الشماليّ الغربيّ منه).
PARTIAL_TILE = (2, 2, 2)
FULL_TILE = (1, 1, 1)


def _validity() -> np.ndarray:
    """مثلّث صلاحيّة: ``row + col < SIZE`` (يمتدّ في البعدين معاً)."""
    rows, cols = np.mgrid[0:SIZE, 0:SIZE]
    return (rows + cols) < SIZE


def _profile(count: int, dtype: str, **extra) -> dict:
    return {
        "driver": "GTiff",
        "width": SIZE,
        "height": SIZE,
        "count": count,
        "dtype": dtype,
        "crs": "EPSG:3857",
        "transform": from_bounds(*SRC_BOUNDS, SIZE, SIZE),
        "tiled": True,
        "blockxsize": 128,
        "blockysize": 128,
        **extra,
    }


def _write(path, kind: str) -> str:
    valid = _validity()
    path = str(path)
    if kind == "rgb3":  # RGB بلا ألفا: الصلاحيّة في قناع المجموعة وحده
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
            with rasterio.open(path, "w", **_profile(3, "uint8")) as dst:
                dst.write(np.full((3, SIZE, SIZE), 100, dtype="uint8"))
                dst.write_mask(np.where(valid, 255, 0).astype("uint8"))
    elif kind == "rgba":
        data = np.full((4, SIZE, SIZE), 100, dtype="uint8")
        data[3] = np.where(valid, 255, 0)
        with rasterio.open(path, "w", **_profile(4, "uint8")) as dst:
            dst.write(data)
    elif kind == "scalar-mask":  # قيم منتهية خارج الحقل + قناع داخليّ (حالة الشرائط الداكنة)
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
            with rasterio.open(path, "w", **_profile(1, "float32")) as dst:
                dst.write(np.full((SIZE, SIZE), 0.5, dtype="float32"), 1)
                dst.write_mask(np.where(valid, 255, 0).astype("uint8"))
    elif kind == "scalar-nodata":
        arr = np.where(valid, 0.5, -9999.0).astype("float32")
        with rasterio.open(path, "w", **_profile(1, "float32", nodata=-9999.0)) as dst:
            dst.write(arr, 1)
    else:  # pragma: no cover
        raise AssertionError(kind)
    return path


def _alpha(png: bytes | None) -> np.ndarray | None:
    if png is None:
        return None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    return np.array(Image.open(io.BytesIO(png)).convert("RGBA"))[..., 3]


def _reference_tile_alpha(path: str, kind: str, z: int, x: int, y: int) -> np.ndarray:
    """الصلاحيّة المرجعيّة: القناع (أو ألفا RGBA) **كاملاً** مُعاداً إسقاطه nearest."""
    minx, miny, maxx, maxy = tile_render.tile_bounds_3857(z, x, y)
    dst_t = from_bounds(minx, miny, maxx, maxy, tile_render.TILE_SIZE, tile_render.TILE_SIZE)
    out = np.zeros((tile_render.TILE_SIZE, tile_render.TILE_SIZE), dtype="uint8")
    with rasterio.open(path) as src:
        reproject(
            source=src.read(4) if kind == "rgba" else src.read_masks(1),
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_t,
            dst_crs="EPSG:3857",
            resampling=Resampling.nearest,
            src_nodata=0,
            dst_nodata=0,
        )
    return np.where(out > 0, 255, 0).astype("uint8")


class _Spy:
    """غلاف DatasetReader يسجّل القراءات المرئيّة لـPython ويحقن فشل ``read_masks`` اختياريّاً."""

    def __init__(self, src, calls: list, fail_masks: bool):
        self.src = src
        self.calls = calls
        self.fail_masks = fail_masks

    def __getattr__(self, name):
        return getattr(self.src, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.src.close()

    def read(self, *args, **kwargs):
        out = self.src.read(*args, **kwargs)
        self.calls.append(("read", kwargs.get("window"), out.shape[-2:]))
        return out

    def read_masks(self, *args, **kwargs):
        if self.fail_masks:
            raise rasterio.errors.RasterioIOError("injected read_masks failure")
        out = self.src.read_masks(*args, **kwargs)
        self.calls.append(("read_masks", kwargs.get("window"), out.shape[-2:]))
        return out


@pytest.fixture
def spy(monkeypatch):
    state = {"calls": [], "fail_masks": False}
    real_open, real_band = rasterio.open, rasterio.band

    def _open(*args, **kwargs):
        return _Spy(real_open(*args, **kwargs), state["calls"], state["fail_masks"])

    def _band(ds, *args, **kwargs):
        return real_band(ds.src if isinstance(ds, _Spy) else ds, *args, **kwargs)

    monkeypatch.setattr(rasterio, "open", _open)
    monkeypatch.setattr(rasterio, "band", _band)
    return state


def _render_tile(path, kind, tile):
    index = "truecolor" if kind in ("rgb3", "rgba") else "ndvi"
    return tile_render.render_tile_png(path, *tile, index)


def _render_thumb(path, kind, max_px=160):
    index = "truecolor" if kind in ("rgb3", "rgba") else "ndvi"
    return tile_render.render_cog_thumbnail_png(path, index, max_px=max_px)


# ── P2-REN-1: فشل القناع لا يُصنِّع عتامة ────────────────────────────────────
def test_rgb3_tile_mask_read_failure_does_not_fabricate_opacity(tmp_path, spy):
    path = _write(tmp_path / "rgb3.tif", "rgb3")
    normal = _alpha(_render_tile(path, "rgb3", FULL_TILE))
    assert normal is not None
    assert normal[0, 0] == 0, "ركن خارج المصدر يجب أن يكون شفّافاً"
    assert 0 < int((normal > 0).sum()) < normal.size

    spy["fail_masks"] = True
    failed = _alpha(_render_tile(path, "rgb3", FULL_TILE))
    if failed is not None:
        fabricated = int(((failed > 0) & (normal == 0)).sum())
        assert fabricated == 0, (
            f"فشل read_masks صنّع {fabricated} بكسلاً معتماً خارج الصلاحيّة "
            f"(معتم {int((failed > 0).sum())}/{failed.size}، ركن ألفا={int(failed[0, 0])})"
        )


def test_rgb3_thumbnail_mask_read_failure_does_not_fabricate_opacity(tmp_path, spy):
    path = _write(tmp_path / "rgb3.tif", "rgb3")
    normal = _alpha(_render_thumb(path, "rgb3"))
    assert normal is not None
    assert 0 < int((normal > 0).sum()) < normal.size

    spy["fail_masks"] = True
    failed = _alpha(_render_thumb(path, "rgb3"))
    if failed is not None:
        fabricated = int(((failed > 0) & (normal == 0)).sum())
        assert fabricated == 0, (
            f"فشل read_masks صنّع {fabricated} بكسلاً معتماً في المصغّرة "
            f"(معتم {int((failed > 0).sum())}/{failed.size})"
        )


@pytest.mark.parametrize("kind", ["scalar-mask", "scalar-nodata", "rgba"])
def test_mask_read_failure_never_widens_validity_for_other_sources(tmp_path, spy, kind):
    path = _write(tmp_path / f"{kind}.tif", kind)
    normal = _alpha(_render_tile(path, kind, FULL_TILE))
    spy["fail_masks"] = True
    failed = _alpha(_render_tile(path, kind, FULL_TILE))
    if failed is not None:
        assert int(((failed > 0) & (normal == 0)).sum()) == 0


# ── الصلاحيّة لم تتغيّر في المسار العاديّ (نافذة بلا تخفيض ⇒ مطابقة بكسليّة) ──────
@pytest.mark.parametrize("kind", ["rgb3", "rgba", "scalar-mask", "scalar-nodata"])
@pytest.mark.parametrize("tile", [FULL_TILE, PARTIAL_TILE])
def test_tile_alpha_matches_full_mask_reference(tmp_path, kind, tile):
    path = _write(tmp_path / f"{kind}.tif", kind)
    alpha = _alpha(_render_tile(path, kind, tile))
    assert alpha is not None
    expected = _reference_tile_alpha(path, kind, *tile)
    mismatch = int((np.where(alpha > 0, 255, 0) != expected).sum())
    assert mismatch == 0, f"{kind} {tile}: {mismatch} بكسلاً تختلف صلاحيّتها عن المرجع"


# ── P2-REN-2 / EXTRA-10: قراءات محدودة بنافذة الخرج ────────────────────────────
@pytest.mark.parametrize("kind", ["rgb3", "rgba", "scalar-mask", "scalar-nodata"])
def test_partial_tile_reads_only_a_bounded_source_window(tmp_path, spy, kind):
    path = _write(tmp_path / f"{kind}.tif", kind)
    assert _render_tile(path, kind, PARTIAL_TILE) is not None
    full = [c for c in spy["calls"] if c[1] is None or max(c[2]) >= SIZE]
    assert not full, f"{kind}: قراءة المجموعة كاملةً لبلاطة تغطّي ربع المصدر: {full}"
    for _method, _window, shape in spy["calls"]:
        # البلاطة تغطّي ~256×256 بكسل مصدر؛ هامش صغير لنواة إعادة العيّنة فقط.
        assert shape[0] <= 270 and shape[1] <= 270, shape


@pytest.mark.parametrize("kind", ["rgb3", "rgba", "scalar-mask", "scalar-nodata"])
def test_thumbnail_reads_are_capped_by_max_read_dim(tmp_path, spy, monkeypatch, kind):
    monkeypatch.setattr(tile_render, "MAX_READ_DIM", 128)
    path = _write(tmp_path / f"{kind}.tif", kind)
    alpha = _alpha(_render_thumb(path, kind, max_px=64))
    assert alpha is not None
    assert alpha[0, 0] == 255 and alpha[-1, -1] == 0, "المثلّث الصالح يجب أن يبقى مرئيّاً"
    for method, _window, shape in spy["calls"]:
        assert shape[0] * shape[1] <= 128 * 128, (method, shape)


def test_tile_reads_are_capped_by_max_read_dim(tmp_path, spy, monkeypatch):
    monkeypatch.setattr(tile_render, "MAX_READ_DIM", 64)
    path = _write(tmp_path / "scalar-mask.tif", "scalar-mask")
    alpha = _alpha(_render_tile(path, "scalar-mask", FULL_TILE))
    assert alpha is not None and alpha[0, 0] == 0
    assert spy["calls"]
    for method, _window, shape in spy["calls"]:
        assert max(shape) <= 64, (method, shape)


def test_scalar_polygon_mask_has_the_same_size_guard_as_rgba(tmp_path, monkeypatch):
    import raster_settings

    path = _write(tmp_path / "scalar-nodata.tif", "scalar-nodata")
    with open(path, "rb") as fh:
        before = fh.read()
    monkeypatch.setattr(raster_settings, "RASTER_MAX_READ_BAND_PIXELS", SIZE * SIZE - 1)
    geom = {
        "type": "Polygon",
        "coordinates": [[[50.0, -60.0], [120.0, -60.0], [120.0, -45.0], [50.0, -60.0]]],
    }
    with pytest.raises(HTTPException) as exc:
        tile_render.apply_polygon_mask(path, geom)
    assert exc.value.status_code == 413
    with open(path, "rb") as fh:
        assert fh.read() == before, "الرفض يجب أن يسبق أيّ قراءة/كتابة"
