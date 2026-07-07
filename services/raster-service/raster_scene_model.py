"""نموذج مشهد موحَّد + سِجِلّ مزوّدين + اقتراح احتياطيّ (V63).

**المشكلة (تدقيق التغطية + التقرير الخارجيّ):** نتائج البحث لكلّ مزوّد قواميس مخصّصة
(`stac_search.py`) بلا نموذج مشترك (collection/sensor/cog_ready/license)، ولا سِجِلّ
مزوّدين واحد، ولا اقتراح مُهيكَل عند فشل CDSE (كان نصّ 503 حرّاً فقط).

**الحلّ (منطق صرف، بلا I/O — قابل للاختبار حتميّاً):**
- `NormalizedScene`: نموذج مشهد واحد يلفّ مخرَج `stac_search_*` القائم دون تغيير سلوك
  التشغيل (إضافيّ). يحمل الحقول التي طلبها التقرير: scene_id/provider/collection/
  sensor/acquisition_date/cloud_cover/bbox/bands/bands_available/cog_ready/source/license.
- `PROVIDER_REGISTRY`: وصف **صادق** لكلّ مزوّد (نشط/مخطَّط، مصادقة، COG، رخصة) — بيانات
  وصفيّة لا توجيه تشغيليّ مُختلَق. `active=False` لِما ليس موصولاً فعلاً (NASA HLS).
- `provider_fallback_suggestion`: اقتراح مُهيكَل قابل للقراءة آليّاً عند نفاد رصيد CDSE
  أو غياب اعتماداته — يوجّه إلى Element84 (صور خام مجانيّة بلا وحدات معالجة).

لا اختلاق: `cog_ready` يُشتقّ من توفّر روابط النطاقات فعلاً؛ الرخص من مصدر البيانات
(Copernicus مفتوح)؛ `active` يعكس الوصل الحقيقيّ في الكود لا الطموح.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── تعيين المصدر (source string من stac_search) → هويّة المزوّد المعياريّة ──────────
_SOURCE_TO_PROVIDER: dict[str, str] = {
    "element84-earth-search": "element84",
    "cdse-catalog": "cdse",
    "local-cog": "local_cog",
}

# رخصة بيانات Sentinel-2 موحّدة عبر كلّ المزوّدين (Copernicus مفتوح، تجاريّ مسموح).
_COPERNICUS_LICENSE = "Copernicus-open (CC-BY, commercial OK)"


@dataclass(frozen=True)
class NormalizedScene:
    """مشهد قمر صناعيّ موحَّد عبر المزوّدين (منطق صرف، غير مُتحوّل)."""

    scene_id: str
    provider: str
    collection: str
    sensor: str
    acquisition_date: str  # وقت الالتقاط من STAC (لا وقت المعالجة)
    cloud_cover: float
    bbox: list[float] | None
    bands: dict[str, str]  # اسم النطاق → رابط COG (فارغ لمشاهد المعالجة الخادميّة)
    bands_available: list[str]
    cog_ready: bool  # True ⇒ قراءة نافذة COG مباشرة؛ False ⇒ يتطلّب معالجة خادميّة
    source: str
    license: str
    thumbnail_url: str | None = None
    preview_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "provider": self.provider,
            "collection": self.collection,
            "sensor": self.sensor,
            "acquisition_date": self.acquisition_date,
            "cloud_cover": self.cloud_cover,
            "bbox": self.bbox,
            "bands_available": self.bands_available,
            "cog_ready": self.cog_ready,
            "source": self.source,
            "license": self.license,
            "thumbnail_url": self.thumbnail_url,
            "preview_url": self.preview_url,
        }


def _clean_bands(bands_urls: Any) -> dict[str, str]:
    """يُبقي فقط النطاقات ذات الروابط الفعليّة (يُسقِط None)."""
    if not isinstance(bands_urls, dict):
        return {}
    return {k: v for k, v in bands_urls.items() if isinstance(v, str) and v}


def normalize_scene(
    item: dict[str, Any],
    *,
    source: str,
    collection: str = "sentinel-2-l2a",
) -> NormalizedScene:
    """يحوّل عنصر بحث خاماً (من ``stac_search_*``) إلى ``NormalizedScene``.

    ``cog_ready`` يُشتقّ من توفّر روابط النطاقات: Element84 يوفّر روابط COG مباشرة
    (⇒ True)، بينما كتالوج CDSE يعيد روابط فارغة لأنّ المعالجة عبر Process API (⇒ False).
    """
    provider = item.get("provider") or _SOURCE_TO_PROVIDER.get(source, source or "unknown")
    bands = _clean_bands(item.get("bands_urls"))
    platform = str(item.get("platform") or "sentinel-2")
    sensor = "MSI" if platform.startswith("sentinel-2") else platform
    cloud = item.get("cloud_cover_pct", 0.0)
    try:
        cloud_f = float(cloud)
    except (TypeError, ValueError):
        cloud_f = 0.0
    return NormalizedScene(
        scene_id=str(item.get("item_id") or ""),
        provider=str(provider),
        collection=collection,
        sensor=sensor,
        acquisition_date=str(item.get("datetime") or ""),
        cloud_cover=cloud_f,
        bbox=item.get("bbox"),
        bands=bands,
        bands_available=sorted(bands.keys()),
        cog_ready=bool(bands),
        source=source,
        license=_COPERNICUS_LICENSE,
        thumbnail_url=item.get("thumbnail_url"),
        preview_url=item.get("preview_url"),
    )


def normalize_search_result(result: dict[str, Any]) -> list[NormalizedScene]:
    """يحوّل مخرَج ``stac_search_*`` كاملاً إلى قائمة مشاهد موحّدة."""
    if not isinstance(result, dict):
        return []
    source = str(result.get("source") or "")
    items = result.get("items")
    if not isinstance(items, list):
        return []
    return [normalize_scene(it, source=source) for it in items if isinstance(it, dict)]


# ── سِجِلّ المزوّدين الوصفيّ (صادق: active يعكس الوصل الفعليّ في الكود) ───────────────
PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "element84": {
        "provider": "element84",
        "label": "Element84 Earth Search v1",
        "catalog_url": "https://earth-search.aws.element84.com/v1",
        "auth": "none",
        "cog_direct": True,
        "processing_units": False,
        "active": True,
        "verified": True,
        "license": _COPERNICUS_LICENSE,
        "category": "imagery_scene",
        "coverage_yemen": True,
        "resolution": "10m (Sentinel-2), 30m (Landsat)",
        "note": "صور Sentinel-2 L2A خام (COG عامّ بلا مصادقة) — الافتراضيّ الحاليّ.",
    },
    "cdse": {
        "provider": "cdse",
        "label": "Copernicus Data Space (CDSE) + Sentinel Hub Process API",
        "catalog_url": "https://stac.dataspace.copernicus.eu/v1",
        "auth": "oauth2",
        "cog_direct": False,
        "processing_units": True,
        "active": True,
        "verified": True,
        "license": _COPERNICUS_LICENSE,
        "category": "imagery_scene",
        "coverage_yemen": True,
        "resolution": "10m/20m/60m (Sentinel-2)",
        # المسار الرسميّ الحاليّ لـSentinel: SciHub (scihub.copernicus.eu) أُغلِق أواخر
        # 2023 ⇒ لا يُضاف؛ CDSE هو البديل الرسميّ (STAC/OData/Process API + Browser).
        "note": "المصدر الرسميّ لـSentinel (بديل SciHub المُغلَق 2023). معالجة تستهلك وحدات.",
    },
    "planetary_computer": {
        "provider": "planetary_computer",
        "label": "Microsoft Planetary Computer",
        "catalog_url": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "auth": "sas-token (short-lived)",
        "cog_direct": True,
        "processing_units": False,
        "active": False,  # صادق: مُستعمَل كـSTAC-fallback URL فقط، لا مسار توقيع SAS مخصّص.
        "verified": True,
        "license": _COPERNICUS_LICENSE,
        "category": "imagery_scene",
        "coverage_yemen": True,
        "resolution": "10m–60m (Sentinel-2 L2A)",
        "recommended_use": "STAC fallback + HLS/DEM (يحتاج مُحوِّل توقيع SAS)",
        "note": "مُهيّأ كعنوان STAC احتياطيّ فقط؛ توقيع SAS المخصّص غير موصول بعد.",
    },
    "nasa_hls": {
        "provider": "nasa_hls",
        "label": "NASA HLS (HLSS30/HLSL30)",
        "catalog_url": "https://cmr.earthdata.nasa.gov/stac/LPCLOUD",
        "auth": "earthdata-login",
        "cog_direct": True,
        "processing_units": False,
        "active": False,  # صادق: غير مُنفَّذ (يحتاج Earthdata Login).
        "verified": True,
        "license": "US-Gov open (no commercial restriction)",
        "category": "imagery_scene",
        "coverage_yemen": True,  # كلّ اليابسة عالميّاً عدا Antarctica.
        "resolution": "30m",
        "recommended_use": "historical_backfill, NDVI baseline, seasonal anomaly trend",
        "note": (
            "مخطَّط للباكفيل التاريخيّ 30م (يغطّي اليمن)؛ غير موصول — يتطلّب مصادقة "
            "Earthdata + مُحوِّل واختبار عقد قبل active=True. غير مناسب لحدود الحقول الصغيرة."
        ),
    },
    "wapor": {
        "provider": "wapor",
        "label": "FAO WaPOR v3 (water productivity)",
        "catalog_url": "https://io.apps.fao.org/gismgr/api/v1",
        "auth": "none",
        "cog_direct": False,
        "processing_units": False,
        "active": False,  # صادق: لا مُحوِّل بعد.
        "verified": True,
        "license": "CC-BY-4.0 (commercial OK)",
        "category": "water_productivity",
        "coverage_yemen": True,  # اليمن ضمن الشرق الأدنى → L2 100م.
        "resolution": "100m (L2 Near-East), 300m (L1 global), 20m (L3 partner sites only)",
        "recommended_use": "water_productivity, actual_ET, biomass, regional/large-field analytics",
        "note": (
            "إنتاجيّة المياه/ET الفعليّ فوق الشرق الأدنى (يغطّي اليمن، L2 100م، 2018→الآن). "
            "مناسب للحيازات الكبيرة/الـpivots/المناطق/المحافظات — لا لحدود حقل دقيقة. "
            "غير موصول — يحتاج مُحوِّلاً واختبار عقد قبل active=True."
        ),
    },
    "worldcereal": {
        "provider": "worldcereal",
        "label": "ESA WorldCereal (crop/irrigation prior)",
        "catalog_url": "https://esa-worldcereal.org",
        "auth": "none (CC-BY partition only)",
        "cog_direct": False,
        "processing_units": False,
        "active": False,  # صادق: لا مُحوِّل بعد.
        "verified": True,
        "license": "CC-BY-4.0 (استعمل قسم CC-BY فقط؛ تجنّب NC/SA)",
        "category": "crop_prior",
        "coverage_yemen": True,  # منتج عالميّ 10م.
        "resolution": "10m",
        "recommended_use": "crop_extent_prior, irrigation_prior, confidence prior",
        "note": (
            "خرائط محاصيل/ريّ عالميّة 10م (تغطّي اليمن) — تُستعمل كأولويّة قرار مُثقَلة "
            "بالثقة لا حقيقة نهائيّة (الزراعة المُدرَّجة/الحيازات الصغيرة تُفاوِت الثقة). "
            "غير موصول — يحتاج مُحوِّلاً واختبار عقد قبل active=True."
        ),
    },
    "aster_gdem": {
        "provider": "aster_gdem",
        "label": "ASTER GDEM (NASA Earthdata / Japan Space Systems)",
        "catalog_url": "https://search.earthdata.nasa.gov",
        "auth": "earthdata-login",
        "cog_direct": False,
        "processing_units": False,
        "active": False,  # صادق: نموذج ارتفاعات، غير موصول (يحتاج Earthdata).
        "verified": True,
        "license": "open (NASA/METI, attribution)",
        "category": "dem",
        "coverage_yemen": True,  # يغطّي اليابسة بين ~83°N و83°S.
        "resolution": "~30m",
        "recommended_use": "DEM/slope/hillshade/contours (رفد terrain)",
        "note": (
            "نموذج ارتفاعات رقميّ ~30م يغطّي اليمن؛ رفدٌ لطبقات terrain القائمة. غير "
            "موصول — يحتاج Earthdata Login + مُحوِّل قبل active=True (تحميل يدويّ أوّليّ ممكن)."
        ),
    },
    "local_cog": {
        "provider": "local_cog",
        "label": "Local cached COG",
        "catalog_url": None,
        "auth": "none",
        "cog_direct": True,
        "processing_units": False,
        "active": True,
        "verified": True,
        "license": _COPERNICUS_LICENSE,
        "category": "imagery_scene",
        "note": "COGs مُنتَجة محليّاً ومُعادة الترطيب من قاعدة البيانات.",
    },
}


def active_providers() -> list[str]:
    """أسماء المزوّدين الموصولين فعلاً (active=True) — صدق لا طموح."""
    return [p for p, meta in PROVIDER_REGISTRY.items() if meta.get("active")]


def planned_providers() -> list[str]:
    """أسماء المزوّدين المُسجَّلين غير الموصولين بعد (active=False) — خارطة طريق صادقة."""
    return [p for p, meta in PROVIDER_REGISTRY.items() if not meta.get("active")]


# ── سِجِلّ المصادر البحثيّة/المكتبات (منفصل تماماً عن مزوّدي الصور) ───────────────────
# **صدق حاسم:** هذه **مكتبات/معماريّات/مجموعات بيانات بحثيّة** لا مزوّدو صور. تُفصَل عن
# ``PROVIDER_REGISTRY`` كي لا يخلط أحد PaddleRS/GeoTrellis بمزوّد صور. ``provides_imagery``
# صراحةً False — لا تُستبدَل بـCDSE/Element84/Planetary Computer/NASA HLS.
RESEARCH_REGISTRY: dict[str, dict[str, Any]] = {
    "gitee_paddlers": {
        "id": "gitee_paddlers",
        "label": "PaddleRS (Gitee mirror)",
        "type": "research_library",
        "provides_imagery": False,
        "recommended_use": [
            "segmentation",
            "change_detection",
            "super_resolution_experiment",
            "mask_to_geojson",
        ],
        "note": "أداة AI للاستشعار عن بعد — تحسين حدود الحقول/التقطيع/كشف التغيّر بعد SAM2/ExG.",
    },
    "gitee_geotrellis_landsat_tutorial": {
        "id": "gitee_geotrellis_landsat_tutorial",
        "label": "GeoTrellis Landsat Tutorial (Gitee)",
        "type": "architecture_reference",
        "provides_imagery": False,
        "recommended_use": [
            "dynamic_ndvi_tile_rendering",
            "ndwi_rendering",
            "tile_cache_design",
        ],
        "note": "مرجع معماريّ لتصيير COG→نافذة→مؤشّر→PNG ديناميكيّاً (يوافق هدف raster-service).",
    },
    "gitee_remote_sensing_datasets": {
        "id": "gitee_remote_sensing_datasets",
        "label": "RS change-detection / VHR datasets (Gitee mirrors)",
        "type": "dataset_reference",
        "provides_imagery": False,  # مجموعات بحثيّة محدودة، لا مزوّد تشغيليّ
        "recommended_use": ["training", "benchmark", "algorithm_validation"],
        "note": "NWPU VHR-10/RSOD/SpaceNet — تدريب/اختبار فقط، لا تغطية يوميّة ولا اليمن.",
    },
    "gitee_cdsystem": {
        "id": "gitee_cdsystem",
        "label": "CDSystem (PaddleRS inference service, Gitee)",
        "type": "architecture_reference",
        "provides_imagery": False,
        "recommended_use": [
            "gpu_inference_service_pattern",
            "cache_by_image_hash",
            "concurrency_limit",
        ],
        "note": "نمط خدمة استدلال GPU منفصلة (لو فُصِل boundary_ai/segmentation عن raster-service).",
    },
}


def research_sources() -> list[str]:
    """أسماء المصادر البحثيّة/المكتبات (لا مزوّدو صور — provides_imagery=False دائماً)."""
    return list(RESEARCH_REGISTRY.keys())


# ── سِجِلّ مصادر خارجيّة (تحميل يدويّ/تجاريّ/أحداث/تقييم) — منفصل عن المزوّدين الموصولين ──
# **صدق:** هذه مصادر صور حقيقيّة لكنّها **ليست مزوّدين موصولين** (لا STAC آليّ مُهيّأ):
# منها التجاريّ (مدفوع)، والأحداث فقط (كوارث)، واليدويّ (تحميل)، وقيد التقييم (ترخيص/API).
# ``active_provider=False`` دائماً؛ ``source_type`` يصنّف الطبيعة كي لا نبالغ في الادّعاء.
_EXTERNAL_SOURCE_TYPES = {
    "manual_download",
    "commercial",
    "event_open_data",
    "research_manual",
}

EXTERNAL_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "usgs_earthexplorer": {
        "id": "usgs_earthexplorer",
        "label": "USGS EarthExplorer",
        "source_type": "manual_download",
        "active_provider": False,
        "free": True,
        "verified": True,
        "provides_imagery": True,
        "coverage_yemen": True,
        "recommended_use": "Landsat/ASTER/DEM backfill (تسجيل + تحميل يدويّ)",
        "note": "منصّة USGS للبحث/طلب الصور — تحتاج تسجيل دخول؛ مناسبة للباكفيل اليدويّ.",
    },
    "planet_scope": {
        "id": "planet_scope",
        "label": "Planet PlanetScope (Planet Labs)",
        "source_type": "commercial",
        "active_provider": False,
        "free": False,
        "verified": True,
        "provides_imagery": True,
        "coverage_yemen": True,
        "resolution": "~3.7m (شبه يوميّ)",
        "recommended_use": "طبقة عالية الدقة مدفوعة (تدقيق/حدود)",
        "note": "تجاريّ باشتراك — لا يُفعَّل كمصدر مجانيّ يوميّ.",
    },
    "maxar_open_data": {
        "id": "maxar_open_data",
        "label": "Maxar Open Data Program",
        "source_type": "event_open_data",
        "active_provider": False,
        "free": True,  # مجانيّ لكن محصور بالأحداث/الكوارث فقط.
        "verified": True,
        "provides_imagery": True,
        "coverage_yemen": "event_only",
        "resolution": "<1m (قبل/بعد الحدث)",
        "recommended_use": "صور كوارث/أحداث فقط (لا تغطية يوميّة عامّة)",
        "note": "صور عالية الدقة للاستجابة للكوارث (ARD/COG/STAC) — ليست اشتراكاً يوميّاً.",
    },
    "china_gaofen": {
        "id": "china_gaofen",
        "label": "China Gaofen (GF-1/GF-6) data platform (CNSA)",
        "source_type": "research_manual",
        "active_provider": False,
        "free": "unverified",
        "verified": "partial",  # صدق: يحتاج تحقّق ترخيص/API/تسجيل/تغطية قبل الإنتاج.
        "requires_verification": True,
        "provides_imagery": True,
        "coverage_yemen": "unverified",
        "recommended_use": "تقييم بحثيّ فقط حتّى يُتحقَّق الترخيص/الـAPI/التسجيل",
        "note": "cnsageo.com يتيح بحث/تنزيل GF-1/GF-6 — لا يُعتمَد إنتاجيّاً قبل تحقّق عمليّ.",
    },
}


def external_sources() -> list[str]:
    """أسماء المصادر الخارجيّة (يدويّ/تجاريّ/أحداث/تقييم) — لا مزوّدون موصولون."""
    return list(EXTERNAL_SOURCE_REGISTRY.keys())


def sources_by_type(source_type: str) -> list[str]:
    """أسماء المصادر الخارجيّة من نوع مُعيَّن (manual_download/commercial/…)."""
    return [k for k, v in EXTERNAL_SOURCE_REGISTRY.items() if v.get("source_type") == source_type]


# ── اقتراح احتياطيّ مُهيكَل عند فشل/نفاد CDSE ────────────────────────────────────
_FALLBACK_REASONS = {
    "cdse_unconfigured": "اعتمادات CDSE غائبة (CDSE_CLIENT_ID/SECRET أو SH_CLIENT_ID/SECRET).",
    "cdse_quota_exhausted": "نفد رصيد وحدات معالجة CDSE لهذا الشهر (403 insufficient units).",
    "cdse_catalog_unavailable": "كتالوج CDSE غير متاح مؤقّتاً.",
}


def provider_fallback_suggestion(reason: str, *, current_provider: str = "cdse") -> dict[str, Any]:
    """اقتراح مُهيكَل صادق للتحوّل عن CDSE عند فشله/نفاده.

    يوجّه إلى Element84 (صور خام مجانيّة بلا وحدات معالجة) — نفس منطق الافتراض الحاليّ.
    مُهيكَل (قابل للقراءة آليّاً) بدل نصّ 503 حرّ، فيمكن للواجهة/العامل التصرّف عليه.
    """
    return {
        "current_provider": current_provider,
        "reason_code": reason,
        "reason": _FALLBACK_REASONS.get(reason, reason),
        "suggested_provider": "element84",
        "action": "set HISTORICAL_SEARCH_PROVIDER=element84",
        "why": (
            "Element84 يوفّر صور Sentinel-2 L2A خام (COG عامّ بلا مصادقة ولا وحدات "
            "معالجة CDSE) فيعمل الخطّ الزمنيّ التاريخيّ دون رصيد."
        ),
        "alternatives": [p for p in active_providers() if p not in {current_provider, "local_cog"}],
        "docs": "https://dataspace.copernicus.eu (شحن الرصيد) · https://earth-search.aws.element84.com/v1",
    }
