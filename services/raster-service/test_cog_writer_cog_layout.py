"""حارس انحدار ST-01: ما يُعلَن COG يجب أن يكون COG **بنيويّاً** لا مجرّد GTiff مبلّط بأهرامات.

الجذر: ``write_cog``/``write_rgba_cog`` كانا يكتبان GTiff مبلّطاً ثمّ يضيفان الأهرامات
والوسوم **في الموضع** (``build_overviews``/``update_tags`` على الملفّ المفتوح). GDAL يُلحِق
عندها IFDs الأهرامات وبياناتها في ذيل الملفّ ويعيد كتابة IFD الرئيسيّ بعدها ⇒ IFD الرئيسيّ
على بُعد عشرات الكيلوبايتات لا في الرأس، وكتل الدقّة الكاملة **قبل** كتل الأهرامات. الملفّ
يُقرأ، لكنّ قارئ HTTP-range يحتاج جولات إضافيّة لبلوغ الفهرس — وهو بالضبط ما يَعِد به COG.
و``validate_cog`` كان يفحص «مبلّط + له أهرامات» فقط فيشهد ``valid=True`` على ملفّ يرفضه
مدقّق COG مستقلّ (rio-cogeo strict: ستّة أخطاء ترتيب IFD/كتل لكلّ من float32 وRGBA).

الشاهد هنا **مستقلّ عن GDAL**: محلّل بايتات TIFF/BigTIFF صغير يقرأ سلسلة IFDs ومواضع
البلاطات مباشرةً ويفرض قواعد تخطيط COG:
  (1) IFD الأوّل في رأس الملفّ (≤ 300 بايت، بعد منطقة GDAL الشبحيّة إن وُجدت)؛
  (2) كلّ IFDs (صورة + أقنعة + أهرامات) قبل أوّل كتلة بيانات؛
  (3) بيانات الصورة مرتّبة من الهرم الأصغر إلى الدقّة الكاملة (الكاملة آخِراً).
وإن توفّر rio-cogeo (ليس في متطلّبات raster-service؛ متاح محلّيّاً أحياناً) فيُستعمَل
تحقّقاً متقاطعاً إضافيّاً — لا شرط تخطٍّ.
"""

from __future__ import annotations

import struct
from pathlib import Path

import cog_writer
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin

UTM = "EPSG:32638"
SIZE = 1024  # > 512 كي يكون للدقّة الكاملة أكثر من بلاطة وللأهرامات معنى

_TAG_NEW_SUBFILE_TYPE = 254
_TAG_IMAGE_WIDTH = 256
_TAG_TILE_OFFSETS = 324
_TYPE_SIZES = {3: 2, 4: 4, 16: 8}  # SHORT · LONG · LONG8


def _read_ifds(path: str) -> tuple[int, list[dict]]:
    """يحلّل سلسلة IFDs (TIFF كلاسيكيّ أو BigTIFF) ويُرجِع (موضع IFD الأوّل، [IFD…])."""
    data = Path(path).read_bytes()
    bo = {b"II": "<", b"MM": ">"}[data[:2]]
    (magic,) = struct.unpack(bo + "H", data[2:4])
    big = magic == 43
    if big:
        (first,) = struct.unpack(bo + "Q", data[8:16])
        cnt_fmt, cnt_size, ent_size, val_fmt, inline = "Q", 8, 20, "Q", 8
    else:
        (first,) = struct.unpack(bo + "I", data[4:8])
        cnt_fmt, cnt_size, ent_size, val_fmt, inline = "H", 2, 12, "I", 4
    ifds: list[dict] = []
    off = first
    while off:
        (n,) = struct.unpack(bo + cnt_fmt, data[off : off + cnt_size])
        tags: dict[int, list[int]] = {}
        for i in range(n):
            e = off + cnt_size + i * ent_size
            tag, typ = struct.unpack(bo + "HH", data[e : e + 4])
            if tag not in (_TAG_NEW_SUBFILE_TYPE, _TAG_IMAGE_WIDTH, _TAG_TILE_OFFSETS):
                continue
            (count,) = struct.unpack(
                bo + ("Q" if big else "I"), data[e + 4 : e + 4 + (8 if big else 4)]
            )
            vpos = e + 4 + (8 if big else 4)
            size = _TYPE_SIZES[typ]
            if count * size > inline:
                (vpos,) = struct.unpack(bo + val_fmt, data[vpos : vpos + inline])
            fmt = {2: "H", 4: "I", 8: "Q"}[size]
            tags[tag] = list(struct.unpack(bo + fmt * count, data[vpos : vpos + count * size]))
        ifds.append(
            {
                "offset": off,
                "is_mask": bool(tags.get(_TAG_NEW_SUBFILE_TYPE, [0])[0] & 4),
                "width": tags[_TAG_IMAGE_WIDTH][0],
                "tile_offsets": [t for t in tags.get(_TAG_TILE_OFFSETS, []) if t],
            }
        )
        nxt = off + cnt_size + n * ent_size
        (off,) = struct.unpack(bo + val_fmt, data[nxt : nxt + inline])
    return first, ifds


def _independent_cog_layout_errors(path: str) -> list[str]:
    """قواعد تخطيط COG مقيسة من البايتات مباشرةً (لا من GDAL ولا من validate_cog)."""
    first, ifds = _read_ifds(path)
    errors: list[str] = []
    if first > 300:
        errors.append(f"main IFD at byte {first} (> 300): not in header")
    data_start = min(t for ifd in ifds for t in ifd["tile_offsets"])
    for ifd in ifds:
        if ifd["offset"] > data_start:
            errors.append(f"IFD at {ifd['offset']} is after first data block at {data_start}")
    images = sorted((i for i in ifds if not i["is_mask"]), key=lambda i: i["width"])
    if len(images) < 2:
        errors.append("no internal overviews")
    for smaller, larger in zip(images, images[1:], strict=False):
        if min(smaller["tile_offsets"]) > min(larger["tile_offsets"]):
            errors.append(
                f"data of width {larger['width']} precedes data of smaller overview "
                f"width {smaller['width']}"
            )
    return errors


