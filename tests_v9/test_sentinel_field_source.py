"""مصدر حقول Sentinel/Vegetation — إغلاق مرن نحو القاعدة (PR #395).

استبدال القراءة الصلبة من FIELD_REGISTRY بمُحمِّل حقول مرن load_field خلف علم
FEATURE_SENTINEL_DB_FIELDS (مُطفأ افتراضيّاً ⇒ السلوك الحاليّ تماماً). هذه الخدمة
بلا pool قاعدة؛ «القاعدة» تُقرأ عبر platform API (hndسة GeoJSON ⇒ bbox، مكافئ
ST_Envelope محليّاً). كلّ المسار fail-soft؛ الارتداد للسجلّ القديم موسوم بصدق
`legacy_field_registry_used`.

طبقتان (كنمط test_vegetation_raster_ndvi):
  (A) تعاقُد على المصدر — يُنفَّذ في CI دائماً (تفتيش نصّيّ، لا استيراد).
  (B) منطقيّ/سلوكيّ — يستورد الوحدة (يتخطّى إن غابت التبعيّات في CI الخفيفة).
"""

from __future__ import annotations

import importlib.util
import os
import re

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
VEG_MAIN = os.path.join(ROOT, "services/vegetation-analysis-service/main.py")
VEG_RUNTIME = os.path.join(ROOT, "services/vegetation-analysis-service/vegetation_runtime.py")


def _src() -> str:
    with open(VEG_MAIN, encoding="utf-8") as f:
        main_src = f.read()
    with open(VEG_RUNTIME, encoding="utf-8") as f:
        runtime_src = f.read()
    return main_src + "\n" + runtime_src


