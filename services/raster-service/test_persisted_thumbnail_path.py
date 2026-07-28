"""معيار قبول ``IMAGERY-BLANK-THUMBNAIL-01``: بطاقة جاهزة تُقرأ من الأصل المُدَام حصراً.

المسار قبل هذه الشريحة: البطاقة تُعلن ``has_cog=true`` (مُشتَقّ في SQL من وجود
``cog_uri`` غير فارغ) ثمّ يبني رابطها نقطةً **تُعيد تنفيذ اكتشاف حيّ** عبر
``ensure_field_cog``. أثران لذلك: نداء CDSE لكلّ بطاقة جاهزة، والأخطر — أنّ توسيع
نافذة البحث (المقترَح لعلاج الفراغ) كان سيسمح بعرض **مشهد تاريخ آخر** تحت التاريخ
المطلوب، وهو خرق نَسَب لا يُصلحه امتلاء الصورة.

لذلك المقيس هنا سلوكيّ لا شكليّ: ``source=persisted`` يجب أن يُنتج **صفر نداء CDSE**
في كلّ فرع — النجاح والغياب والتلف على السواء — وأن يُعلن حالته في ``X-Imagery-State``
بدل تمرير فراغ صامت.

تكذيب مُتحقَّق منه: إعادة توجيه الفرع إلى المسار الحيّ تُسقِط
``test_missing_asset_never_falls_back_to_cdse`` فوراً.
"""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin

rasterio = pytest.importorskip("rasterio")

pytestmark = pytest.mark.unit


@pytest.fixture
def ready_cog(tmp_path):
    """COG مُدَام حقيقيّ على القرص بقيم صالحة."""
    path = tmp_path / "persisted_ndvi.tif"
    values = np.full((32, 32), 0.55, dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=32,
        width=32,
        count=1,
        dtype="float32",
        crs="EPSG:32638",
        transform=from_origin(500000.0, 2800000.0, 10.0, 10.0),
        nodata=float("nan"),
    ) as dst:
        dst.write(values, 1)
    return str(path)


@pytest.fixture
def router_module(monkeypatch):
    """يحمّل الراوتر ويقطع كلّ منافذ CDSE — أيّ استدعاء يُفشِل الاختبار صراحةً."""
    import object_store
    import raster_cdse_tile_runtime as runtime
    from routers import cdse_tiles

    calls: list[str] = []

    def _forbidden(*_args, **_kwargs):
        calls.append("cdse")
        raise AssertionError("المسار المُدَام نادى CDSE — خرق للعقد")

    monkeypatch.setattr(runtime, "ensure_field_cog", _forbidden)
    monkeypatch.setattr(cdse_tiles._cdse_rt, "ensure_field_cog", _forbidden)
    monkeypatch.setattr(cdse_tiles._cdse, "get_client", _forbidden)
    monkeypatch.setattr(cdse_tiles, "_require_field", _noop_async)
    monkeypatch.setattr(object_store, "exists_locally", lambda uri: bool(uri))
    return cdse_tiles, calls


async def _noop_async(*_args, **_kwargs):
    return None


def _asset(cog_url: str, acquisition_date: str = "2026-06-18"):
    async def _fetch(*_args, **_kwargs):
        return {"cog_url": cog_url, "acquisition_date": acquisition_date}

    return _fetch


@pytest.mark.asyncio
async def test_ready_card_renders_from_the_persisted_asset(monkeypatch, router_module, ready_cog):
    """أصل جاهز ⇒ PNG حقيقيّ + حالة ready + تاريخ التقاط مُعلَن، بلا نداء CDSE."""
    cdse_tiles, calls = router_module
    monkeypatch.setattr(cdse_tiles._db, "fetch_latest_asset", _asset(ready_cog))

    response = await cdse_tiles.field_cdse_thumbnail(
        "fld_x", index="ndvi", date="2026-06-18", size=160, source="persisted"
    )

    assert calls == [], "صفر نداء CDSE هو الشرط الحاسم"
    assert response.status_code == 200
    assert response.headers["X-Imagery-State"] == "ready"
    assert response.headers["X-Acquisition-Date"] == "2026-06-18"
    assert response.media_type == "image/png"
    assert len(response.body) > 100, "PNG حقيقيّ لا صورة شفّافة"


