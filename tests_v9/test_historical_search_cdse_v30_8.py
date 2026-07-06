"""حارس تحويل البحث التاريخيّ إلى CDSE/Copernicus (لا ارتداد صامت إلى Element84).

الطلب: مسار البحث التاريخيّ عن مشاهد Sentinel-2 يعتمد كتالوج CDSE (Copernicus Data
Space) لا Element84 Earth Search. المعالجة على CDSE أصلاً. هذه الحُرّاس تمنع الانحدار
إلى ``earth-search.aws.element84.com`` في مسار backfill التاريخيّ. منطق ساكن (بلا خدمات).
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"


def _read(rel: pathlib.Path) -> str:
    return rel.read_text(encoding="utf-8")


# ── الافتراض CDSE: مزوّد البحث التاريخيّ = cdse ما لم يُطلَب Element84 صراحةً ──
def test_default_historical_search_provider_is_cdse():
    # phase12: الإعدادات (المزوّد الافتراضيّ) انتقلت إلى raster_settings.py
    src = _read(_RASTER / "main.py") + "\n" + _read(_RASTER / "raster_settings.py")
    assert 'os.getenv("HISTORICAL_SEARCH_PROVIDER", "cdse")' in src, (
        "المزوّد الافتراضيّ للبحث التاريخيّ يجب أن يكون cdse"
    )


# ── _stac_search يوجّه إلى CDSE + يفشل مُغلَقاً بلا اعتمادات (لا ارتداد صامت لـElement84) ──
def test_stac_search_dispatches_to_cdse_failclosed():
    # منطق البحث فُكِّك من main.py إلى stac_search.py (بلا بادئة _)؛ main يعيد تصديره
    # عبر ألقاب _stac_search*. نتتبّع الشيفرة المنقولة ونثبّت وصلها بواجهة main.
    src = _read(_RASTER / "stac_search.py")
    main_src = _read(_RASTER / "main.py")
    assert "_stac_search = stac_search_helpers.stac_search" in main_src, (
        "main يجب أن يوجّه _stac_search إلى الوحدة المفكَّكة"
    )
    assert "async def stac_search_cdse" in src, "يجب وجود باحث CDSE للكتالوج"
    assert "search_scenes(" in src, "يجب استعمال cdse_client.search_scenes"
    assert '"source": "cdse-catalog"' in src
    # Element84 ارتداد صريح فقط (تجاوز واعٍ)
    assert 'HISTORICAL_SEARCH_PROVIDER == "element84"' in src
    # لا اعتمادات CDSE ⇒ فشل مُغلَق بـ503 (لا تسرّب صامت إلى Element84)
    idx = src.find("async def stac_search(")
    body = src[idx : idx + 1800]
    assert "not _cdse.is_configured()" in body
    assert "status_code=503" in body, "غياب اعتمادات CDSE يجب أن يفشل مُغلَقاً بـ503"


# ── مسار المعالجة التاريخيّة يستعمل CDSE Process API لمشاهد الكتالوج ──
def test_backfill_processes_cdse_scenes_via_process_api():
    # phase12: مسار معالجة مشهد backfill عبر CDSE Process API انتقل إلى
    # raster_backfill_scene_processing.py (وبقي غلاف التوافق في main.py).
    src = _read(_RASTER / "main.py") + "\n" + _read(_RASTER / "raster_backfill_scene_processing.py")
    assert "_process_backfill_scene_cdse" in src
    assert "cdse_client.get_client().process_index(" in src
    worker = _read(_RASTER / "backfill_scan_worker.py")
    assert "_process_backfill_scene_cdse" in worker, "العامل يجب أن يعالج مشاهد CDSE"
    sync = _read(_RASTER / "routers" / "fields.py")
    assert "_process_backfill_scene_cdse" in sync, "المسار المتزامن يجب أن يعالج مشاهد CDSE"


# ── لا earth-search في مسار backfill التاريخيّ (العامل + الراوتر) ──
def test_no_earth_search_in_backfill_paths():
    for rel in ("backfill_scan_worker.py", "routers/fields.py"):
        src = _read(_RASTER / rel)
        assert "earth-search.aws.element84.com" not in src, f"{rel} يجب ألا يشير إلى Earth Search"
        assert "EARTH_SEARCH_URL" not in src, f"{rel} يجب ألا يستعمل EARTH_SEARCH_URL في backfill"


# ── البحث في مسار backfill يمرّر هندسة الحقل (intersects) للقصّ الدقيق ──
def test_backfill_search_passes_geometry():
    worker = _read(_RASTER / "backfill_scan_worker.py")
    assert "geometry=clip" in worker
    sync = _read(_RASTER / "routers" / "fields.py")
    assert "geometry=clip" in sync
