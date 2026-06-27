"""models.py — نماذج وتعدادات خدمة الراستر (Pydantic/StrEnum).

مُستخرَجة حرفيّاً من ``main.py`` (تفكيك المرحلة 1) لتقليل ضخامة الملفّ المركزيّ
وتجميع العقود (contracts) في موضع واحد. السلوك محفوظ بالكامل: لا تغيير في الحقول
أو الافتراضات أو التحقّقات؛ ``main.py`` يعيد تصديرها عبر ``from models import …``
فتبقى متاحة كـ``main.X`` لكلّ مستورِد قائم (مثل الاختبارات).

نقيّة بلا I/O ولا اعتماد على globals الخدمة — تعتمد فقط على pydantic/enum.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


# ─── النماذج (مطابقة لأنواع الجوال) ───────────────────────────────
class IndicatorKind(StrEnum):
    ndvi = "ndvi"
    evi = "evi"
    savi = "savi"
    ndwi = "ndwi"
    ndmi = "ndmi"
    gndvi = "gndvi"
    fapar = "fapar"
    vari = "vari"
    gli = "gli"
    tgi = "tgi"
    ndre = "ndre"
    msi = "msi"  # NDRE (نيتروجين/red-edge) + MSI (إجهاد مائي)
    msavi = "msavi"  # Modified SAVI (تصحيح تربة ذاتي L) — كثافة نباتيّة منخفضة
    moisture = "moisture"  # مؤشّر رطوبة (NDMI-style: NIR/SWIR1) للواجهة
    # مؤشّرات التربة (Sentinel-2) — تسدّ نقص: السابقة كلّها نباتيّة
    bsi = "bsi"
    bi = "bi"
    bi2 = "bi2"
    ndti = "ndti"
    dbsi = "dbsi"
    ndsi = "ndsi"
    satvi = "satvi"


class SourceFormat(StrEnum):
    sentinel2_l2a = "sentinel2_l2a"
    sentinel2_l1c = "sentinel2_l1c"
    landsat8 = "landsat8"
    drone_orthomosaic = "drone_orthomosaic"
    custom = "custom"


class JobStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BandMapping(BaseModel):
    red: int | None = None
    green: int | None = None
    blue: int | None = None
    nir: int | None = None
    rededge: int | None = None  # red-edge (B5/B6/B7) — لـNDRE (النيتروجين)
    swir1: int | None = None
    swir2: int | None = None  # لمؤشّرات التربة (BSI/NDTI/SATVI)
    scl: int | None = None
    clp: int | None = None  # s2cloudless cloud probability (0..100 or 0..1), optional
    clm: int | None = None  # s2cloudless cloud mask: 1=cloud, 0=clear, optional


class ProcessRequest(BaseModel):
    tenant_id: str
    field_id: str | None = None
    raster_url: str | None = None
    indicator: IndicatorKind
    source_format: SourceFormat
    bands: BandMapping
    clip_polygon_geojson: dict | None = None
    apply_cloud_mask: bool = True
    # تحويل DN→انعكاس [0,1] للمؤشّرات المعتمِدة على المقياس (EVI/SAVI/MSAVI). افتراضيّاً
    # تُحترَم بيانات scale/offset المُعلَنة في الراستر؛ هذان يتجاوزانها يدويّاً لمصادر
    # تورّد DN خاماً دون إعلان (مثل بعض أصول Sentinel-2: reflectance_scale=0.0001).
    reflectance_scale: float | None = None
    reflectance_offset: float | None = None
    tiling_strategy: str = "pyramid"
    zoom_min: int = 10
    zoom_max: int = 18
    # provenance (#7): تثبيت المصدر لإعادة الإنتاج
    scene_id: str | None = None  # item_id من STAC search
    capture_datetime: str | None = None  # وقت التقاط القمر
    # مؤشّر محسوب مسبقاً (CDSE Process API): الراستر نطاق-واحد جاهز للمؤشّر — لا band math.
    precomputed_index: bool = False
    provider: str | None = None  # مصدر الصورة (مثل "cdse" / "element84") للأصل (provenance)


class BatchProcessRequest(BaseModel):
    """معالجة دفعيّة: عدّة مؤشّرات من نفس المشهد في مهمّة واحدة (كفاءة).

    بدل طلب لكلّ مؤشّر (يقرأ النطاقات مرّة لكلّ منها)، هذا يقرأ المشهد مرّة
    ويحسب كلّ المؤشّرات — توفير I/O كبير، مهمّ لقلب النظام تحت الحمل.
    """

    tenant_id: str
    field_id: str | None = None
    raster_url: str | None = None
    indicators: list[IndicatorKind]  # قائمة المؤشّرات (NDVI + NDRE + NDSI ...)
    source_format: SourceFormat
    bands: BandMapping
    clip_polygon_geojson: dict | None = None
    apply_cloud_mask: bool = True
    scene_id: str | None = None
    capture_datetime: str | None = None


class SearchRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    datetime_start: str
    datetime_end: str
    max_cloud_pct: float = 30
    limit: int = 20


class HistoricalBackfillPreset(StrEnum):
    """Preset windows for historical imagery backfill.

    auto_12_months: default immediate history for newly-created fields.
    extended_3_years: agronomic season comparison and recurring weak-zone analysis.
    research_5_years: enterprise/research tier; heavier cost and storage.
    custom: explicit from_date/to_date or months.
    """

    auto_12_months = "auto_12_months"
    extended_3_years = "extended_3_years"
    research_5_years = "research_5_years"
    custom = "custom"


class HistoricalBackfillRequest(BaseModel):
    """Backfill historical satellite imagery for a field using current geometry.

    The request is intentionally configurable instead of hard-coded. This allows the
    platform to run a cheap automatic 12-month bootstrap on field creation, and let
    users opt into 3-year/5-year or custom history only when they need it.
    """

    tenant_id: str | None = None
    preset: HistoricalBackfillPreset = HistoricalBackfillPreset.auto_12_months
    from_date: str | None = None
    to_date: str | None = None
    months: int | None = Field(default=None, ge=1, le=120)
    indices: list[IndicatorKind] = Field(
        default_factory=lambda: [
            IndicatorKind.ndvi,
            IndicatorKind.ndmi,
            IndicatorKind.savi,
            IndicatorKind.evi,
        ]
    )
    max_cloud_pct: float = Field(default=30, ge=0, le=100)
    limit_per_month: int = Field(default=2, ge=1, le=8)
    apply_cloud_mask: bool = True
    source: str = Field(default="sentinel-2")
    clip_polygon_geojson: dict | None = None
    dry_run: bool = False


class AutoBackfillPolicy(BaseModel):
    enabled: bool = True
    default_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.auto_12_months
    extended_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.extended_3_years
    research_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.research_5_years
    default_indices: list[str] = ["ndvi", "ndmi", "savi", "evi"]
    max_cloud_pct: float = 30
    note: str = (
        "Use auto_12_months on field creation; expose extended_3_years and "
        "research_5_years as explicit user/plan toggles."
    )


class SceneCandidate(BaseModel):
    """A STAC/scene candidate normalized for quality ranking.

    Inspired by Sentinel Hub least-cloud mosaicking and common STAC quality filters:
    AOI cloud percentage is strongest, then recency, then field coverage and provider
    quality/confidence. All fields are optional so provider-specific payloads can be
    ranked without brittle adapters.
    """

    item_id: str | None = None
    datetime: str | None = None
    cloud_cover_pct: float | None = None
    aoi_cloud_pct: float | None = None
    coverage_pct: float | None = None
    view_angle: float | None = None
    provider_quality: float | None = None
    source: str | None = None
    properties: dict | None = None


class SceneRankRequest(BaseModel):
    scenes: list[SceneCandidate]
    mode: str = Field(default="best_available")
    max_cloud_pct: float = Field(default=40, ge=0, le=100)
    prefer_recent_days: int = Field(default=45, ge=1, le=3650)


class MosaicPlanRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    datetime_start: str
    datetime_end: str
    max_cloud_pct: float = Field(default=40, ge=0, le=100)
    limit: int = Field(default=20, ge=1, le=100)
    mosaic_rule: str = Field(default="least_cloud_then_recent")


class GeoParquetExportRequest(BaseModel):
    tenant_id: str | None = None
    field_ids: list[str] | None = None
    include_raster_assets: bool = True
    output_name: str = Field(default="field_analytics")


class TimeSeriesAnalyzeRequest(BaseModel):
    scene_values: list[dict]  # [{"datetime": "...", "mean": 0.5}, ...]


class ManagementZonesRequest(BaseModel):
    pixel_values: list[float]
    n_zones: int = 3
    base_rate: float | None = None
    strategy: str = "compensate"


class ChangeDetectRequest(BaseModel):
    field_id: str
    index: str = "ndvi"
    date_before: str
    date_after: str
    grid_before: list[list[float | None]]  # شبكة المؤشّر للتاريخ الأقدم
    grid_after: list[list[float | None]]  # شبكة المؤشّر للتاريخ الأحدث
    slight_threshold: float = 0.1
    severe_threshold: float = 0.2


class FvcComputeRequest(BaseModel):
    field_id: str
    date: str
    ndvi_grid: list[list[float | None]]  # شبكة NDVI مُحسبة من COG
    method: str = "cumulative_frequency"  # | global_constant | dynamic_range
    ndvi_soil: float | None = None  # لـdynamic_range فقط
    ndvi_veg: float | None = None


class SarRviRequest(BaseModel):
    field_id: str
    date: str
    vv_grid: list[list[float | None]]  # σ°_VV (قدرة خطّيّة أو dB)
    vh_grid: list[list[float | None]]  # σ°_VH
    in_db: bool = False  # هل القيم بالديسيبل؟ (تُحوَّل للخطّي قبل النسبة)


class TerrainRequest(BaseModel):
    dem_url: str
    pixel_size_m: float = 30.0


class ProcessFromStacRequest(BaseModel):
    """مدخل المعالجة من مشهد STAC متعدّد الملفّات (COG لكلّ نطاق)."""

    tenant_id: str | None = None
    indicator: IndicatorKind = IndicatorKind.ndvi
    band_hrefs: dict[str, str]  # {"red": url, "nir": url, "scl": url, ...}
    scene_id: str | None = None
    capture_datetime: str | None = None
    apply_cloud_mask: bool = True
    clip_polygon_geojson: dict | None = None
    source_format: SourceFormat = SourceFormat.sentinel2_l2a


class ProcessCdseRequest(BaseModel):
    """مدخل معالجة CDSE: bbox + هندسة + مؤشّرات + نافذة زمنيّة."""

    tenant_id: str | None = None
    indicators: list[str] = ["ndvi"]
    bbox: list[float]  # [west, south, east, north] بـEPSG:4326
    geometry: dict | None = None  # Polygon GeoJSON (قصّ على الحقل)
    lookback_days: int = 30
    max_cloud_pct: float = 40.0
    # Optional explicit scene/date window. When set, CDSE processing must not
    # silently use a different "latest" mosaic, because the UI date selector and
    # tile cache depend on acquisition_date matching the requested scene.
    date_from: str | None = None
    date_to: str | None = None


class PrescriptionRequest(BaseModel):
    index: str = "ndvi"
    date: str = "latest"
    grid: int = Field(32, ge=2, le=256)
    n_zones: int = Field(3, ge=2, le=6)
    base_rate: float | None = None  # معدّل أساسي (سماد/بذار) لاشتقاق معدّل المناطق
    strategy: str = "compensate"  # compensate | protect


class FieldChangeRequest(BaseModel):
    index: str = "ndvi"
    date_a: str  # التاريخ الأقدم (before)
    date_b: str  # التاريخ الأحدث (after)
    grid: int = Field(32, ge=2, le=256)
    slight_threshold: float = 0.1
    severe_threshold: float = 0.2


class SalinityClassifyRequest(BaseModel):
    ndsi: float


class SalinityFitRequest(BaseModel):
    samples: list[dict]  # [{"ndsi","ece_ds_m","extraction_method"}]