@pytest.mark.asyncio
async def test_missing_asset_never_falls_back_to_cdse(monkeypatch, router_module):
    """لا أصل ⇒ unavailable مُعلَنة — لا اشتقاق حيّ ولا مشهد بديل."""
    cdse_tiles, calls = router_module

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(cdse_tiles._db, "fetch_latest_asset", _none)

    response = await cdse_tiles.field_cdse_thumbnail(
        "fld_x", index="ndvi", date="2026-06-18", size=160, source="persisted"
    )

    assert calls == [], "الغياب لا يُبرّر نداءً حيّاً"
    assert response.status_code == 404, "‏<img> لا يقرأ الترويسات — 404 هي الإشارة الوحيدة"
    assert response.headers["X-Imagery-State"] == "unavailable"


@pytest.mark.asyncio
async def test_asset_row_without_file_on_disk_is_unavailable(monkeypatch, router_module):
    """القاعدة تقول ready والملفّ غائب ⇒ ادّعاء بلا أصل ⇒ يُعلَن (BUG-1A مرئيّاً)."""
    import object_store

    cdse_tiles, calls = router_module
    monkeypatch.setattr(cdse_tiles._db, "fetch_latest_asset", _asset("/gone/asset.tif"))
    monkeypatch.setattr(object_store, "exists_locally", lambda _uri: False)

    response = await cdse_tiles.field_cdse_thumbnail(
        "fld_x", index="ndvi", date="2026-06-18", size=160, source="persisted"
    )

    assert calls == []
    assert response.status_code == 404, "‏<img> لا يقرأ الترويسات — 404 هي الإشارة الوحيدة"
    assert response.headers["X-Imagery-State"] == "unavailable"


@pytest.mark.asyncio
async def test_corrupt_persisted_asset_is_unavailable_not_blank(
    monkeypatch, router_module, tmp_path
):
    """أصل تالف ⇒ unavailable مع تاريخه — لا يُقدَّم كبطاقة جاهزة فارغة."""
    cdse_tiles, calls = router_module
    corrupt = tmp_path / "corrupt.tif"
    corrupt.write_bytes(b"II*\x00 not a tiff")
    monkeypatch.setattr(cdse_tiles._db, "fetch_latest_asset", _asset(str(corrupt)))

    response = await cdse_tiles.field_cdse_thumbnail(
        "fld_x", index="ndvi", date="2026-06-18", size=160, source="persisted"
    )

    assert calls == []
    assert response.status_code == 404, "‏<img> لا يقرأ الترويسات — 404 هي الإشارة الوحيدة"
    assert response.headers["X-Imagery-State"] == "unavailable"
    assert response.headers["X-Acquisition-Date"] == "2026-06-18"


@pytest.mark.asyncio
async def test_the_requested_date_reaches_the_asset_query_unwidened(
    monkeypatch, router_module, ready_cog
):
    """التاريخ المطلوب يصل الاستعلام كما هو — لا توسيع نافذة داخل مسار العرض."""
    cdse_tiles, _calls = router_module
    seen: dict = {}

    async def _capture(field_id, index_name, date=None, tenant_id=None):
        seen["date"] = date
        seen["index"] = index_name
        return {"cog_url": ready_cog, "acquisition_date": "2026-06-18"}

    monkeypatch.setattr(cdse_tiles._db, "fetch_latest_asset", _capture)

    await cdse_tiles.field_cdse_thumbnail(
        "fld_x", index="ndvi", date="2026-06-18", size=160, source="persisted"
    )

    assert seen["date"] == "2026-06-18", "لا توسيع ±أيّام في مسار العرض"


@pytest.mark.asyncio
async def test_auto_source_keeps_the_previous_live_behaviour(monkeypatch, router_module):
    """التوافق للخلف: بلا ``source=persisted`` يبقى المسار القديم كما هو."""
    cdse_tiles, _calls = router_module

    async def _normalize(*_args, **_kwargs):
        return None  # يُنهي المسار الحيّ مبكراً بلا شبكة

    monkeypatch.setattr(cdse_tiles, "_normalize_cdse_request", _normalize)

    response = await cdse_tiles.field_cdse_thumbnail("fld_x", index="ndvi", date="latest", size=160)

    assert "X-Imagery-State" not in response.headers, "المسار القديم بلا تغيير عقد"
