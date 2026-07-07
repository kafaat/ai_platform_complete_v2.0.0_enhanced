"""تحقّق V63 — نموذج المشهد الموحَّد + سِجِلّ المزوّدين + الاقتراح الاحتياطيّ المُهيكَل.

- ``NormalizedScene`` يلفّ مخرَج ``stac_search_*`` القائم: element84 ⇒ cog_ready True،
  كتالوج CDSE (روابط فارغة) ⇒ cog_ready False. لا تغيير سلوك تشغيل (إضافيّ).
- ``PROVIDER_REGISTRY`` صادق: nasa_hls/planetary_computer غير نشطَين (لم يُوصَلا)؛
  element84/cdse/local_cog نشطة. ``active_providers`` يعكس الوصل الفعليّ لا الطموح.
- ``provider_fallback_suggestion`` مُهيكَل يوجّه إلى element84 عند فشل/نفاد CDSE.
- مسار 503 في ``stac_search`` يحمل الاقتراح المُهيكَل (لا نصّ حرّ فقط).

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import raster_scene_model as M  # noqa: E402

_E84_ITEM = {
    "item_id": "S2B_36PXV_20260701_0_L2A",
    "datetime": "2026-07-01T08:12:19Z",
    "cloud_cover_pct": 3.4,
    "bbox": [44.0, 16.0, 44.4, 16.4],
    "bands_urls": {"red": "https://x/red.tif", "nir": "https://x/nir.tif", "swir1": None},
    "thumbnail_url": "https://x/thumb.jpg",
    "preview_url": "https://x/visual.tif",
    "platform": "sentinel-2b",
    "provider": "element84",
}
_CDSE_ITEM = {
    "item_id": "S2A_CDSE_20260630",
    "datetime": "2026-06-30T08:00:00Z",
    "cloud_cover_pct": 12.0,
    "bbox": [44.0, 16.0, 44.4, 16.4],
    "bands_urls": {},  # كتالوج CDSE: معالجة خادميّة، لا روابط COG
    "provider": "cdse",
}


def test_normalize_element84_scene_is_cog_ready():
    s = M.normalize_scene(_E84_ITEM, source="element84-earth-search")
    assert s.provider == "element84"
    assert s.cog_ready is True
    assert s.sensor == "MSI"
    assert s.acquisition_date == "2026-07-01T08:12:19Z"
    assert s.bands_available == ["nir", "red"]  # None يُسقَط + مُرتَّب
    assert "Copernicus" in s.license
    assert s.cloud_cover == pytest.approx(3.4)


def test_normalize_cdse_scene_not_cog_ready():
    s = M.normalize_scene(_CDSE_ITEM, source="cdse-catalog")
    assert s.provider == "cdse"
    assert s.cog_ready is False  # لا روابط ⇒ يتطلّب معالجة خادميّة
    assert s.bands_available == []


def test_to_dict_has_required_report_fields():
    s = M.normalize_scene(_E84_ITEM, source="element84-earth-search")
    d = s.to_dict()
    for key in (
        "scene_id",
        "provider",
        "collection",
        "sensor",
        "acquisition_date",
        "cloud_cover",
        "bbox",
        "bands_available",
        "cog_ready",
        "source",
        "license",
    ):
        assert key in d


def test_normalize_search_result_propagates_source():
    result = {"source": "element84-earth-search", "count": 1, "items": [_E84_ITEM]}
    scenes = M.normalize_search_result(result)
    assert len(scenes) == 1 and scenes[0].source == "element84-earth-search"


def test_normalize_search_result_handles_malformed():
    assert M.normalize_search_result(None) == []
    assert M.normalize_search_result({"items": "nope"}) == []
    # عنصر ناقص الحقول ⇒ افتراضات آمنة لا استثناء
    s = M.normalize_scene({}, source="x")
    assert s.scene_id == "" and s.cog_ready is False and s.cloud_cover == 0.0


def test_provider_registry_is_honest_about_active():
    assert M.PROVIDER_REGISTRY["element84"]["active"] is True
    assert M.PROVIDER_REGISTRY["cdse"]["active"] is True
    assert M.PROVIDER_REGISTRY["nasa_hls"]["active"] is False  # غير موصول
    assert M.PROVIDER_REGISTRY["planetary_computer"]["active"] is False  # STAC-fallback فقط
    active = M.active_providers()
    assert "element84" in active and "nasa_hls" not in active


def test_fallback_suggestion_points_to_element84():
    sug = M.provider_fallback_suggestion("cdse_quota_exhausted")
    assert sug["suggested_provider"] == "element84"
    assert sug["reason_code"] == "cdse_quota_exhausted"
    assert "element84" in sug["action"]
    assert sug["reason"]  # نصّ بشريّ حاضر
    # البدائل لا تُعيد المزوّد الحاليّ ولا local_cog
    assert "cdse" not in sug["alternatives"] and "local_cog" not in sug["alternatives"]


# ── حارس ١: المزوّدون غير الموصولين لا يظهرون نشطين إطلاقاً ──────────────────────
def test_unwired_providers_never_active():
    active = M.active_providers()
    for p in ("nasa_hls", "planetary_computer"):
        assert p not in active, f"{p} غير موصول ⇒ يجب ألّا يظهر نشطاً"
        assert M.PROVIDER_REGISTRY[p]["active"] is False


# ── الحالات الحديّة لعقد cog_ready (assets مفقودة / نطاقات جزئيّة) ────────────────
def test_cog_ready_missing_assets_is_false():
    # لا مفتاح bands_urls إطلاقاً ⇒ لا قراءة COG مباشرة
    s = M.normalize_scene({"item_id": "z", "datetime": "2026-07-01T00:00:00Z"}, source="x")
    assert s.cog_ready is False and s.bands_available == []


def test_cog_ready_partial_bands_is_ready_with_subset():
    # نطاقات جزئيّة (red فقط، swir1 مفقود) ⇒ جاهز مع عكس المجموعة الفعليّة المتوفّرة
    item = {
        "item_id": "p",
        "datetime": "2026-07-01T00:00:00Z",
        "bands_urls": {"red": "http://x/r.tif", "swir1": None},
    }
    s = M.normalize_scene(item, source="element84-earth-search")
    assert s.cog_ready is True
    assert s.bands_available == ["red"]  # يعكس المتوفّر فقط (لا يدّعي swir1)


# ── حارس ٢: الاقتراح الاحتياطيّ عقدٌ CDSE-محصور (لا يُطلَق لمزوّد آخر ضمنيّاً) ──────
def test_fallback_suggestion_is_cdse_scoped_contract():
    for code in ("cdse_unconfigured", "cdse_quota_exhausted", "cdse_catalog_unavailable"):
        sug = M.provider_fallback_suggestion(code)
        assert sug["current_provider"] == "cdse"
        assert sug["suggested_provider"] == "element84"
    # الافتراض current_provider=cdse — لا يُنسَب فشل مزوّد آخر إلى CDSE ضمنيّاً.
    assert M.provider_fallback_suggestion("anything")["current_provider"] == "cdse"


def test_element84_path_carries_no_fallback_suggestion():
    # مسار element84 يقصر الدائرة قبل عقد اقتراح CDSE — لا تسريب للاقتراح خارج فشل CDSE.
    src = (_RASTER / "stac_search.py").read_text(encoding="utf-8")
    assert src.count('"fallback_suggestion"') == 1, "الاقتراح يجب أن يظهر مرّة واحدة (عقد CDSE فقط)"
    i_e84 = src.find("async def stac_search_element84(")
    body_e84 = src[i_e84 : i_e84 + 1600]
    assert "fallback_suggestion" not in body_e84


# ── حارس ٣ (الأهمّ): acquisition_date لا يقبل processed_at كبديل صامت ──────────────
def test_acquisition_date_never_falls_back_to_processed_at():
    # عنصر يحمل datetime + processed_at/created_at ⇒ يُختار datetime (وقت الالتقاط) حصراً.
    item = {
        "item_id": "a",
        "datetime": "2026-07-01T08:00:00Z",
        "processed_at": "2026-07-05T00:00:00Z",
        "created_at": "2026-07-06T00:00:00Z",
        "bands_urls": {"red": "http://x/r.tif"},
    }
    s = M.normalize_scene(item, source="element84-earth-search")
    assert s.acquisition_date == "2026-07-01T08:00:00Z"
    # غياب datetime ⇒ فراغ صريح، لا انحدار صامت إلى processed_at/created_at.
    s2 = M.normalize_scene(
        {"item_id": "b", "processed_at": "2026-07-05T00:00:00Z", "created_at": "2026-07-06"},
        source="x",
    )
    assert s2.acquisition_date == ""
    assert "2026-07-05" not in s2.acquisition_date and "2026-07-06" not in s2.acquisition_date


def test_model_source_has_no_processed_at_mapping():
    # حارس انحدار ساكن: النموذج يجب ألّا يشير إلى processed_at إطلاقاً (منع تعيينه سرّاً).
    src = (_RASTER / "raster_scene_model.py").read_text(encoding="utf-8")
    assert "processed_at" not in src, "النموذج يجب ألّا يعيّن processed_at كتاريخ التقاط"


# ── حارس ساكن: مسار 503 يحمل الاقتراح المُهيكَل ─────────────────────────────────
def test_stac_search_503_carries_structured_suggestion():
    src = (_RASTER / "stac_search.py").read_text(encoding="utf-8")
    assert "provider_fallback_suggestion" in src, "يجب استيراد باني الاقتراح"
    assert '"fallback_suggestion"' in src, "تفاصيل 503 يجب أن تحمل اقتراحاً مُهيكَلاً"
    assert "status_code=503" in src  # يبقى فشلاً مُغلَقاً صادقاً
