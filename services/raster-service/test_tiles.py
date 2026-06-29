"""
test_tiles.py — تحقّق ذاتيّ (synthetic) لبلاطات XYZ الديناميكيّة (TiTiler-style).

البيئة هنا تحجب الشبكة، لذا نبني COG صناعيّاً في الذاكرة/قرص مؤقّت بـUTM
ونسجّل طبقة لحقل اختباري، ثمّ عبر TestClient نتحقّق:
  (أ) بلاطة تتقاطع حدودها (3857) مع بيانات الحقل → PNG يفكّ تشفيره وفيه
      بكسلات غير شفّافة (alpha>0) بألوان معقولة (تدرّج NDVI: أخضر للقيم العالية).
  (ب) بلاطة بعيدة خارج الحقل → PNG شفّاف تماماً (كلّ alpha=0).
  (ج) /tilejson صالح: فيه tiles[] وbounds وminzoom/maxzoom.
"""

import io
import os
import struct
import tempfile
import zlib

import main
import numpy as np
import rasterio
import tile_render
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

# الجوف (اليمن) ضمن UTM zone 38N
UTM = "EPSG:32638"
ORIGIN_X = 393000.0  # easting (أعلى يسار)
ORIGIN_Y = 1773000.0  # northing
RES = 10.0  # 10 م/بكسل (Sentinel-2)
W = H = 100


def _make_synthetic_cog(path: str):
    """يكتب COG صناعي أحادي النطاق بـNDVI معروف (0.7 ثابت) في UTM.

    NDVI=0.7 يقع في الجزء الأخضر من التدرّج (نبات قويّ). يُرجِع حدود COG بـ4326.
    """
    ndvi = np.full((H, W), 0.7, dtype="float32")
    transform = from_origin(ORIGIN_X, ORIGIN_Y, RES, RES)
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": H,
        "width": W,
        "crs": UTM,
        "transform": transform,
        "nodata": float("nan"),
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(ndvi, 1)
    from rasterio.warp import transform_bounds

    left, right = ORIGIN_X, ORIGIN_X + W * RES
    top, bottom = ORIGIN_Y, ORIGIN_Y - H * RES
    bounds_4326 = list(transform_bounds(UTM, "EPSG:4326", left, bottom, right, top))
    return bounds_4326


def _decode_png_rgba(png_bytes: bytes) -> np.ndarray:
    """يفكّ تشفير PNG (RGBA، color type 6، filter 0) بـzlib — بلا PIL.

    يدعم تحديداً المخرجات من tile_render.encode_png_rgba (filter=0 لكلّ صفّ).
    """
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n", "ليس PNG"
    pos = 8
    width = height = None
    idat = bytearray()
    while pos < len(png_bytes):
        (length,) = struct.unpack(">I", png_bytes[pos : pos + 4])
        tag = png_bytes[pos + 4 : pos + 8]
        data = png_bytes[pos + 8 : pos + 8 + length]
        if tag == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
            assert bit_depth == 8 and color_type == 6, "متوقّع 8-bit RGBA"
        elif tag == b"IDAT":
            idat.extend(data)
        elif tag == b"IEND":
            break
        pos += 12 + length
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    out = np.zeros((height, width, 4), dtype=np.uint8)
    rp = 0
    for r in range(height):
        ftype = raw[rp]
        assert ftype == 0, f"filter type {ftype} غير مدعوم (متوقّع 0)"
        rp += 1
        row = np.frombuffer(raw[rp : rp + stride], dtype=np.uint8)
        out[r] = row.reshape(width, 4)
        rp += stride
    return out


