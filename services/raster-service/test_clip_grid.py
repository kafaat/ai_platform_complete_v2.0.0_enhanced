"""
test_clip_grid.py — تحقّق ذاتيّ (synthetic) لمسار القصّ + المؤشّر + الشبكة.

البيئة هنا تحجب الشبكة لمزوّدي الأقمار، لذا نتحقّق بـraster صناعي في الذاكرة
(MemoryFile/ملفّ مؤقّت) في CRS من نوع UTM، لا بجلب حيّ. المنطق نفسه صحيح
للإنتاج حيث تُقرأ COGs لـSentinel-2 L2A عبر /vsicurl.

نتحقّق:
  (أ) بكسلات خارج مضلّع الحقل = NaN/null.
  (ب) NDVI محسوب صحيحاً داخل الحقل.
  (ج) الحدود معاد إسقاطها إلى 4326 بشكل معقول.
  (د) عقد شبكة المؤشّر يطابق العقد المطلوب (شكلاً).
"""

import math
import os
import tempfile

import main
import numpy as np
import raster_processing_runtime
import rasterio
from raster_api_models import BandMapping, IndicatorKind, ProcessRequest, SourceFormat
from rasterio.transform import from_origin

# منطقة الجوف (اليمن) تقع في UTM zone 38N (EPSG:32638).
UTM = "EPSG:32638"
# أصل تقريبي قرب lon=44E, lat=16N في UTM 38N
ORIGIN_X = 393000.0  # easting
ORIGIN_Y = 1773000.0  # northing (أعلى يسار)
RES = 10.0  # 10 م/بكسل (Sentinel-2)
W = H = 100


def _decode_png_rgba(png_bytes: bytes) -> np.ndarray:
    """Decode renderer PNG output (RGBA, filter 0) without PIL."""
    import struct
    import zlib

    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    width = height = None
    idat = bytearray()
    while pos < len(png_bytes):
        (length,) = struct.unpack(">I", png_bytes[pos : pos + 4])
        tag = png_bytes[pos + 4 : pos + 8]
        data = png_bytes[pos + 8 : pos + 8 + length]
        if tag == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
            assert bit_depth == 8 and color_type == 6
        elif tag == b"IDAT":
            idat.extend(data)
        pos += 12 + length
    raw = zlib.decompress(bytes(idat))
    rows = []
    stride = width * 4
    off = 0
    for _ in range(height):
        assert raw[off] == 0
        off += 1
        rows.append(np.frombuffer(raw[off : off + stride], dtype=np.uint8).reshape(width, 4))
        off += stride
    return np.stack(rows, axis=0)


def _make_synthetic_geotiff(path: str):
    """يكتب راستر صناعي ٢-نطاق (red, nir) في UTM. NDVI معروف = 0.5 بكلّ مكان.

    red=1000, nir=3000 → NDVI=(3000-1000)/(3000+1000)=0.5.
    """
    red = np.full((H, W), 1000.0, dtype="float32")
    nir = np.full((H, W), 3000.0, dtype="float32")
    transform = from_origin(ORIGIN_X, ORIGIN_Y, RES, RES)
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 2,
        "height": H,
        "width": W,
        "crs": UTM,
        "transform": transform,
        "nodata": -9999.0,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(red, 1)  # band 1 = red
        dst.write(nir, 2)  # band 2 = nir
    return transform


def _clip_polygon_4326_left_half():
    """مضلّع 4326 يغطّي النصف الأيسر تقريباً من الراستر.

    نحسب حدود الراستر بـ4326 ثمّ نأخذ نصفه الأيسر (lon < منتصف) كمضلّع حقل.
    """
    from rasterio.warp import transform_bounds

    left = ORIGIN_X
    right = ORIGIN_X + W * RES
    top = ORIGIN_Y
    bottom = ORIGIN_Y - H * RES
    minlon, minlat, maxlon, maxlat = transform_bounds(UTM, "EPSG:4326", left, bottom, right, top)
    # مثلّث يغطّي ~نصف المساحة: حدوده الخارجيّة = bbox الراستر، لكن المثلّث
    # نفسه يترك ركناً كبيراً خارجه → بكسلات NaN كثيرة بعد القصّ (crop=True
    # يقصّ على bbox المثلّث = bbox الراستر، فالركن خارج المثلّث = NaN).
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [minlon, minlat],
                [maxlon, minlat],
                [minlon, maxlat],
                [minlon, minlat],
            ]
        ],
    }, (minlon, minlat, maxlon, maxlat)


