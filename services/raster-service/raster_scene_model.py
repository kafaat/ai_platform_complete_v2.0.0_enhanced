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
        # صدق التحقّق (docs-based، لا تخمين): النقطة keyless + عناصر mapsets (code/caption)
        # مُتحقَّقة من وثائق FAO؛ الغلاف الكامل/قراءة البكسل غير مُتحقَّقة حيّاً (بيئة محجوبة).
        "live_verified": False,
        "schema_verified_from_docs": True,
        "provides": ["evapotranspiration", "biomass", "water_productivity"],
        "activation_blockers": [
            "live FAO request",
            "contract fixture from real response",
            "Yemen AOI sample validation",
        ],
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
        # صدق: واجهة WorldCereal لم تُتحقَّق من مصدر موثوق في هذه البيئة (ESA محجوب) —
        # لا نكتب parser بلا مخطّط مُتحقَّق (شرط: no guessed schemas).
        "live_verified": False,
        "schema_verified_from_docs": False,
        "provides": ["crop_type_prior", "irrigation_prior", "confidence"],
        "activation_blockers": [
            "verify product access schema from authoritative docs",
            "live ESA/WorldCereal sample",
            "Yemen AOI validation + local threshold tuning",
        ],
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
    "copernicus_dem": {
        "provider": "copernicus_dem",
        "label": "Copernicus DEM GLO-30",
        "catalog_url": "https://registry.opendata.aws/copernicus-dem/",
        "auth": "none (AWS Open Data) / CDSE",
        "cog_direct": True,
        "processing_units": False,
        "active": False,  # صادق: DEM مُفضَّل لكن غير موصول (يحتاج مستورِد).
        "verified": True,
        "license": "open (ESA/Copernicus)",
        "category": "dem",
        "coverage_yemen": True,
        "resolution": "30m",
        "preferred_dem": True,  # المُفضَّل: جودة أعلى من ASTER في الدراسات الحديثة.
        "recommended_use": "DEM/slope/hillshade/contours/erosion (المصدر المُفضَّل)",
        "note": (
            "DEM المُفضَّل (COG عامّ عبر AWS Open Data؛ يوافق DEM_COLLECTION=cop-dem-glo-30). "
            "غير موصول — يحتاج مستورِد قبل active=True. ASTER/SRTM/NASADEM احتياطيّ."
        ),
    },
    "aster_gdem": {
        "provider": "aster_gdem",
        "label": "ASTER GDEM V003 (NASA Earthdata / Japan Space Systems)",
        "catalog_url": "https://search.earthdata.nasa.gov",
        "auth": "earthdata-login",
        "cog_direct": True,  # V003 يُوزَّع COG + NetCDF4.
        "processing_units": False,
        "active": False,  # صادق: نموذج ارتفاعات احتياطيّ، غير موصول (يحتاج Earthdata).
        "verified": True,
        "requires_earthdata_login": True,
        "license": "open (NASA/METI, attribution)",
        "category": "dem",
        "coverage_yemen": True,  # يغطّي اليابسة بين ~83°N و83°S (~99٪ من اليابسة).
        "resolution": "~30m (1 arc-second)",
        "preferred_dem": False,  # احتياطيّ خلف Copernicus DEM.
        "products": ["DEM", "NUM"],  # NUM = عدد المشاهد ⇒ إشارة جودة (dem_quality).
        "recommended_use": "DEM/slope/hillshade/contours/erosion (احتياطيّ مجانيّ)",
        "note": (
            "احتياطيّ DEM ~30م يغطّي اليمن؛ V003 يوزّع DEM+NUM (NUM إشارة جودة عبر "
            "dem_quality). غير موصول — يحتاج Earthdata Login + مستورِد (تحميل يدويّ أوّليّ ممكن)."
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


def dem_providers() -> list[str]:
    """أسماء مزوّدي نماذج الارتفاعات (category='dem')."""
    return [p for p, meta in PROVIDER_REGISTRY.items() if meta.get("category") == "dem"]


def preferred_dem() -> str | None:
    """اسم DEM المُفضَّل (preferred_dem=True) — Copernicus DEM حاليّاً، أو None."""
    for p, meta in PROVIDER_REGISTRY.items():
        if meta.get("category") == "dem" and meta.get("preferred_dem"):
            return p
    return None


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
    "manual_batch_download",
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
    "earthdata_wget_batch": {
        "id": "earthdata_wget_batch",
        "label": "NASA Earthdata batch import (wget/earthaccess + .netrc)",
        "source_type": "manual_batch_download",
        "active_provider": False,
        "free": True,
        "verified": True,
        "requires_earthdata_login": True,
        "provides_imagery": True,  # قناة تنزيل: HLS/MODIS/VIIRS + DEM + مناخ.
        "coverage_yemen": True,
        "supports": ["hls", "aster_gdem", "srtm", "nasadem", "modis", "viirs", "merra2"],
        "recommended_use": ["historical_backfill", "dem_import", "climate_archive"],
        "note": (
            "قناة استيراد دفعيّ (Earthdata Search → روابط/سكربت → wget/earthaccess → MinIO → "
            "تسجيل كـlocal_cog/terrain_asset). **الأمن:** الاعتماد عبر ~/.netrc (0600) أو "
            "مدير أسرار، **لا** كلمة مرور في سكربت/مستودع. سجّل كلّ مُستورَد بـchecksum + "
            "source_url + acquisition_date. ليس مزوّداً حيّاً حتّى يُبنى adapter."
        ),
    },
}


# ── نَسَب الأصول المُستورَدة يدويّاً (Earthdata batch وغيره) — صدق + أمن ──────────────
REQUIRED_IMPORT_PROVENANCE: tuple[str, ...] = ("checksum", "source_url", "acquisition_date")
_SECRET_FIELD_HINTS = {"password", "passwd", "netrc", "secret", "token", "credential"}


def imported_asset_provenance_ok(record: dict[str, Any]) -> dict[str, Any]:
    """يتحقّق أنّ سجلّ أصل مُستورَد يحمل النَّسَب الإلزاميّ ولا يُسرّب أسراراً.

    **صدق:** أصل مُستورَد بلا (checksum + source_url + acquisition_date) يُرفَض — لا أصل
    يتيم بلا مصدر/تحقّق. **أمن:** يُرفَض أيّ حقل يشبه سرّاً (password/token/netrc) — الاعتماد
    عبر ``.netrc``/مدير أسرار لا في السجلّ/المستودع. منطق صرف (بلا I/O).
    """
    if not isinstance(record, dict):
        return {
            "ok": False,
            "missing": list(REQUIRED_IMPORT_PROVENANCE),
            "leaked_secret_fields": [],
        }
    missing = [f for f in REQUIRED_IMPORT_PROVENANCE if not record.get(f)]
    leaked = [k for k in record if str(k).lower() in _SECRET_FIELD_HINTS]
    return {"ok": not missing and not leaked, "missing": missing, "leaked_secret_fields": leaked}


def external_sources() -> list[str]:
    """أسماء المصادر الخارجيّة (يدويّ/تجاريّ/أحداث/تقييم) — لا مزوّدون موصولون."""
    return list(EXTERNAL_SOURCE_REGISTRY.keys())


# ── سِجِلّ نماذج الذكاء الاصطناعيّ (foundation models) — منفصل عن مزوّدي الصور تماماً ──
# **صدق حاسم:** OlmoEarth (Ai2) نموذج أساس EO يعمل *فوق* الصور (Sentinel-1/2/Landsat)،
# **ليس مزوّد صور** (``provides_imagery=False``). لا يُغني عن CDSE/Element84. غير مُفعَّل:
# يحتاج أوزاناً + GPU + **تحقّق محلّيّ (اليمن)** قبل الاعتماد. لا يُختلَق embedding بدون ذلك.
AI_MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "olmoearth": {
        "id": "olmoearth",
        "label": "OlmoEarth (Ai2 / Allen Institute for AI)",
        "type": "ai_foundation_model",
        "provides_imagery": False,
        "active_provider": False,
        "verified": True,
        "requires_model_weights": True,
        "requires_satellite_time_series": True,
        "requires_local_validation_yemen": True,
        "requires_imagery_provider": ["sentinel1", "sentinel2", "landsat"],
        "coverage_note": "true_by_input_sources",  # المدخلات تغطّي اليمن؛ النموذج غير مُتحقَّق محلّيّاً.
        "recommended_use": [
            "embeddings",
            "crop_classification",
            "field_condition_similarity",
            "change_detection",
            "productivity_zone_features",
        ],
        "license": "open (Ai2) — راجع الرخصة قبل الإنتاج",
        "refs": [
            "arXiv: OlmoEarth (Stable Latent Image Modeling for Multimodal EO)",
            "github.com/allenai/olmoearth_pretrain",
            "huggingface: OlmoEarth-v1-Base (ViT-B, 89M)",
        ],
        "status": "research_or_planned_ai_adapter",
        "note": (
            "نموذج أساس متعدّد الوسائط فوق Sentinel-1/2/Landsat/DEM/WorldCereal/OSM — محرّك "
            "embeddings لا مزوّد صور. لا يُغني عن CDSE/Element84. غير مُفعَّل: أوزان + GPU + "
            "تحقّق محلّيّ (مدرّجات/حقول صغيرة/جفاف اليمن) قبل أيّ اعتماد إنتاجيّ."
        ),
    },
}


