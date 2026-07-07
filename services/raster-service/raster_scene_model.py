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
        "license": _COPERNICUS_LICENSE,
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
        "license": _COPERNICUS_LICENSE,
        "note": "كتالوج + معالجة خادميّة تستهلك وحدات معالجة (رصيد شهريّ).",
    },
    "planetary_computer": {
        "provider": "planetary_computer",
        "label": "Microsoft Planetary Computer",
        "catalog_url": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "auth": "sas-token (short-lived)",
        "cog_direct": True,
        "processing_units": False,
        "active": False,  # صادق: مُستعمَل كـSTAC-fallback URL فقط، لا مسار توقيع SAS مخصّص.
        "license": _COPERNICUS_LICENSE,
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
        "license": "US-Gov open (no commercial restriction)",
        "note": "مخطَّط للباكفيل التاريخيّ 30م؛ غير موصول (يتطلّب مصادقة Earthdata).",
    },
    "local_cog": {
        "provider": "local_cog",
        "label": "Local cached COG",
        "catalog_url": None,
        "auth": "none",
        "cog_direct": True,
        "processing_units": False,
        "active": True,
        "license": _COPERNICUS_LICENSE,
        "note": "COGs مُنتَجة محليّاً ومُعادة الترطيب من قاعدة البيانات.",
    },
}


def active_providers() -> list[str]:
    """أسماء المزوّدين الموصولين فعلاً (active=True) — صدق لا طموح."""
    return [p for p, meta in PROVIDER_REGISTRY.items() if meta.get("active")]


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
