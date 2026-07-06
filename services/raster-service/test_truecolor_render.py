"""اختبارات وحدة للصورة الخام بالألوان الطبيعيّة (True Color) — evalscript RGBA + تصيير
متعدّد النطاقات. نقيّة (بلا شبكة CDSE): الـevalscript دالّة نصّ خالصة، والتصيير يُختبَر
على COG اصطناعيّ 4-نطاقات UINT8 يُبنى في الذاكرة (rasterio) دون أيّ جلب خارجيّ.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ── evalscript: RGBA UINT8 من B04/B03/B02 + قناع SCL/dataMask في ألفا ─────────
def test_truecolor_evalscript_is_rgba_uint8_from_visual_bands():
    import cdse_client as _cdse

    es = _cdse.build_truecolor_evalscript()
    # النطاقات البصريّة الثلاثة + SCL (قناع الغيوم) + dataMask.
    for band in ('"B02"', '"B03"', '"B04"', '"SCL"', '"dataMask"'):
        assert band in es, band
    # مُخرَج 4 نطاقات UINT8 (RGBA) — لا FLOAT32 أحاديّ كالمؤشّرات.
    assert "bands: 4" in es
    assert "UINT8" in es
    # قناع per-pixel: بلا بيانات أو غيمة ⇒ شفّاف تماماً [0,0,0,0].
    assert "s.dataMask !== 1 || isCloud" in es
    assert "[0, 0, 0, 0]" in es
    # أصناف SCL للغيوم مُضمَّنة (اتّساق مع مسار المؤشّرات).
    assert "SCL_CLOUD" in es


def test_truecolor_evalscript_default_gain_is_3_5():
    import cdse_client as _cdse

    es = _cdse.build_truecolor_evalscript()
    assert "3.500000" in es  # الكسب الافتراضيّ 3.5 (Sentinel-2 TCI نموذجيّ)


def test_truecolor_evalscript_respects_gain_env(monkeypatch):
    import cdse_client as _cdse

    monkeypatch.setenv("CDSE_TRUECOLOR_GAIN", "3.0")
    es = _cdse.build_truecolor_evalscript()
    assert "3.000000" in es  # الكسب البصريّ مضبوط من البيئة (لا قيمة مُثبَّتة عمياء)


def test_is_truecolor_normalizes_separators():
    import cdse_client as _cdse

    for v in ("truecolor", "TrueColor", "true-color", "true color", " TRUE_COLOR "):
        assert _cdse.is_truecolor(v) is True
    for v in ("ndvi", "", None, "true"):
        assert _cdse.is_truecolor(v) is False


def test_build_evalscript_dispatches_truecolor_to_rgba():
    import cdse_client as _cdse

    # build_evalscript('truecolor') يجب أن يُرجِع الـRGBA (4 نطاقات) لا مؤشّراً أحاديّاً.
    es = _cdse.build_evalscript("truecolor")
    assert "bands: 4" in es and "UINT8" in es
    # وأنّ truecolor مُدرَج في المؤشّرات المدعومة (لتقرير التوافر).
    assert "truecolor" in _cdse.supported_indices()


# ── التصيير: COG اصطناعيّ RGBA → بلاطة PNG (تمرير مباشر بلا خريطة ألوان) ─────
def _write_synthetic_rgba_cog(path: str) -> None:
    """يكتب GeoTIFF 4-نطاقات UINT8 (RGBA) في EPSG:3857 داخل بلاطة z=0 (العالم كلّه)."""
    np = pytest.importorskip("numpy")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_bounds

    w, h = 64, 64
    # امتداد مركزيّ صغير ضمن حدود بلاطة z=0/0/0 (العالم في 3857).
    minx, miny, maxx, maxy = -5_000_000.0, -5_000_000.0, 5_000_000.0, 5_000_000.0
    transform = from_bounds(minx, miny, maxx, maxy, w, h)
    data = np.zeros((4, h, w), dtype="uint8")
    data[0, :, :] = 120  # R
    data[1, :, :] = 160  # G
    data[2, :, :] = 60  # B
    data[3, :, :] = 255  # ألفا: كلّه مرئيّ
    profile = {
        "driver": "GTiff",
        "width": w,
        "height": h,
        "count": 4,
        "dtype": "uint8",
        "crs": "EPSG:3857",
        "transform": transform,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)


def test_render_truecolor_tile_returns_png_with_visible_pixels(tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("rasterio")
    import tile_render

    cog = str(tmp_path / "tc.tif")
    _write_synthetic_rgba_cog(cog)
    png = tile_render.render_truecolor_tile_png(cog, 0, 0, 0)
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # توقيع PNG صحيح


def test_render_tile_png_routes_truecolor_to_multiband_path(tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("rasterio")
    import tile_render

    cog = str(tmp_path / "tc2.tif")
    _write_synthetic_rgba_cog(cog)
    # render_tile_png بمؤشّر 'truecolor' يجب أن يمرّ عبر مسار RGBA (لا colorize أحاديّ).
    png = tile_render.render_tile_png(cog, 0, 0, 0, "truecolor")
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_truecolor_rejects_single_band_cog(tmp_path):
    np = pytest.importorskip("numpy")
    rasterio = pytest.importorskip("rasterio")
    import tile_render
    from rasterio.transform import from_bounds

    cog = str(tmp_path / "single.tif")
    w, h = 32, 32
    transform = from_bounds(-1_000_000.0, -1_000_000.0, 1_000_000.0, 1_000_000.0, w, h)
    with rasterio.open(
        cog,
        "w",
        driver="GTiff",
        width=w,
        height=h,
        count=1,
        dtype="uint8",
        crs="EPSG:3857",
        transform=transform,
    ) as dst:
        dst.write(np.full((1, h, w), 100, dtype="uint8"))
    # <3 نطاقات ⇒ ليست RGB(A) ⇒ None (لا نُصيِّر صورة ألوان من نطاق واحد).
    assert tile_render.render_truecolor_tile_png(cog, 0, 0, 0) is None


# ── حفظ COG RGBA (persist) → تصيير من /tiles المحفوظ (دورة كاملة) ─────
def test_write_rgba_cog_roundtrips_to_truecolor_tile(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("rasterio")
    import cog_writer
    import tile_render
    from rasterio.transform import from_bounds

    w, h = 64, 64
    transform = from_bounds(-5_000_000.0, -5_000_000.0, 5_000_000.0, 5_000_000.0, w, h)
    rgba = np.zeros((4, h, w), dtype="uint8")
    rgba[0], rgba[1], rgba[2], rgba[3] = 120, 160, 60, 255
    out = str(tmp_path / "tc_cog.tif")
    info = cog_writer.write_rgba_cog(rgba, out, transform, crs="EPSG:3857")
    assert info["written"] is True
    assert info["bands"] == 4
    # COG المحفوظ يُصيَّر عبر نفس مسار truecolor (كما يفعل /tiles للحقل المُجهَّز).
    png = tile_render.render_truecolor_tile_png(out, 0, 0, 0)
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_write_rgba_cog_accepts_hwc_and_rejects_2d(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("rasterio")
    import cog_writer
    from rasterio.transform import from_bounds

    transform = from_bounds(-1_000_000.0, -1_000_000.0, 1_000_000.0, 1_000_000.0, 16, 16)
    # (H,W,C) مقبول ويُحوَّل داخليّاً إلى (C,H,W).
    hwc = np.zeros((16, 16, 4), dtype="uint8")
    hwc[..., 3] = 255
    info = cog_writer.write_rgba_cog(hwc, str(tmp_path / "hwc.tif"), transform, crs="EPSG:3857")
    assert info["written"] is True and info["bands"] == 4
    # مصفوفة ثنائيّة (نطاق واحد) مرفوضة بصدق (ليست RGB/RGBA) — لا كتابة مُلفَّقة.
    bad = cog_writer.write_rgba_cog(
        np.zeros((16, 16), dtype="uint8"), str(tmp_path / "bad.tif"), transform, crs="EPSG:3857"
    )
    assert bad["written"] is False


def test_truecolor_thumbnail_preserves_rgb_channels(tmp_path):
    """مصغّرة TrueColor يجب أن تكون RGB حقيقية، لا band-1 ملوّن بتدرّج المؤشرات."""
    import io

    import numpy as np
    import rasterio
    import tile_render
    from PIL import Image
    from rasterio.transform import from_bounds

    path = tmp_path / "truecolor_thumb.tif"
    profile = {
        "driver": "GTiff",
        "height": 16,
        "width": 16,
        "count": 4,
        "dtype": "uint8",
        "crs": "EPSG:4326",
        "transform": from_bounds(44.0, 16.0, 44.1, 16.1, 16, 16),
    }
    data = np.zeros((4, 16, 16), dtype="uint8")
    data[0, :, :] = 100  # R
    data[1, :, :] = 150  # G
    data[2, :, :] = 200  # B
    data[3, :, :] = 255  # A
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)

    png = tile_render.render_cog_thumbnail_png(str(path), "truecolor", max_px=64)
    assert png is not None
    arr = np.array(Image.open(io.BytesIO(png)).convert("RGBA"))
    visible = arr[arr[..., 3] > 0]
    assert visible.size > 0
    mean = visible[:, :3].mean(axis=0)
    assert abs(float(mean[0]) - 100) < 4
    assert abs(float(mean[1]) - 150) < 4
    assert abs(float(mean[2]) - 200) < 4
