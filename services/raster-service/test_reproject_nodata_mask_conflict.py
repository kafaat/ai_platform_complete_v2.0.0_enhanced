"""حارس انحدار: تعارض ``src_nodata`` مع قناع مجموعة البيانات في إعادة الإسقاط.

الجذر: عند إعادة إسقاط COG يملك قناعاً داخليّاً (per-dataset mask) بينما نمرّر
``src_nodata`` إلى ``rasterio.warp.reproject``، يُطلِق GDAL تحذيراً متكرّراً:

    "Source dataset has both a per-dataset mask band and the warper has been also
     configured with a source nodata value. Only taking into account the latter
     (i.e. ignoring the per-dataset mask band)"

يُطلَق مرّة لكلّ عمليّة warp (عدّة مرّات لكلّ بلاطة) فيُغرِق السجلّات. الإصلاح:
حين يملك المصدر قناعاً، لا نمرّر ``src_nodata`` ونعتمد على القناع (المُعاد تطبيقه
عبر ``_reproject_dataset_mask``) — نفس التقنيع، بلا تحذير. COGs بلا قناع تبقى
تعتمد على ``src_nodata``. نقيّة بلا شبكة.
"""

from __future__ import annotations

import logging
import os
import tempfile

import cog_writer
import numpy as np
import pytest
import rasterio
import tile_render
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit

UTM = "EPSG:32638"
ORIGIN_X = 393000.0
ORIGIN_Y = 1773000.0
RES = 10.0
SIZE = 512


def _write_masked_cog(path: str) -> None:
    """COG بقناع داخلي (النصف الأيسر NaN، الأيمن صالح) عبر write_cog."""
    arr = np.full((SIZE, SIZE), np.nan, dtype="float32")
    arr[:, SIZE // 2 :] = 0.7
    transform = from_origin(ORIGIN_X, ORIGIN_Y, RES, RES)
    res = cog_writer.write_cog(arr, path, transform, crs=UTM)
    assert res.get("written") is True, res


def _write_plain_cog(path: str) -> None:
    """COG بلا قناع per-dataset: كلّ البكسلات صالحة (all_valid) + nodata رقميّ."""
    arr = np.full((SIZE, SIZE), 0.5, dtype="float32")
    transform = from_origin(ORIGIN_X, ORIGIN_Y, RES, RES)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=SIZE,
        width=SIZE,
        count=1,
        dtype="float32",
        crs=UTM,
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(arr, 1)


def test_has_per_dataset_mask_true_for_masked_cog():
    tmp = tempfile.mkdtemp(prefix="maskprobe_")
    path = os.path.join(tmp, "masked.tif")
    _write_masked_cog(path)
    with rasterio.open(path) as src:
        assert tile_render._has_per_dataset_mask(src) is True


def test_has_per_dataset_mask_false_for_plain_cog():
    tmp = tempfile.mkdtemp(prefix="maskprobe2_")
    path = os.path.join(tmp, "plain.tif")
    _write_plain_cog(path)
    with rasterio.open(path) as src:
        # all_valid فقط (لا per-dataset) → نُبقي src_nodata.
        assert tile_render._has_per_dataset_mask(src) is False


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record):  # noqa: D401 — يجمع نصّ كلّ سجلّ
        self.messages.append(record.getMessage())


def test_render_masked_cog_emits_no_nodata_mask_conflict_warning():
    """تصيير COG مُقنَّع لا يُطلِق تحذير GDAL 'per-dataset mask band … source nodata value'.

    التحذير يمرّ عبر مُسجّل rasterio (``rasterio._env``) لا عبر ``warnings``؛ نلتقط
    سجلّاته ونؤكّد خُلوّها من سطر التعارض.
    """
    tmp = tempfile.mkdtemp(prefix="maskwarn_")
    path = os.path.join(tmp, "masked.tif")
    _write_masked_cog(path)

    from rasterio.warp import transform_bounds

    bounds_utm = (ORIGIN_X, ORIGIN_Y - SIZE * RES, ORIGIN_X + SIZE * RES, ORIGIN_Y)
    b4 = transform_bounds(UTM, "EPSG:4326", *bounds_utm)
    clon = (b4[0] + b4[2]) / 2.0
    clat = (b4[1] + b4[3]) / 2.0
    z = 14
    tx, ty = tile_render._lonlat_to_tile(clon, clat, z)

    rio_logger = logging.getLogger("rasterio")
    handler = _CaptureHandler()
    prev_level = rio_logger.level
    rio_logger.setLevel(logging.DEBUG)
    rio_logger.addHandler(handler)
    try:
        png = tile_render.render_tile_png(path, z, tx, ty, "ndvi")
    finally:
        rio_logger.removeHandler(handler)
        rio_logger.setLevel(prev_level)

    assert png is not None
    offending = [
        m for m in handler.messages if "per-dataset mask band" in m and "source nodata" in m
    ]
    assert not offending, f"تحذير التعارض ما زال يُطلَق: {offending}"