def test_clip_index_bounds_and_grid():
    tmpdir = tempfile.mkdtemp(prefix="raster_test_")
    tif_path = os.path.join(tmpdir, "scene.tif")
    _make_synthetic_geotiff(tif_path)

    clip_geojson, (minlon, minlat, maxlon, maxlat) = _clip_polygon_4326_left_half()

    req = ProcessRequest(
        tenant_id="t_test",
        field_id="field_001",
        raster_url=f"file://{tif_path}",
        indicator=IndicatorKind.ndvi,
        source_format=SourceFormat.sentinel2_l2a,
        bands=BandMapping(red=1, nir=2),
        clip_polygon_geojson=clip_geojson,
        apply_cloud_mask=False,
        capture_datetime="2026-05-01T08:30:00Z",
    )

    # وجّه COG إلى مجلّد مؤقّت عبر سياق المعالجة الصريح.
    stats, bounds, res_m, meta = raster_processing_runtime.process_pixels(
        req, "layer_test", upload_dir=tmpdir
    )

    # ── (ب) NDVI داخل الحقل = 0.5 ────────────────────────────────────
    assert abs(stats["mean"] - 0.5) < 1e-4, f"NDVI mean متوقّع 0.5، وجد {stats['mean']}"
    assert abs(stats["min"] - 0.5) < 1e-4 and abs(stats["max"] - 0.5) < 1e-4
    assert stats["valid_pixels"] > 0
    print(f"(ب) NDVI صحيح: mean={stats['mean']} valid={stats['valid_pixels']}")

    # ── (ج) الحدود معاد إسقاطها إلى 4326 ─────────────────────────────
    assert -180 <= bounds[0] <= 180 and -90 <= bounds[1] <= 90, f"حدود غير 4326: {bounds}"
    # يجب أن تكون قرب lon~44, lat~16 (الجوف)
    assert 43.0 < bounds[0] < 45.0, f"minlon متوقّع ~44، وجد {bounds[0]}"
    assert 15.0 < bounds[1] < 17.0, f"minlat متوقّع ~16، وجد {bounds[1]}"
    print(f"(ج) حدود 4326 معقولة: {[round(x, 4) for x in bounds]}")

    # ── (أ) بكسلات خارج المضلّع = NaN ────────────────────────────────
    # نعيد فتح COG المكتوب ونتحقّق أنّ النصف الأيمن NaN والأيسر = 0.5
    cog_path = meta["cog_url"].replace("file://", "")
    assert os.path.exists(cog_path), "COG لم يُكتب"
    with rasterio.open(cog_path) as src:
        out = src.read(1).astype("float64")
    finite_mask = np.isfinite(out)
    # عمود منتصف الشبكة المقصوصة: يمينه يجب أن يكون كلّه NaN (خارج الحقل)
    n_finite = int(finite_mask.sum())
    n_nan = int((~finite_mask).sum())
    assert n_finite > 0, "لا بكسلات صالحة داخل الحقل"
    assert n_nan > 0, "متوقّع بكسلات NaN خارج الحقل (القصّ لم يُطبَّق!)"
    # كلّ القيم الصالحة = 0.5
    assert np.allclose(out[finite_mask], 0.5, atol=1e-4)
    # النسبة المقصوصة معقولة (~نصف المساحة خارج المضلّع تقريباً)
    frac_outside = n_nan / out.size
    print(
        f"(أ) القصّ مطبَّق: داخل={n_finite} NaN={n_nan} (خارج={frac_outside:.0%} من شبكة COG المقصوصة)"
    )
    assert frac_outside > 0.2, "متوقّع جزء كبير NaN خارج النصف الأيسر"

    # ── (أ2) لا raster bleed في مسار البلاطات: نفس الـCOG المقصوص يجب أن ينتج
    # بكسلات شفافة خارج المضلّع داخل البلاطة، لا تلوين bbox كامل.
    import tile_render

    z = 18
    tx, ty = tile_render._lonlat_to_tile((minlon + maxlon) / 2.0, (minlat + maxlat) / 2.0, z)
    png = tile_render.render_tile_png(cog_path, z, tx, ty, "ndvi")
    assert png is not None, "متوقّع بلاطة تتقاطع COG المقصوص"
    rgba = _decode_png_rgba(png)
    alpha = rgba[..., 3]
    assert int((alpha > 0).sum()) > 0, "متوقّع بكسلات داخل الحقل"
    assert int((alpha == 0).sum()) > 0, "متوقّع شفافية خارج الحقل — لا raster bleed"

    # سجّل الطبقة في الحالة كما يفعل _run_processing (لاختبار العقد)
    main._layers["layer_test"] = {
        "layer_id": "layer_test",
        "field_id": "field_001",
        "index": "ndvi",
        "cog_url": meta["cog_url"],
        "acquisition_date": "2026-05-01T08:30:00Z",
        "created_at": "2026-05-01T09:00:00Z",
        "source_format": "sentinel2_l2a",
        "bounds_4326": bounds,
    }
    main._field_layers.setdefault("field_001", []).append("layer_test")

    # ── (د) عقد شبكة المؤشّر (real_data=True) عبر TestClient ──────────
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    resp = client.get(
        "/v1/fields/field_001/indicator-grid",
        params={"index": "ndvi", "date": "latest", "grid": 16},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    required = {
        "field_id",
        "index",
        "date",
        "bbox",
        "rows",
        "cols",
        "grid",
        "stats",
        "zones",
        "source",
        "real_data",
    }
    assert required.issubset(body.keys()), f"حقول ناقصة: {required - set(body.keys())}"
    assert body["real_data"] is True, "متوقّع real_data=True (COG حقيقي موجود)"
    assert body["field_id"] == "field_001"
    assert body["index"] == "ndvi"
    assert isinstance(body["bbox"], list) and len(body["bbox"]) == 4
    assert isinstance(body["rows"], int) and isinstance(body["cols"], int)
    assert len(body["grid"]) == body["rows"]
    for row in body["grid"]:
        assert len(row) == body["cols"]
        for v in row:
            assert v is None or isinstance(v, (int, float))
    assert set(body["stats"].keys()) == {"min", "max", "mean"}
    for z in body["zones"]:
        assert set(z.keys()) == {"id", "severity", "mean", "cells"}
        assert z["severity"] in ("low", "medium", "high")
        for cell in z["cells"]:
            assert len(cell) == 2

    # داخل الحقل NDVI=0.5 → بعض الخلايا = 0.5، وبعضها null (خارج الحقل)
    flat = [v for r in body["grid"] for v in r]
    n_null = sum(1 for v in flat if v is None)
    n_val = sum(1 for v in flat if v is not None)
    assert n_val > 0 and n_null > 0, "متوقّع خلايا قيمة + خلايا null في الشبكة"
    assert all(abs(v - 0.5) < 1e-3 for v in flat if v is not None)
    print(
        f"(د) عقد شبكة صحيح: {body['rows']}x{body['cols']} "
        f"قيمة={n_val} null={n_null} real_data={body['real_data']} "
        f"zones={[z['severity'] for z in body['zones']]}"
    )

    # ── (هـ) fallback المحاكاة لحقل بلا COG ──────────────────────────
    resp2 = client.get(
        "/v1/fields/no_such_field/indicator-grid",
        params={"index": "salinity", "date": "latest", "grid": 8},
    )
    assert resp2.status_code == 200
    sim = resp2.json()
    assert sim["real_data"] is False and sim["source"] == "simulation"
    assert required.issubset(sim.keys())
    print(f"(هـ) fallback محاكاة صحيح: real_data={sim['real_data']} source={sim['source']}")

    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    test_clip_index_bounds_and_grid()