def ai_models() -> list[str]:
    """أسماء نماذج الذكاء الاصطناعيّ المُسجَّلة (لا مزوّدو صور — provides_imagery=False)."""
    return list(AI_MODEL_REGISTRY.keys())


def olmoearth_embedding_contract(*, has_weights: bool, inputs_available: bool) -> dict[str, Any]:
    """عقد إتاحة embedding من OlmoEarth — **صدق: لا يُختلَق embedding**.

    لا يُنفّذ استدلالاً هنا (يحتاج أوزاناً + GPU)؛ عقد إتاحة فقط. غياب الأوزان أو مدخلات
    السلاسل الزمنيّة (Sentinel-1/2/Landsat) ⇒ ``available=False`` بسبب صريح و``embedding=None``.
    حتّى عند توفّرهما لا يُعاد متّجه مُختلَق — الحالة ``ready_pending_local_validation`` فقط.
    """
    if not has_weights:
        return {"available": False, "reason": "no_model_weights", "embedding": None}
    if not inputs_available:
        return {"available": False, "reason": "no_satellite_time_series", "embedding": None}
    return {
        "available": True,
        "reason": None,
        "embedding": None,  # لا متّجه مُختلَق — الاستدلال الفعليّ خلف GPU + تحقّق محلّيّ.
        "status": "ready_pending_local_validation",
        "note_ar": "الأوزان والمدخلات متاحة؛ الاستدلال يتطلّب GPU + تحقّق محلّيّ (اليمن) قبل الاعتماد.",
    }


