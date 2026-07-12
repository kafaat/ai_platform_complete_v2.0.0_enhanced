"""مصدر حقول Sentinel/Vegetation — حقيقة تشغيليّة: لا تلفيق تركيبيّ (20260712).

بعد اكتمال حقيقة التشغيل (runtime-truth): `FIELD_REGISTRY` فارغ، ومُحمِّل الحقول
`load_field` يقرأ الحقل من المنصّة المستأجَرة (platform API؛ هندسة GeoJSON ⇒ bbox،
مكافئ ST_Envelope محليّاً) خلف علم FEATURE_SENTINEL_DB_FIELDS (يُفعَّل تلقائيّاً عند
توفّر PLATFORM_API_URL). المسار fail-soft، لكنّه **لا يرتدّ للسجلّ التركيبيّ إطلاقاً**:
مسار «legacy» ميْت بصدق ⇒ يُسجَّل `legacy_field_registry_forbidden` ويعيد None حتّى
تفشل النشرات القديمة بوضوح بدل تلفيق بيانات. `ALLOW_LEGACY_FIELD_REGISTRY` يبقى مِفتاح
تهيئة (off افتراضيّاً) لكنّه لم يعُد يسبّب تلفيقاً.

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
VEG = os.path.join(ROOT, "services/vegetation-analysis-service/main.py")
# P1 decomposition: المنطق انتقل إلى vegetation_runtime.py الشقيقة — نفحص الملفّين معاً.
VEG_RT = os.path.join(ROOT, "services/vegetation-analysis-service/vegetation_runtime.py")


def _src() -> str:
    with open(VEG, encoding="utf-8") as f:
        src = f.read()
    with open(VEG_RT, encoding="utf-8") as f:
        src += "\n" + f.read()
    return src


def _func_src(name: str) -> str:
    src = _src()
    start = src.index(f"async def {name}(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    end = (start + 1 + nxt.start()) if nxt else len(src)
    return src[start:end]


# ── (A) تعاقُد على المصدر — يُنفَّذ في CI دائماً (لا يستورد الوحدة) ──
def test_load_field_exists_and_never_fabricates():
    body = _func_src("load_field")
    assert "FEATURE_SENTINEL_DB_FIELDS" in body, "load_field لا يفحص علم تفعيل القاعدة"
    assert "_load_field_from_db" in body, "load_field لا يستدعي مُحمِّل القاعدة/المنصّة"
    # حقيقة تشغيليّة: مسار legacy ميْت بصدق — لا ارتداد للسجلّ التركيبيّ إطلاقاً.
    assert "legacy_field_registry_forbidden" in body, "لا يَسِم منع السجلّ التركيبيّ بصدق"
    assert "FIELD_REGISTRY.get(field_id)" not in body, "ما زال يرتدّ للسجلّ التركيبيّ (تلفيق)"


def test_feature_flag_and_legacy_defaults_are_production_safe():
    src = _src()
    # FEATURE_SENTINEL_DB_FIELDS يُفعَّل تلقائيّاً عند توفّر PLATFORM_API_URL (منفذ القاعدة).
    assert re.search(
        r"FEATURE_SENTINEL_DB_FIELDS\s*=\s*_flag_enabled\(\s*os\.getenv\("
        r"\"FEATURE_SENTINEL_DB_FIELDS\"\),\s*default=bool\(PLATFORM_API_URL\)",
        src,
    ), "FEATURE_SENTINEL_DB_FIELDS يجب أن يُفعَّل تلقائيّاً عند توفّر PLATFORM_API_URL"
    # الارتداد التركيبيّ مُعطَّل افتراضيّاً في كلّ بيئة (production-safe، لا تلفيق).
    assert re.search(
        r"ALLOW_LEGACY_FIELD_REGISTRY\s*=\s*_flag_enabled\(\s*"
        r"os\.getenv\(\"ALLOW_LEGACY_FIELD_REGISTRY\"\),\s*default=False",
        src,
    ), "ALLOW_LEGACY_FIELD_REGISTRY يجب أن يكون off افتراضيّاً في كلّ بيئة"


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
    # P1 decomposition: main.py يستورد وحدة شقيقة (*_runtime) — يجب أن يكون
    # مجلّد الخدمة على sys.path قبل exec_module.
    import sys as _sys

    _svc_dir = os.path.dirname(VEG)
    if _svc_dir not in _sys.path:
        _sys.path.insert(0, _svc_dir)
    # عزل: نسخة شقيقة قديمة (خدمة أخرى/بيئة سابقة) في sys.modules تُفسد الاستيراد.
    _stale = _sys.modules.get("vegetation_runtime")
    if _stale is not None and os.path.dirname(getattr(_stale, "__file__", "") or "") != _svc_dir:
        _sys.modules.pop("vegetation_runtime", None)
    spec = importlib.util.spec_from_file_location("veg_field_source_test", VEG)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    # P1 decomposition: load_field/_load_field_from_db والأعلام تعيش في vegetation_runtime
    # — monkeypatch على وحدة الواجهة لا يصل globals المنطق؛ نُرجِع وحدة الـruntime نفسها.
    return _sys.modules["vegetation_runtime"]


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


async def test_load_field_off_by_default_returns_none_no_fabrication(veg, monkeypatch):
    # العلم مُطفأ: لا يلمس القاعدة، ولا يرتدّ للسجلّ التركيبيّ ⇒ None (لا تلفيق).
    monkeypatch.setattr(veg, "FEATURE_SENTINEL_DB_FIELDS", False)

    async def _boom(*a, **k):
        raise AssertionError("يجب ألّا يُستدعى مُحمِّل القاعدة والعلم مُطفأ")

    monkeypatch.setattr(veg, "_load_field_from_db", _boom)
    assert await veg.load_field("field_01", "t1") is None


async def test_load_field_db_used_when_flag_on(veg, monkeypatch):
    monkeypatch.setattr(veg, "FEATURE_SENTINEL_DB_FIELDS", True)
    sentinel = {"name": "from-db", "bbox": [1, 2, 3, 4], "crop": "wheat"}

    async def _db(field_id, tenant_id=None):
        return sentinel

    monkeypatch.setattr(veg, "_load_field_from_db", _db)
    assert await veg.load_field("field_01", "t1") is sentinel


async def test_load_field_failsoft_never_fabricates_even_when_legacy_allowed(veg, monkeypatch):
    # فشل القاعدة fail-soft (لا يرفع) لكنّه لا يرتدّ للسجلّ التركيبيّ حتّى مع السماح ⇒ None.
    monkeypatch.setattr(veg, "FEATURE_SENTINEL_DB_FIELDS", True)
    monkeypatch.setattr(veg, "ALLOW_LEGACY_FIELD_REGISTRY", True)

    async def _db(field_id, tenant_id=None):
        raise RuntimeError("platform down")

    monkeypatch.setattr(veg, "_load_field_from_db", _db)
    assert await veg.load_field("field_01", "t1") is None, "لا تلفيق: فشل القاعدة ⇒ None لا سجلّ"


async def test_load_field_no_legacy_returns_none(veg, monkeypatch):
    # ALLOW_LEGACY_FIELD_REGISTRY=false ⇒ فشل القاعدة لا يرتدّ للسجلّ (None).
    monkeypatch.setattr(veg, "FEATURE_SENTINEL_DB_FIELDS", True)
    monkeypatch.setattr(veg, "ALLOW_LEGACY_FIELD_REGISTRY", False)

    async def _db(field_id, tenant_id=None):
        return None

    monkeypatch.setattr(veg, "_load_field_from_db", _db)
    assert await veg.load_field("field_01", "t1") is None
