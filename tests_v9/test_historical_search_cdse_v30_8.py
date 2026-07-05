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
    src = _read(_RASTER / "main.py")
    assert 'os.getenv("HISTORICAL_SEARCH_PROVIDER", "cdse")' in src, (
        "المزوّد الافتراضيّ للبحث التاريخيّ يجب أن يكون cdse"
    )


# ── _stac_search يوجّه إلى CDSE أوّلاً (وElement84 ارتداد صريح فقط) ──
def test_stac_search_dispatches_to_cdse():
    src = _read(_RASTER / "main.py")
    assert "async def _stac_search_cdse" in src, "يجب وجود باحث CDSE للكتالوج"
    assert 'HISTORICAL_SEARCH_PROVIDER == "cdse"' in src
    assert "search_scenes(" in src, "يجب استعمال cdse_client.search_scenes"
    # الاكتشاف عبر كتالوج CDSE يُصدِر source=cdse-catalog
    assert '"source": "cdse-catalog"' in src


# ── مسار المعالجة التاريخيّة يستعمل CDSE Process API لمشاهد الكتالوج ──
def test_backfill_processes_cdse_scenes_via_process_api():
    src = _read(_RASTER / "main.py")
    assert "def _process_backfill_scene_cdse" in src
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
