"""EXTRA-10 (نطاق المراجعة): المسار العدديّ ``process_precomputed_pixels`` يفحص الحجم قبل القراءة.

نظيره ``process_precomputed_truecolor`` يستدعي ``assert_readable_size`` قبل ``src.read()``؛
والعدديّ كان يقرأ النطاق كاملاً (``src.read(1, masked=True)``) بلا سقف — على رابطٍ يقبله
``safe_raster_source`` من أيّ مصدر ``http(s)`` غير محجوب. الرفض المُعلَن (413) يجب أن
يسبق أيّ تخصيص، في الفرعَين: الإرث أحاديّ النطاق، والمنتَج الأصليّ (native) رباعيّ النطاقات.
"""

from __future__ import annotations

import numpy as np
import pytest
import raster_settings
import rasterio
from fastapi import HTTPException
from raster_api_models import ProcessRequest
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit

W, H = 12, 10


def _write_single_band(path):
    data = np.linspace(0.1, 0.8, W * H, dtype="float32").reshape(H, W)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=H,
        width=W,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(44, 15, 0.001, 0.001),
    ) as dst:
        dst.write(data, 1)
    return str(path)


def _request(path):
    return ProcessRequest(
        tenant_id="",
        field_id="f",
        raster_url=path,
        indicator="ndvi",
        source_format="sentinel2_l2a",
        bands={},
        provider="cdse",
        precomputed_index=True,
    )


@pytest.fixture
def reads(monkeypatch):
    """يسجّل كلّ ``read``/``read_masks`` مرئيّ من بايثون — الرفض يجب أن يسبقها كلّها."""
    calls = []
    for name in ("read", "read_masks"):
        original = getattr(rasterio.io.DatasetReader, name)

        def wrapper(self, *args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(rasterio.io.DatasetReader, name, wrapper)
    return calls


def test_oversized_scalar_precomputed_raster_is_refused_before_any_read(
    tmp_path, monkeypatch, reads
):
    from raster_processing_runtime import process_precomputed_pixels

    path = _write_single_band(tmp_path / "index.tif")
    monkeypatch.setattr(raster_settings, "RASTER_MAX_READ_BAND_PIXELS", W * H - 1)
    with pytest.raises(HTTPException) as exc:
        process_precomputed_pixels(_request(path), "layer", upload_dir=str(tmp_path))
    assert exc.value.status_code == 413, exc.value.detail
    assert reads == [], f"الرفض جاء بعد التخصيص: {reads}"


def test_scalar_precomputed_raster_at_the_ceiling_still_processes(tmp_path, monkeypatch):
    """حارسٌ يرفض الجميع لا يقيس شيئاً: السقف مساوٍ للحجم يمرّ ويُنتج إحصاءً."""
    from raster_processing_runtime import process_precomputed_pixels

    path = _write_single_band(tmp_path / "index.tif")
    monkeypatch.setattr(raster_settings, "RASTER_MAX_READ_BAND_PIXELS", W * H)
    stats, _, _, _ = process_precomputed_pixels(_request(path), "layer", upload_dir=str(tmp_path))
    assert stats["valid_pixels"] == W * H


def test_oversized_native_product_is_refused_before_any_read(tmp_path, monkeypatch, reads):
    """الفرع الأصليّ يمرّ بالحارس نفسه (حدّه الخاصّ 2500×2500 لا يتبع السقف المُعلَن)."""
    from raster_processing_runtime import process_precomputed_pixels
    from test_cdse_native_product import request

    req, _ = request(tmp_path)  # 10×10×4 = 400 بكسل-نطاق
    monkeypatch.setattr(raster_settings, "RASTER_MAX_READ_BAND_PIXELS", 10 * 10 * 4 - 1)
    with pytest.raises(HTTPException) as exc:
        process_precomputed_pixels(req, "layer", upload_dir=str(tmp_path))
    assert exc.value.status_code == 413, exc.value.detail
    assert reads == [], f"الرفض جاء بعد التخصيص: {reads}"