def olmoearth_runtime_status(checkpoint_path: str | None = None) -> dict[str, Any]:
    """تشخيص جاهزيّة OlmoEarth على العتاد (صادق قابل للتنفيذ) — **لا استدلال هنا**.

    يجيب: ما الذي ينقص لتفعيل OlmoEarth على هذا الجهاز؟ ``reason_code`` مُصنَّف (نمط
    تشخيص SAM2): ``weights_missing`` (ركّب الأوزان على المسار) · ``cuda_unavailable``
    (لا GPU) · ``library_missing`` (torch/olmoearth غير مثبّتة) · ``ready_pending_validation``
    (أوزان+GPU متاحة لكن **يبقى تحقّق محلّيّ يمنيّ** قبل التفعيل الإنتاجيّ — لا نُفعّل بلا benchmark).

    **صدق:** ``ready`` يبقى ``False`` دائماً حتّى بعد توفّر الأوزان/GPU — التفعيل قرار بشريّ
    بعد قياس محلّيّ (اليمن)؛ لا يُختلَق embedding ولا يُدّعى «يغطّي اليمن» بلا تدريب/تحقّق.
    """
    import os

    path = (
        checkpoint_path or os.getenv("OLMOEARTH_CHECKPOINT", "/models/olmoearth_v1_base.pt")
    ).strip()
    base = {"model": "olmoearth", "ready": False, "checkpoint_expected": path}
    if not path or not os.path.isfile(path):
        return {
            **base,
            "reason_code": "weights_missing",
            "reason": f"أوزان OlmoEarth غير موجودة على {path or '—'}",
        }
    try:
        import torch  # ثقيل — داخل الدالّة.
    except ImportError:
        return {
            **base,
            "reason_code": "library_missing",
            "reason": "torch غير مثبّت (بيئة بلا استدلال)",
        }
    try:
        cuda_ok = bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001 — أيّ خطأ torch ⇒ غير جاهز بصدق
        cuda_ok = False
    if not cuda_ok:
        return {
            **base,
            "reason_code": "cuda_unavailable",
            "reason": "torch.cuda.is_available()==False — لا GPU",
        }
    return {
        **base,
        "reason_code": "ready_pending_validation",
        "reason": None,
        "note_ar": (
            "الأوزان وGPU متاحة؛ يبقى تحقّق محلّيّ يمنيّ (benchmark مقابل NDVI/V60.3) قبل "
            "التفعيل الإنتاجيّ — لا embedding مُختلَق ولا ادّعاء تغطية محلّيّة بلا قياس."
        ),
    }


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
