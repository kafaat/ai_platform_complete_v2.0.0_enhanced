"""برهان الوصل لـ``IMAGERY-BLANK-THUMBNAIL-01``: ``ensure_field_cog`` لا يُخزِّن فراغاً.

اختبار الدالّة النقيّة وحده لا يكفي — حارس غير موصول يمرّ أخضر ويترك العطل قائماً.
هنا يُقاد **المسار الحقيقيّ** ``raster_cdse_tile_runtime.ensure_field_cog`` بعميل CDSE
يُعيد GeoTIFF **سليم البنية وفارغ البكسلات** (وهو ما تُعيده CDSE فعلاً حين لا يقع مرور
قمر داخل النافذة المطلوبة)، ويُتحقَّق أنّ:

  * النتيجة ``None`` لا مسار ملفّ.
  * ``cdse_tile_cache`` **فارغ** — فلا يُجمَّد الفراغ ساعةً ولا يُستهلَك من الكاش لاحقاً.
  * الملفّ المؤقّت حُذِف — فلا يتسرّب القرص على كلّ طلب فاشل.

وفي المقابل: استجابة تحمل مشاهدة حقيقيّة **تُخزَّن** — كي لا يتحوّل الحارس إلى رفض شامل.

تكذيب مُتحقَّق منه: إزالة فحص المحتوى قبل سطر الكاش تُسقِط
``test_empty_cdse_response_is_not_cached`` فوراً (يصبح الكاش بمدخل واحد).
"""

from __future__ import annotations

import logging

import cdse_singleflight
import numpy as np
import pytest
import raster_cdse_tile_runtime as runtime
from rasterio.transform import from_origin

rasterio = pytest.importorskip("rasterio")

pytestmark = pytest.mark.unit

_BBOX = [44.10, 15.30, 44.12, 15.32]
_LOGGER = logging.getLogger(__name__)


def _geotiff_bytes(values) -> bytes:
    """يُنتج بايتات GeoTIFF حقيقيّة — لا بيانات وهميّة — بقيم المُعطى."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "scene.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=values.shape[0],
            width=values.shape[1],
            count=1,
            dtype="float32",
            crs="EPSG:32638",
            transform=from_origin(500000.0, 2800000.0, 10.0, 10.0),
            nodata=float("nan"),
        ) as dst:
            dst.write(values, 1)
        return path.read_bytes()


class _StubClient:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.calls = 0

    def process_index(self, **_kwargs) -> bytes:
        self.calls += 1
        return self._payload


@pytest.fixture(autouse=True)
def _clean_cache():
    """كاش نظيف قبل/بعد كلّ حالة — الحالة عامّة على مستوى الوحدة."""
    cdse_singleflight.cdse_tile_cache.clear()
    yield
    cdse_singleflight.cdse_tile_cache.clear()


async def _run(monkeypatch, values, date: str = "2026-06-18"):
    return await _run_payload(monkeypatch, _geotiff_bytes(values), date)


async def _run_payload(monkeypatch, payload: bytes, date: str = "2026-06-18"):
    client = _StubClient(payload)
    monkeypatch.setattr(runtime._cdse, "get_client", lambda: client)
    monkeypatch.setattr(runtime._cdse, "is_truecolor", lambda _index: False)
    result = await runtime.ensure_field_cog(
        "fld_test",
        "ndvi",
        date,
        f"{date}T00:00:00Z",
        f"{date}T23:59:59Z",
        _BBOX,
        None,  # بلا هندسة ⇒ لا مسار قناع، فالمقيس هو فحص المحتوى وحده
        False,
        logger=_LOGGER,
    )
    return result, client


@pytest.mark.asyncio
async def test_empty_cdse_response_is_not_cached(monkeypatch, tmp_path):
    """استجابة ٢٠٠ بمحتوى كلّه NaN ⇒ لا نتيجة ولا مدخل كاش."""
    empty = np.full((32, 32), np.nan, dtype="float32")
    result, client = await _run(monkeypatch, empty)

    assert client.calls == 1, "يجب أن تُستدعى CDSE فعلاً (المقيس هو ما بعدها)"
    assert result is None, "الفراغ لا يُعاد كـCOG صالح"
    assert cdse_singleflight.cdse_tile_cache == {}, (
        "فراغ مُخزَّن ⇒ يُجمَّد ساعةً ويُستهلَك بلا إعادة سؤال — هذا هو العطل نفسه"
    )


@pytest.mark.asyncio
async def test_empty_response_does_not_leak_a_temp_file(monkeypatch):
    """الملفّ المؤقّت للفراغ يُحذَف — لا تسريب قرص على كلّ طلب بلا مشاهدة."""
    import os
    import tempfile

    before = set(os.listdir(tempfile.gettempdir()))
    await _run(monkeypatch, np.full((32, 32), np.nan, dtype="float32"))
    leaked = {
        name
        for name in set(os.listdir(tempfile.gettempdir())) - before
        if name.startswith("cdse_fld_test")
    }
    assert not leaked, f"ملفّات مؤقّتة متسرّبة: {leaked}"


@pytest.mark.asyncio
async def test_a_real_observation_is_still_cached(monkeypatch):
    """الاتّجاه المقابل: مشاهدة حقيقيّة تُخزَّن — الحارس ليس رفضاً شاملاً."""
    values = np.full((32, 32), 0.44, dtype="float32")
    result, _client = await _run(monkeypatch, values)

    assert result is not None, "مشاهدة صالحة يجب أن تُعاد"
    assert len(cdse_singleflight.cdse_tile_cache) == 1, "المشاهدة الصالحة تُخزَّن كالمعتاد"


@pytest.mark.asyncio
async def test_a_corrupt_response_is_not_cached(monkeypatch):
    """بايتات ليست GeoTIFF أصلاً ⇒ لا نتيجة ولا كاش على المسار الموصول.

    بقيّة الحالات تُغذّي ملفّات **سليمة البنية** فتقيس فرع «قرأتُ ولم أجد مشاهدة»؛
    هنا يفشل الفتح نفسه.

    **حدّ مقيس، لا مُفترَض:** هذه الحالة **لا** تحرس مظروف ``try/except`` حول فحص
    المحتوى داخل ``ensure_field_cog`` — إزالته تُبقيها خضراء، لأنّ ``except`` الخارجيّ
    للدالّة يبتلع الاستثناء ويُعيد ``None`` على أيّ حال (مُثبَت بالتكذيب). ما تحرسه
    فعلاً: أنّ فشل الفتح لا ينتهي بمدخل كاش. الفشل المفتوح في الفحص نفسه يُمسَك في
    ``test_unreadable_file_is_not_observable``.
    """
    result, client = await _run_payload(monkeypatch, b"II*\x00 not a real tiff")

    assert client.calls == 1
    assert result is None
    assert cdse_singleflight.cdse_tile_cache == {}


@pytest.mark.asyncio
async def test_a_single_valid_pixel_still_counts_as_an_observation(monkeypatch):
    """الحدّ الأدنى مشاهدة واحدة — لا عتبة تغطية مُخفاة داخل حارس الكاش."""
    values = np.full((32, 32), np.nan, dtype="float32")
    values[3, 9] = 0.21
    result, _client = await _run(monkeypatch, values)

    assert result is not None
    assert len(cdse_singleflight.cdse_tile_cache) == 1