def _rio_cogeo_cross_check(path: str) -> None:
    """تحقّق متقاطع اختياريّ (rio-cogeo ليس تبعيّة raster-service)."""
    try:
        from rio_cogeo.cogeo import cog_validate
    except ImportError:
        return
    valid, errors, _warnings = cog_validate(path, strict=True)
    assert valid, errors


def _float_array() -> np.ndarray:
    rng = np.random.default_rng(7)
    arr = rng.uniform(-0.2, 0.9, (SIZE, SIZE)).astype("float32")
    arr[:, :200] = np.nan  # خارج الحقل ⇒ قناع داخليّ + nodata
    return arr


def _rgba_array() -> np.ndarray:
    rng = np.random.default_rng(11)
    arr = rng.integers(0, 256, (4, SIZE, SIZE), dtype=np.uint8)
    arr[3] = 0
    arr[3, 100:900, 100:900] = 255
    return arr


def _transform():
    return from_origin(393000.0, 1773000.0, 10.0, 10.0)


def test_float_cog_has_cog_byte_layout(tmp_path):
    path = str(tmp_path / "ndvi.tif")
    res = cog_writer.write_cog(_float_array(), path, _transform(), crs=UTM)
    assert res["written"] is True, res
    errors = _independent_cog_layout_errors(path)
    assert errors == [], errors
    _rio_cogeo_cross_check(path)
    assert res["validation"]["valid"] is True, res["validation"]


def test_rgba_cog_has_cog_byte_layout(tmp_path):
    path = str(tmp_path / "truecolor.tif")
    res = cog_writer.write_rgba_cog(_rgba_array(), path, _transform(), crs=UTM)
    assert res["written"] is True, res
    errors = _independent_cog_layout_errors(path)
    assert errors == [], errors
    _rio_cogeo_cross_check(path)
    assert res["validation"]["valid"] is True, res["validation"]


def test_final_cog_keeps_scientific_contract(tmp_path):
    """النسخة النهائيّة لا تُسقط ما كان يحمله الملفّ: أهرامات [2,4,8,16] وطريقتها، nodata،
    القناع الداخليّ، الضغط والتنبّؤ، والقيم العلميّة بلا تغيير."""
    arr = _float_array()
    path = str(tmp_path / "ndvi.tif")
    cog_writer.write_cog(arr, path, _transform(), crs=UTM)
    with rasterio.open(path) as src:
        assert src.overviews(1) == cog_writer.OVERVIEW_LEVELS
        assert src.tags().get("OVR_RESAMPLING_ALG") == "AVERAGE"
        assert src.nodata == cog_writer.DEFAULT_NODATA
        assert src.profile["blockxsize"] == 512 and src.profile["tiled"]
        assert src.tags(ns="IMAGE_STRUCTURE").get("PREDICTOR") == "3"
        assert str(src.profile.get("compress")).lower() == "deflate"
        assert src.dtypes[0] == "float32"
        data = src.read(1)
        mask = src.read_masks(1)
    valid = np.isfinite(arr)
    assert np.array_equal(data[valid], arr[valid])
    assert (mask[~valid] == 0).all() and (mask[valid] == 255).all()

    rgba_path = str(tmp_path / "truecolor.tif")
    rgba = _rgba_array()
    cog_writer.write_rgba_cog(rgba, rgba_path, _transform(), crs=UTM)
    with rasterio.open(rgba_path) as src:
        assert src.overviews(1) == cog_writer.OVERVIEW_LEVELS
        assert src.tags().get("OVR_RESAMPLING_ALG") == "NEAREST"
        assert src.tags(ns="IMAGE_STRUCTURE").get("PREDICTOR") == "2"
        assert np.array_equal(src.read(), rgba)
    # لا بقايا ملفّات وسيطة بجوار الناتج (المجلّد يُنظَّف بمهامّ دورة الحياة بالامتداد).
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ndvi.tif", "truecolor.tif"]


def test_validate_cog_rejects_tiled_gtiff_with_in_place_overviews(tmp_path):
    """المدقّق لا يشهد COG لملفّ مبلّط بأهرامات مضافة في الموضع (الوصفة القديمة نفسها)."""
    path = str(tmp_path / "not_cog.tif")
    arr = _float_array()
    profile = {
        **cog_writer.COG_PROFILE,
        "height": SIZE,
        "width": SIZE,
        "count": 1,
        "crs": UTM,
        "transform": _transform(),
        "nodata": cog_writer.DEFAULT_NODATA,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.nan_to_num(arr, nan=cog_writer.DEFAULT_NODATA), 1)
        dst.build_overviews(cog_writer.OVERVIEW_LEVELS, Resampling.average)
    # الشاهد المستقلّ يرفضه (له أسنان) ⇒ والمدقّق يجب أن يتّفق معه.
    assert _independent_cog_layout_errors(path) != []
    report = cog_writer.validate_cog(path)
    assert report["valid"] is False, report
    assert report["tiled"] is True and report["overviews"] == cog_writer.OVERVIEW_LEVELS
    assert report["errors"], report


def test_validate_cog_missing_file_is_invalid(tmp_path):
    report = cog_writer.validate_cog(str(tmp_path / "missing.tif"))
    assert report["valid"] is False