def test_dynamic_tiles():
    tmpdir = tempfile.mkdtemp(prefix="tile_test_")
    cog_path = os.path.join(tmpdir, "ndvi_cog.tif")
    bounds_4326 = _make_synthetic_cog(cog_path)
    print(f"COG bounds_4326: {[round(b, 5) for b in bounds_4326]}")

    # سجّل طبقة لحقل اختباري (كما يفعل _run_processing)
    main._layers["tile_layer"] = {
        "layer_id": "tile_layer",
        "field_id": "field_tiles",
        "index": "ndvi",
        "cog_url": f"file://{cog_path}",
        "acquisition_date": "2026-05-01T08:30:00Z",
        "created_at": "2026-05-01T09:00:00Z",
        "source_format": "sentinel2_l2a",
        "bounds_4326": bounds_4326,
    }
    main._field_layers.setdefault("field_tiles", []).append("tile_layer")

    client = TestClient(main.app)

    # ── احسب z/x/y لبلاطة تغطّي مركز الحقل ──────────────────────────
    minlon, minlat, maxlon, maxlat = bounds_4326
    clon = (minlon + maxlon) / 2.0
    clat = (minlat + maxlat) / 2.0
    z = 14
    tx, ty = tile_render._lonlat_to_tile(clon, clat, z)
    print(f"بلاطة مركز الحقل: z={z} x={tx} y={ty}")

    # ── (أ) بلاطة فوق الحقل → بكسلات غير شفّافة بألوان معقولة ─────────
    resp = client.get(
        f"/v1/fields/field_tiles/tiles/{z}/{tx}/{ty}.png",
        params={"index": "ndvi", "date": "latest"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/png"
    rgba = _decode_png_rgba(resp.content)
    assert rgba.shape == (256, 256, 4), f"شكل غير متوقّع: {rgba.shape}"
    alpha = rgba[..., 3]
    n_opaque = int((alpha > 0).sum())
    assert n_opaque > 0, "متوقّع بكسلات غير شفّافة فوق الحقل"
    # ألوان معقولة: NDVI=0.7 → الجزء الأخضر (green > red للبكسلات المعتمة)
    opaque = alpha > 0
    mean_r = float(rgba[..., 0][opaque].mean())
    mean_g = float(rgba[..., 1][opaque].mean())
    mean_b = float(rgba[..., 2][opaque].mean())
    assert mean_g > mean_b, f"متوقّع لون مائل للأخضر (g>{mean_b}), وجد g={mean_g}"
    print(
        f"(أ) بلاطة فوق الحقل: opaque={n_opaque}/65536 "
        f"لون متوسّط RGB=({mean_r:.0f},{mean_g:.0f},{mean_b:.0f})"
    )

    # ── (ب) بلاطة بعيدة خارج الحقل → شفّافة تماماً ───────────────────
    fx, fy = tile_render._lonlat_to_tile(clon + 10.0, clat + 10.0, z)
    resp_out = client.get(
        f"/v1/fields/field_tiles/tiles/{z}/{fx}/{fy}.png",
        params={"index": "ndvi", "date": "latest"},
    )
    assert resp_out.status_code == 200, resp_out.text
    rgba_out = _decode_png_rgba(resp_out.content)
    assert int((rgba_out[..., 3] > 0).sum()) == 0, "متوقّع بلاطة شفّافة تماماً خارج الحقل"
    print(f"(ب) بلاطة خارج الحقل (z={z} x={fx} y={fy}): شفّافة تماماً (alpha كلّه=0)")

    # ── (ج) TileJSON صالح ────────────────────────────────────────────
    tj = client.get("/v1/fields/field_tiles/tilejson", params={"index": "ndvi", "date": "latest"})
    assert tj.status_code == 200, tj.text
    body = tj.json()
    assert body["tilejson"] == "2.2.0"
    assert isinstance(body["tiles"], list) and len(body["tiles"]) >= 1
    assert "/v1/fields/field_tiles/tiles/" in body["tiles"][0]
    assert "{z}" in body["tiles"][0] and "{x}" in body["tiles"][0] and "{y}" in body["tiles"][0]
    assert isinstance(body["bounds"], list) and len(body["bounds"]) == 4
    assert body["minzoom"] < body["maxzoom"]
    assert isinstance(body["center"], list) and len(body["center"]) == 3
    # bounds تطابق حدود COG (لا حدود افتراضيّة)
    assert abs(body["bounds"][0] - round(minlon, 6)) < 1e-3, body["bounds"]
    print(
        f"(ج) TileJSON صالح: tiles={body['tiles']} "
        f"bounds={body['bounds']} zoom={body['minzoom']}-{body['maxzoom']}"
    )

    # ── (د) حقل بلا COG → بلاطة شفّافة لا 500 ─────────────────────────
    resp_none = client.get(f"/v1/fields/no_such_field/tiles/{z}/{tx}/{ty}.png")
    assert resp_none.status_code == 200
    rgba_none = _decode_png_rgba(resp_none.content)
    assert int((rgba_none[..., 3] > 0).sum()) == 0
    print("(د) حقل بلا COG: بلاطة شفّافة (لا 500)")

    print("\nALL TILE ASSERTIONS PASSED")


def test_render_tile_honors_internal_mask_when_pixels_are_finite_zero():
    """القناع الداخلي يجب أن يُخفي بكسلات finite (مثل 0.0) خارج حدود القصّ/dataMask.

    قبل الإصلاح: renderer كان يعتمد على nodata فقط → بكسلات خارج الحقل بقيمة 0.0
    تُعتبر صالحة → colorize يعطيها alpha=255 → شرائط داكنة فوق الخريطة.
    بعد الإصلاح: dataset_mask() يُسقَط إلى شبكة البلاطة → mask=0 → NaN → alpha=0.

    حارس غير فارغ (non-vacuous): الحقل ٥١٢بكسل (≈٥٫١كم) **أكبر** من بلاطة z14
    (≈٢٫٤كم)، فالبلاطة المركزيّة تقع **بالكامل داخل** بصمة الحقل — وعليه فكلّ بكسل
    شفّاف يأتي حتماً من النصف المُقنَّع (finite 0.0, mask=0)، لا من خارج البصمة. بهذا
    يفشل الاختبار فعليّاً لو عاد المصيّر يتجاهل القناع: النصف السفلي يصير معتماً
    ⇒ shfّاف=0. (لو كان الحقل أصغر من البلاطة لكانت الشفافيّة خارج-البصمة كافيةً
    لإنجاح التوكيد بلا إصلاح — اختبارٌ فارغ.)
    """
    import tempfile

    import rasterio

    # بنِ COG بنطاقين من البكسلات:
    #   نصف علوي: قيم NDVI صالحة (0.7) مع mask=255
    #   نصف سفلي: قيم finite (0.0) لكن mask=0 (خارج dataMask/القصّ)
    tmpdir = tempfile.mkdtemp(prefix="mask_test_")
    cog_path = os.path.join(tmpdir, "masked_cog.tif")

    # ٥١٢بكسل×١٠م ≈ ٥٫١كم > بلاطة z14 (~٢٫٤كم): شرطٌ لازم لجعل الحارس غير فارغ.
    size = 512
    data = np.zeros((size, size), dtype="float32")
    data[: size // 2, :] = 0.7  # نصف علوي: NDVI صالح
    # النصف السفلي يبقى 0.0 (finite لكن خارج القناع)

    # قناع: النصف العلوي صالح (255)، السفلي غير صالح (0)
    mask = np.zeros((size, size), dtype="uint8")
    mask[: size // 2, :] = 255

    transform = from_origin(ORIGIN_X, ORIGIN_Y, RES, RES)
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": size,
        "width": size,
        "crs": UTM,
        "transform": transform,
        # nodata مضبوط على قيمة مختلفة عن 0.0 عمداً — لإثبات أنّ الإصلاح لا يعتمد على nodata
        "nodata": -9999.0,
    }
    with rasterio.open(cog_path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.write_mask(mask)

    # احسب بلاطة تغطّي مجال الـCOG كاملاً
    from rasterio.warp import transform_bounds

    bounds_utm = (
        ORIGIN_X,
        ORIGIN_Y - size * RES,
        ORIGIN_X + size * RES,
        ORIGIN_Y,
    )
    bounds_4326 = transform_bounds(UTM, "EPSG:4326", *bounds_utm)
    clon = (bounds_4326[0] + bounds_4326[2]) / 2.0
    clat = (bounds_4326[1] + bounds_4326[3]) / 2.0

    z = 14
    tx, ty = tile_render._lonlat_to_tile(clon, clat, z)
    png = tile_render.render_tile_png(cog_path, z, tx, ty, "ndvi")
    assert png is not None, "render_tile_png أرجع None — خطأ في التصيير"

    rgba = _decode_png_rgba(png)
    alpha = rgba[..., 3]

    n_transparent = int((alpha == 0).sum())
    n_opaque = int((alpha > 0).sum())

    # شرط عدم-الفراغ: البلاطة داخل بصمة الحقل بالكامل ⇒ شبه كلّ البكسلات إمّا معتمة
    # (نصف صالح) أو شفّافة-من-القناع (نصف مُقنَّع)، بلا فجوة خارج-بصمة كبيرة. لو سقط
    # هذا فالهندسة لم تعد تعزل القناع والاختبار يفقد قيمته.
    coverage = (n_transparent + n_opaque) / alpha.size
    assert coverage > 0.97, (
        f"البلاطة ليست داخل بصمة الحقل بالكامل (تغطية={coverage:.2f}) — "
        "الحارس يفقد قيمته (شفافيّة خارج-البصمة قد تُنجِح التوكيد بلا إصلاح)"
    )

    # النصف السفلي (finite 0.0, mask=0) يجب أن يكون شفّافاً — وإذ البلاطة داخل البصمة
    # فهذه شفافيّةٌ من القناع حصراً. تساوي صفراً ⇒ القناع غير مطبَّق ⇒ شرائط داكنة.
    assert n_transparent > 0, (
        "بكسلات finite (0.0) خارج القناع ظهرت معتمة فوق حقل تقع البلاطة داخله "
        "بالكامل — القناع الداخلي غير مطبَّق (عرض الشرائط الداكنة)"
    )
    # النصف العلوي (NDVI=0.7, mask=255) يجب أن يكون معتماً.
    assert n_opaque > 0, "متوقّع بكسلات معتمة (NDVI=0.7) لكن لا شيء — خطأ في التصيير"

    print(
        f"test_internal_mask: opaque={n_opaque} transparent={n_transparent} "
        f"coverage={coverage:.3f} — القناع الداخلي مطبَّق صحيحاً (حارس غير فارغ)"
    )


if __name__ == "__main__":
    test_dynamic_tiles()


def test_field_layer_date_and_index_selection_is_strict():
    """Timeline/index switching guard:

    - requesting a missing date must not fall back to latest
    - latest must be latest acquisition_date, not merely latest created_at
    - index switch must select the requested indicator only
    """
    tmpdir = tempfile.mkdtemp(prefix="field_layer_strict_")
    cog_old = os.path.join(tmpdir, "ndvi_old.tif")
    cog_new = os.path.join(tmpdir, "ndvi_new.tif")
    cog_msi = os.path.join(tmpdir, "msi_new.tif")
    bounds = _make_synthetic_cog(cog_old)
    _make_synthetic_cog(cog_new)
    _make_synthetic_cog(cog_msi)

    field = "field_strict_dates"
    for lid in list(main._field_layers.get(field, [])):
        main._layers.pop(lid, None)
    main._field_layers[field] = []

    # أقدم acquisition لكنه أحدث created_at: يجب ألا يفوز في latest.
    main._layers["strict_ndvi_old"] = {
        "layer_id": "strict_ndvi_old",
        "field_id": field,
        "index": "ndvi",
        "cog_url": f"file://{cog_old}",
        "acquisition_date": "2026-05-01T08:30:00Z",
        "created_at": "2026-06-01T09:00:00Z",
        "source_format": "sentinel2_l2a",
        "bounds_4326": bounds,
    }
    main._layers["strict_ndvi_new"] = {
        "layer_id": "strict_ndvi_new",
        "field_id": field,
        "index": "ndvi",
        "cog_url": f"file://{cog_new}",
        "acquisition_date": "2026-05-20T08:30:00Z",
        "created_at": "2026-05-20T09:00:00Z",
        "source_format": "sentinel2_l2a",
        "bounds_4326": bounds,
    }
    main._layers["strict_msi_new"] = {
        "layer_id": "strict_msi_new",
        "field_id": field,
        "index": "msi",
        "cog_url": f"file://{cog_msi}",
        "acquisition_date": "2026-05-20T08:30:00Z",
        "created_at": "2026-05-20T09:10:00Z",
        "source_format": "sentinel2_l2a",
        "bounds_4326": bounds,
    }
    main._field_layers[field].extend(["strict_ndvi_old", "strict_ndvi_new", "strict_msi_new"])

    latest = main._find_field_layer(field, "ndvi", "latest")
    assert latest and latest["layer_id"] == "strict_ndvi_new"

    exact_old = main._find_field_layer(field, "ndvi", "2026-05-01")
    assert exact_old and exact_old["layer_id"] == "strict_ndvi_old"

    missing = main._find_field_layer(field, "ndvi", "2026-05-09")
    assert missing is None, "missing date must not silently render latest imagery"

    msi = main._find_field_layer(field, "msi", "latest")
    assert msi and msi["layer_id"] == "strict_msi_new"

    client = TestClient(main.app)
    tj_missing = client.get(
        f"/v1/fields/{field}/tilejson", params={"index": "ndvi", "date": "2026-05-09"}
    )
    assert tj_missing.status_code == 200, tj_missing.text
    body = tj_missing.json()
    assert body["available"] is False

    z = 14
    minlon, minlat, maxlon, maxlat = bounds
    tx, ty = tile_render._lonlat_to_tile((minlon + maxlon) / 2.0, (minlat + maxlat) / 2.0, z)
    tile_missing = client.get(
        f"/v1/fields/{field}/tiles/{z}/{tx}/{ty}.png",
        params={"index": "ndvi", "date": "2026-05-09"},
    )
    assert tile_missing.status_code == 200
    rgba = _decode_png_rgba(tile_missing.content)
    assert int((rgba[..., 3] > 0).sum()) == 0, "missing date must render transparent tile"