def _func_src(name: str) -> str:
    src = _src()
    start = src.index(f"async def {name}(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    end = (start + 1 + nxt.start()) if nxt else len(src)
    return src[start:end]


# ── (A) تعاقُد على المصدر — يُنفَّذ في CI دائماً (لا يستورد الوحدة) ──
def test_load_field_exists_and_is_graceful():
    body = _func_src("load_field")
    assert "FEATURE_SENTINEL_DB_FIELDS" in body, "load_field لا يفحص علم تفعيل القاعدة"
    assert "_load_field_from_db" in body, "load_field لا يستدعي مُحمِّل القاعدة"
    assert "legacy_field_registry_used" in body, "لا يَسِم الارتداد للسجلّ القديم بصدق"
    assert "FIELD_REGISTRY.get(field_id)" in body, "لا يرتدّ للسجلّ التركيبيّ القديم"


def test_feature_flag_off_by_default():
    src = _src()
    # العلم يُطبَّع عبر _flag_enabled بافتراض False (off) — السلوك الحاليّ تماماً.
    assert re.search(
        r"FEATURE_SENTINEL_DB_FIELDS\s*=\s*_flag_enabled\(.*default=False",
        src,
    ), "FEATURE_SENTINEL_DB_FIELDS يجب أن يكون off افتراضيّاً"
    assert re.search(
        r"ALLOW_LEGACY_FIELD_REGISTRY\s*=\s*_flag_enabled\(.*default=True",
        src,
    ), "ALLOW_LEGACY_FIELD_REGISTRY يجب أن يسمح بالارتداد افتراضيّاً"


def test_db_loader_is_failsoft_via_platform_api():
    body = _func_src("_load_field_from_db")
    assert "PLATFORM_API_URL" in body, "لا يقرأ من المنصّة (لا منفذ قاعدة في الخدمة)"
    assert "_geometry_to_bbox" in body, "لا يحوّل هندسة GeoJSON إلى bbox"
    assert "except Exception" in body, "ليس fail-soft (لا يلتقط الاستثناء)"


def test_run_analysis_uses_loader_not_direct_registry():
    body = _func_src("run_analysis")
    assert "await load_field(field_id, tenant_id)" in body, "run_analysis لا يستعمل المُحمِّل المرن"
    assert "FIELD_REGISTRY.get(field_id)" not in body, "run_analysis ما زال يقرأ السجلّ مباشرةً"


# ── (B) منطقيّ/سلوكيّ — يتخطّى إن غابت التبعيّات (بيئة CI الخفيفة) ──
@pytest.fixture(scope="module")
def veg():
    pytest.importorskip("fastapi")
    pytest.importorskip("jwt")
    pytest.importorskip("httpx")
    pytest.importorskip("prometheus_client")
    spec = importlib.util.spec_from_file_location("veg_field_source_test", VEG_MAIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_flag_enabled_normalization(veg):
    f = veg._flag_enabled
    # None ⇒ الافتراض
    assert f(None, default=True) is True
    assert f(None, default=False) is False
    # قيم الإطفاء المتعارَفة
    for off in ("0", "false", "False", ""):
        assert f(off, default=True) is False, off
    # أيّ شيء آخر ⇒ True
    for on in ("1", "true", "yes", "on"):
        assert f(on, default=False) is True, on


def test_select_field_source_decision_table(veg):
    sel = veg.select_field_source
    # العلم مُطفأ ⇒ السجلّ القديم دائماً (السلوك الحاليّ)
    assert sel(feature_db=False, allow_legacy=True, db_available=False) == "legacy"
    assert sel(feature_db=False, allow_legacy=False, db_available=True) == "legacy"
    # العلم مُفعَّل + قراءة قاعدة ناجحة ⇒ db
    assert sel(feature_db=True, allow_legacy=True, db_available=True) == "db"
    # العلم مُفعَّل + فشل قاعدة + ارتداد مسموح ⇒ legacy
    assert sel(feature_db=True, allow_legacy=True, db_available=False) == "legacy"
    # العلم مُفعَّل + فشل قاعدة + ارتداد ممنوع ⇒ none
    assert sel(feature_db=True, allow_legacy=False, db_available=False) == "none"


def test_geometry_to_bbox(veg):
    g2b = veg._geometry_to_bbox
    # Polygon: bbox = [minx, miny, maxx, maxy]
    poly = {
        "type": "Polygon",
        "coordinates": [[[45.5, 15.0], [45.6, 15.0], [45.6, 15.1], [45.5, 15.1], [45.5, 15.0]]],
    }
    assert g2b(poly) == [45.5, 15.0, 45.6, 15.1]
    # MultiPolygon (تداخل أعمق) يُغطّى أيضاً
    multi = {"type": "MultiPolygon", "coordinates": [[[[1.0, 2.0], [3.0, 4.0], [1.0, 2.0]]]]}
    assert g2b(multi) == [1.0, 2.0, 3.0, 4.0]
    # هندسة غائبة/غير صالحة ⇒ None (لا تلفيق)
    assert g2b(None) is None
    assert g2b({}) is None
    assert g2b({"type": "Polygon", "coordinates": []}) is None


async def test_load_field_off_by_default_returns_registry(veg, monkeypatch):
    # العلم مُطفأ (الافتراض): يرتدّ للسجلّ التركيبيّ ولا يلمس القاعدة إطلاقاً.
    monkeypatch.setattr(veg, "FEATURE_SENTINEL_DB_FIELDS", False)
    monkeypatch.setattr(veg._vegetation_runtime, "FEATURE_SENTINEL_DB_FIELDS", False)

    async def _boom(*a, **k):
        raise AssertionError("يجب ألّا يُستدعى مُحمِّل القاعدة والعلم مُطفأ")

    monkeypatch.setattr(veg, "_load_field_from_db", _boom)
    monkeypatch.setattr(veg._vegetation_runtime, "_load_field_from_db", _boom)
    field = await veg.load_field("field_01", "t1")
    assert field == veg.FIELD_REGISTRY["field_01"]


async def test_load_field_db_used_when_flag_on(veg, monkeypatch):
    monkeypatch.setattr(veg, "FEATURE_SENTINEL_DB_FIELDS", True)
    monkeypatch.setattr(veg._vegetation_runtime, "FEATURE_SENTINEL_DB_FIELDS", True)
    sentinel = {"name": "from-db", "bbox": [1, 2, 3, 4], "crop": "wheat"}

    async def _db(field_id, tenant_id=None):
        return sentinel

    monkeypatch.setattr(veg, "_load_field_from_db", _db)
    monkeypatch.setattr(veg._vegetation_runtime, "_load_field_from_db", _db)
    assert await veg.load_field("field_01", "t1") is sentinel


async def test_load_field_failsoft_falls_back_to_registry(veg, monkeypatch):
    monkeypatch.setattr(veg, "FEATURE_SENTINEL_DB_FIELDS", True)
    monkeypatch.setattr(veg._vegetation_runtime, "FEATURE_SENTINEL_DB_FIELDS", True)
    monkeypatch.setattr(veg, "ALLOW_LEGACY_FIELD_REGISTRY", True)
    monkeypatch.setattr(veg._vegetation_runtime, "ALLOW_LEGACY_FIELD_REGISTRY", True)

    async def _db(field_id, tenant_id=None):
        raise RuntimeError("platform down")

    monkeypatch.setattr(veg, "_load_field_from_db", _db)
    monkeypatch.setattr(veg._vegetation_runtime, "_load_field_from_db", _db)
    field = await veg.load_field("field_01", "t1")
    assert field == veg.FIELD_REGISTRY["field_01"], "يجب الارتداد للسجلّ عند فشل القاعدة"


async def test_load_field_no_legacy_returns_none(veg, monkeypatch):
    # ALLOW_LEGACY_FIELD_REGISTRY=false ⇒ فشل القاعدة لا يرتدّ للسجلّ (None).
    monkeypatch.setattr(veg, "FEATURE_SENTINEL_DB_FIELDS", True)
    monkeypatch.setattr(veg._vegetation_runtime, "FEATURE_SENTINEL_DB_FIELDS", True)
    monkeypatch.setattr(veg, "ALLOW_LEGACY_FIELD_REGISTRY", False)
    monkeypatch.setattr(veg._vegetation_runtime, "ALLOW_LEGACY_FIELD_REGISTRY", False)

    async def _db(field_id, tenant_id=None):
        return None

    monkeypatch.setattr(veg, "_load_field_from_db", _db)
    monkeypatch.setattr(veg._vegetation_runtime, "_load_field_from_db", _db)
    assert await veg.load_field("field_01", "t1") is None
