"""حارس Landsat thermal-unique (CI): Landsat طبقة حرارية فريدة فقط، لا تكرار Sentinel-2.

القرار المعماريّ: Copernicus/Sentinel-2 مصدر NDVI/NDMI/...؛ Landsat يُسحب منه فقط LST
(أصل حراريّ مباشر) وتُشتق CWSI/TVDI/TCI/VHI لاحقاً — لا تُعاد مؤشّرات بصريّة أخشن.
فحوص ساكنة على المصدر (بلا استيراد main الثقيل) + تسجيل ترحيل v147 في المُشغّلَين.
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"


def _read(rel: str) -> str:
    return (_RASTER / rel).read_text(encoding="utf-8")


# ── مجموعات Landsat لا تحتوي مؤشّرات Sentinel-2 المكررة ──
def test_landsat_unique_sets_exclude_sentinel_duplicates():
    # التفكيك: منطق Landsat الفريد انتقل إلى stac_search.py؛ main يحتفظ بالمجموعات + الأسماء المستعارة.
    src = _read("main.py") + "\n" + _read("stac_search.py") + "\n" + _read("raster_settings.py")
    assert 'LANDSAT_UNIQUE_INDICES = {"lst", "cwsi", "tvdi", "tci", "vhi", "et_inputs"}' in src
    assert 'LANDSAT_DIRECT_RASTER_INDICES = {"lst"}' in src
    # الأصل الحراريّ المباشر lst فقط؛ لا red/nir/swir بصريّة
    assert "_landsat_thermal_href" in src
    assert "def stac_search_landsat_unique" in src
    # المكرّرات معلَنة صراحةً كمستبعَدة (المجموعة قد تُنسَّق سطراً لكلّ عنصر)
    assert "LANDSAT_DUPLICATE_SENTINEL_INDICES = {" in src
    for dup in ('"ndvi"', '"ndmi"', '"msi"', '"savi"', '"evi"'):
        assert dup in src, f"مؤشّر Sentinel المكرّر {dup} يجب أن يُعلَن مستبعَداً"


# ── payload الحراريّ يحمل thermal_urls فقط (لا bands_urls بصريّة) ──
def test_landsat_payload_thermal_only():
    # التفكيك: حمولة Landsat الحراريّة انتقلت إلى stac_search.py (landsat_unique_payload).
    src = _read("main.py") + "\n" + _read("stac_search.py") + "\n" + _read("raster_settings.py")
    assert '"thermal_urls": {"lst": thermal_href}' in src
    # لا يُدرِج bands_urls (تفادي بناء NDVI من Landsat)
    idx = src.find("def landsat_unique_payload")
    body = src[idx : idx + 1400]
    assert '"bands_urls"' not in body, "payload الحراريّ يجب ألّا يحمل bands_urls البصريّة"


# ── مسار backfill يرفض المؤشّرات المكررة ويوجّه لبحث Landsat الفريد ──
def test_backfill_route_landsat_source_guard():
    src = _read("routers/fields.py")
    assert "is_landsat_thermal" in src
    assert "main.LANDSAT_UNIQUE_INDICES" in src
    assert "المؤشرات المكررة مع Sentinel-2 مرفوضة" in src
    assert "main._stac_search_landsat_unique" in src
    # مشتقات لا تُسحب كراستر مباشر إلّا dry_run
    assert "main.LANDSAT_DIRECT_RASTER_INDICES" in src


# ── العامل: is_landsat_thermal مُعرَّف في _process_run (حارس ضدّ NameError) ──
def test_worker_defines_is_landsat_thermal():
    src = _read("backfill_scan_worker.py")
    assert 'is_landsat_thermal = str(run.get("source")' in src, (
        "is_landsat_thermal مستعمَل في _process_run فيجب تعريفه (وإلّا NameError على كلّ تشغيلة)"
    )
    # معالجة LST من الأصل الحراريّ مباشرةً
    assert "main.IndicatorKind.lst" in src and "landsat-element84" in src


# ── معالجة Landsat LST تُثبِت persisted (لا نجاح كاذب) ──
def test_landsat_lst_processing_requires_persisted():
    for rel in ("backfill_scan_worker.py", "routers/fields.py"):
        src = _read(rel)
        assert "landsat_lst_asset_missing" in src, f"{rel} يجب أن يرفض مشهداً بلا أصل LST"


# ── ترحيل v147 مُسجَّل في المُشغّلَين + النمط idempotent الصحيح للقيد ──
def test_v147_registered_both_runners_idempotent():
    manifest = (_ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    runner = (_ROOT / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
    name = "v147_backfill_runs_source_landsat_thermal.sql"
    assert name in manifest, "v147 مفقود من MANIFEST"
    assert name in runner, "v147 مفقود من run_migrations.sql"
    sql = (_ROOT / "migrations" / name).read_text(encoding="utf-8")
    # idempotent: DROP CONSTRAINT IF EXISTS قبل ADD (درس v146)
    assert "DROP CONSTRAINT IF EXISTS backfill_runs_source_check" in sql
    assert "CHECK (source IN ('sentinel-2', 'landsat-thermal'))" in sql
