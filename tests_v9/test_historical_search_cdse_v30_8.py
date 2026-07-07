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
    # phase31: ألقاب _stac_search* انتقلت من main.py إلى raster_main_compat_exports.py.
    main_src = _read(_RASTER / "main.py") + "\n" + _read(_RASTER / "raster_main_compat_exports.py")
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
    # raster_backfill_scene_processing.py. phase28: أُزيل غلاف main._process_backfill_scene_cdse؛
    # الدالّة الفعليّة process_backfill_scene_cdse تعيش في الوحدة المستخرَجة.
    src = _read(_RASTER / "main.py") + "\n" + _read(_RASTER / "raster_backfill_scene_processing.py")
    assert "process_backfill_scene_cdse" in src
    assert "cdse_client.get_client().process_index(" in src
    worker = _read(_RASTER / "backfill_scan_worker.py")
    assert "_process_backfill_scene_cdse" in worker, "العامل يجب أن يعالج مشاهد CDSE"
    sync = _read(_RASTER / "routers" / "fields.py")
    assert "_process_backfill_scene_cdse" in sync, "المسار المتزامن يجب أن يعالج مشاهد CDSE"


# ── لا earth-search في مسار backfill التاريخيّ (العامل + الراوتر) ──
def test_no_earth_search_in_backfill_paths():
    # العقد الحقيقيّ: جلب/معالجة مشاهد backfill تمرّ عبر CDSE Process API + توجيه المزوّد
    # الافتراضيّ (cdse)، لا عبر استعلام earth-search مباشر إلى element84. ليس «السلسلة
    # الحرفيّة EARTH_SEARCH_URL لا تظهر أبداً».
    #
    # phase21: العامل المستقلّ يبني عميل STAC المرن في _configure_stac_search ويمرّر
    # raster_settings.EARTH_SEARCH_URL كأساس/ارتداد للعميل — تماماً كما يفعل main. هذه
    # تهيئة عميل، لا استعلام backfill. لذا نمنع مضيف earth-search الحرفيّ في الملفَّين،
    # ونحصر EARTH_SEARCH_URL في تهيئة العميل فقط (لا في مسار الجلب/المعالجة).
    for rel in ("backfill_scan_worker.py", "routers/fields.py"):
        src = _read(_RASTER / rel)
        assert "earth-search.aws.element84.com" not in src, f"{rel} يجب ألا يشير إلى Earth Search"

    # الراوتر المتزامن لا يذكر EARTH_SEARCH_URL إطلاقاً (يفوّض التوجيه لوحدة stac_search).
    fields_src = _read(_RASTER / "routers" / "fields.py")
    assert "EARTH_SEARCH_URL" not in fields_src, (
        "الراوتر يجب ألا يستعمل EARTH_SEARCH_URL في backfill"
    )

    # phase27: تهيئة عميل STAC (بما فيها EARTH_SEARCH_URL كأساس/ارتداد) انتقلت من العامل
    # إلى raster_stac_runtime.py. العامل الآن يفوّض عبر _configure_stac_search الذي يستدعي
    # raster_stac_runtime.configure_stac_search فقط، فلا يظهر EARTH_SEARCH_URL في العامل
    # إطلاقاً — وهذا أقوى من الحصر السابق (لا تسريب في مسار الجلب/المعالجة). نؤكّد بقاء
    # الأساس محصوراً في وحدة البوتستراب المخصّصة.
    worker = _read(_RASTER / "backfill_scan_worker.py")
    cfg_start = worker.index("def _configure_stac_search(")
    cfg_end = worker.index("\n_configure_stac_search()", cfg_start)  # الاستدعاء على مستوى الوحدة
    config_region = worker[cfg_start:cfg_end]
    assert "raster_stac_runtime.configure_stac_search" in config_region, (
        "تهيئة العميل يجب أن تفوّض إلى raster_stac_runtime"
    )
    assert "EARTH_SEARCH_URL" not in worker, (
        "EARTH_SEARCH_URL يجب ألّا يظهر في العامل — البوتستراب مفوَّض إلى raster_stac_runtime"
    )
    stac_runtime = _read(_RASTER / "raster_stac_runtime.py")
    assert "EARTH_SEARCH_URL" in stac_runtime, (
        "EARTH_SEARCH_URL يجب أن يبقى في تهيئة العميل داخل raster_stac_runtime"
    )
    # مسار جلب/معالجة backfill يستعمل CDSE (Process API) لا استعلام element84 مباشر.
    assert "_process_backfill_scene_cdse" in worker, "معالجة مشهد backfill يجب أن تمرّ عبر CDSE"
    assert "stac_search_helpers.stac_search" in worker, (
        "الجلب يجب أن يمرّ عبر موجّه المزوّد (cdse افتراضاً)"
    )


# ── البحث في مسار backfill يمرّر هندسة الحقل (intersects) للقصّ الدقيق ──
def test_backfill_search_passes_geometry():
    worker = _read(_RASTER / "backfill_scan_worker.py")
    assert "geometry=clip" in worker
    sync = _read(_RASTER / "routers" / "fields.py")
    assert "geometry=clip" in sync
