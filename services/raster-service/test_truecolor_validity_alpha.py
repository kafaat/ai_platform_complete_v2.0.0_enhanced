"""شهود انحدار لصلاحيّة البكسل ومعايرة مسار TrueColor الخام (Element84/VRT).

P2-COL-1: ألفا كانت تُشتقّ من سطوع RGB **بعد** تكميم uint8، فالبكسل الصالح الأسود أو
الخافت (Sentinel DN20×0.0001 → RGB 0) يصير شفّافاً — مع المضلّع وبدونه.
P2-COL-2: بلا مضلّع، قناع الراستر الداخليّ (internal/dataset mask) كان يُتجاهَل فيظهر
بكسل غير صالح لامع معتماً.
P2-COL-3: تراجع Sentinel-2 الاحتياطيّ (0.0001) كان يستبدل ``reflectance_scale=1`` الصريح
في الطلب، فيُعايَر انعكاس جاهز مرّتين (0.5 → 0.00005 → شفّاف).

العقد: الصلاحيّة (nodata/قناع/مضلّع) تُحمَل منفصلةً عن اللون المُكمَّم؛ المعايرة الصريحة
تغلب افتراض المستشعر؛ وDN0 المُعلَن nodata يبقى شفّافاً. rasterio/GDAL حقيقيّان على
راسترات اصطناعيّة؛ الرفع إلى مخزن الكائنات والتحقّق من الرابط فقط مُستبدَلان.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

np = pytest.importorskip("numpy")
rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_bounds  # noqa: E402

pytestmark = pytest.mark.unit

_BOUNDS = (44.0, 16.0, 44.032, 16.032)
_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[44.0, 16.0], [44.032, 16.0], [44.032, 16.032], [44.0, 16.032], [44.0, 16.0]]],
}
# أرباع 32×32: (0:16,0:16) أسود · (0:16,16:) خافت · (16:,0:16) لامع · (16:,16:) غير صالح لامع
_BLACK, _DIM, _BRIGHT, _INVALID = (8, 8), (8, 24), (24, 8), (24, 24)


def _write(tmp_path, name, data, *, nodata=None, internal_mask=None, scales=None):
    path = tmp_path / f"{name}.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[2],
        height=data.shape[1],
        count=data.shape[0],
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=from_bounds(*_BOUNDS, data.shape[2], data.shape[1]),
        nodata=nodata,
    ) as dst:
        dst.write(data)
        if internal_mask is not None:
            dst.write_mask(internal_mask)
        if scales is not None:
            dst.scales = scales
    return str(path)


def _quadrants(dtype, black, dim, bright, invalid):
    a = np.full((3, 32, 32), bright, dtype=dtype)
    a[:, :16, :16] = black
    a[:, :16, 16:] = dim
    a[:, 16:, 16:] = invalid
    return a


def _run(tmp_path, monkeypatch, path, *, source_format, scale, offset=None, polygon=False):
    import band_math
    import cog_writer
    import raster_pixel_processing as pp
    from raster_api_models import BandMapping, ProcessRequest, SourceFormat

    written = []

    def capture(rgba, _path, transform, **_kw):
        written.append(rgba.copy())
        return {"written": False}

    monkeypatch.setattr(cog_writer, "write_rgba_cog", capture)
    req = ProcessRequest(
        tenant_id="witness",
        field_id="field",
        raster_url=path,
        indicator="truecolor",
        source_format=source_format,
        bands=BandMapping(red=1, green=2, blue=3),
        reflectance_scale=scale,
        reflectance_offset=offset,
        apply_cloud_mask=False,
        clip_polygon_geojson=_POLYGON if polygon else None,
    )
    ctx = NS(
        _safe_raster_source=lambda u: u,
        SourceFormat=SourceFormat,
        band_math=band_math,
        UPLOAD_DIR=str(tmp_path),
        object_store=NS(upload_cog=lambda *_a: None),
    )
    stats, *_ = pp.process_pixels(ctx, req, "witness")
    assert len(written) == 1
    return stats, written[0]


@pytest.mark.parametrize("polygon", [False, True], ids=["no_polygon", "polygon"])
@pytest.mark.parametrize(
    "fmt, dtype, values, scale",
    [
        ("custom", "float32", (0.0, 0.002, 0.2, 0.6), 1.0),
        ("sentinel2_l2a", "uint16", (0, 20, 2000, 6000), 0.0001),
    ],
    ids=["custom_reflectance", "sentinel2_dn"],
)
@pytest.mark.parametrize("validity", ["internal_mask", "declared_nodata"])
def test_alpha_is_source_validity_not_quantised_brightness(
    tmp_path, monkeypatch, polygon, fmt, dtype, values, scale, validity
):
    """P2-COL-1 + P2-COL-2: الأسود/الخافت الصالحان معتمان؛ غير الصالح اللامع شفّاف."""
    black, dim, bright, invalid = values
    mask = np.full((32, 32), 255, dtype="uint8")
    mask[16:, 16:] = 0
    if validity == "internal_mask":
        data = _quadrants(dtype, black, dim, bright, invalid)
        path = _write(tmp_path, "rgb", data, internal_mask=mask)
    else:
        nd = 65535 if dtype == "uint16" else -9999.0
        data = _quadrants(dtype, black, dim, bright, nd)
        path = _write(tmp_path, "rgb", data, nodata=nd)

    stats, rgba = _run(tmp_path, monkeypatch, path, source_format=fmt, scale=scale, polygon=polygon)

    assert rgba.shape == (4, 32, 32)
    alpha = rgba[3]
    assert alpha[_BLACK] == 255, "valid black pixel must stay opaque"
    assert alpha[_DIM] == 255, "valid dim pixel quantised to RGB 0 must stay opaque"
    assert alpha[_BRIGHT] == 255
    assert alpha[_INVALID] == 0, "masked/nodata bright pixel must be transparent"
    np.testing.assert_array_equal(alpha, mask)
    assert tuple(rgba[:3, _BLACK[0], _BLACK[1]]) == (0, 0, 0)
    assert stats["valid_pixels"] == 768
    assert stats["nodata_pixels"] == 256


@pytest.mark.parametrize("polygon", [False, True], ids=["no_polygon", "polygon"])
def test_internal_mask_hides_bright_pixels_with_and_without_polygon(tmp_path, monkeypatch, polygon):
    """P2-COL-2: القناع الداخليّ يُخفي البكسل اللامع حتى بلا مضلّع (لا nodata مطابق)."""
    mask = np.full((32, 32), 255, dtype="uint8")
    mask[16:, 16:] = 0
    data = _quadrants("float32", 0.2, 0.2, 0.2, 0.6)
    path = _write(tmp_path, "masked", data, internal_mask=mask)
    stats, rgba = _run(
        tmp_path, monkeypatch, path, source_format="custom", scale=1.0, polygon=polygon
    )
    assert rgba[3][_INVALID] == 0, "internally masked bright pixel leaked as opaque"
    assert stats["nodata_pixels"] == 256


@pytest.mark.parametrize("polygon", [False, True], ids=["no_polygon", "polygon"])
def test_entirely_black_valid_raster_is_opaque(tmp_path, monkeypatch, polygon):
    """P2-COL-1: راستر أسود صالح بالكامل (لا nodata مُعلَن) لا يُعلَن بلا بكسلات صالحة."""
    path = _write(tmp_path, "black", np.zeros((3, 32, 32), dtype="float32"))
    stats, rgba = _run(
        tmp_path, monkeypatch, path, source_format="custom", scale=1.0, polygon=polygon
    )
    assert stats["valid_pixels"] == 1024
    assert (rgba[3] == 255).all()


def test_partial_band_invalidity_makes_the_pixel_transparent(tmp_path, monkeypatch):
    """سياسة جمع الأقنعة: البكسل صالح فقط إن صلح في النطاقات الثلاثة."""
    data = np.full((3, 32, 32), 0.2, dtype="float32")
    data[0, 0, 0] = -9999.0  # الأحمر فقط nodata
    path = _write(tmp_path, "partial", data, nodata=-9999.0)
    stats, rgba = _run(tmp_path, monkeypatch, path, source_format="custom", scale=1.0)
    assert rgba[3, 0, 0] == 0
    assert stats["valid_pixels"] == 1023


def test_sentinel_declared_dn0_nodata_stays_transparent(tmp_path, monkeypatch):
    """DN0 المُعلَن nodata في منتج Sentinel-2 لا يُعامَل صالحاً؛ DN20 الخافت معتم."""
    data = _quadrants("uint16", 0, 20, 2000, 0)
    path = _write(tmp_path, "s2_dn0", data, nodata=0)
    stats, rgba = _run(tmp_path, monkeypatch, path, source_format="sentinel2_l2a", scale=None)
    assert rgba[3][_BLACK] == 0 and rgba[3][_INVALID] == 0
    assert rgba[3][_DIM] == 255 and rgba[3][_BRIGHT] == 255
    assert stats["valid_pixels"] == 512


def test_explicit_identity_scale_beats_sentinel_fallback(tmp_path, monkeypatch):
    """P2-COL-3: scale=1 صريح في الطلب يغلب تراجع Sentinel-2 (0.0001) — معايرة مرّة واحدة."""
    data = np.full((3, 32, 32), 0.5, dtype="float32")
    path = _write(tmp_path, "calibrated", data)
    _, custom = _run(tmp_path, monkeypatch, path, source_format="custom", scale=1.0)
    _, s2 = _run(tmp_path, monkeypatch, path, source_format="sentinel2_l2a", scale=1.0)
    assert int(custom[0, 0, 0]) == 127
    np.testing.assert_array_equal(s2, custom)
    assert (s2[3] == 255).all()


def test_undeclared_sentinel_dn_keeps_the_fallback_scale(tmp_path, monkeypatch):
    """التراجع المقصود باقٍ: لا scale في الطلب ولا في الراستر ⇒ DN Sentinel-2 × 0.0001."""
    data = np.full((3, 32, 32), 5000, dtype="uint16")
    path = _write(tmp_path, "raw_dn", data)
    _, rgba = _run(tmp_path, monkeypatch, path, source_format="sentinel2_l2a", scale=None)
    assert int(rgba[0, 0, 0]) == 127
    assert (rgba[3] == 255).all()


def test_declared_raster_scale_beats_sentinel_fallback(tmp_path, monkeypatch):
    """scale مُعلَن في الراستر (≠1) يُطبَّق مرّة واحدة دون تراجع."""
    data = np.full((3, 32, 32), 2500, dtype="uint16")
    path = _write(tmp_path, "declared", data, scales=(0.0002, 0.0002, 0.0002))
    _, rgba = _run(tmp_path, monkeypatch, path, source_format="sentinel2_l2a", scale=None)
    assert int(rgba[0, 0, 0]) == 127
