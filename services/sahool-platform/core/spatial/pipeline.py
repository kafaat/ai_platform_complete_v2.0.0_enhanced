"""
core.spatial.pipeline
=====================
خط أنابيب الاستشعار المكاني — من القمر إلى البلاطة فوق الخريطة.

المراحل (حسب رؤية المستخدم):
  ١. الجلب      كل 3-5 أيام عند مرور القمر (S2 بصري / S1 رادار)
  ٢. القص       لحدود الحقل (AOI) فقط — لا تحميل مديرية كامل
  ٣. فحص السحب  C6: سحب >20% → S1 (رادار يخترق) أو دمج S1+S2
  ٤. الحساب     NDVI/NDMI/SI لكل بكسل → raster
  ٥. التخزين    PostGIS raster + تحويل PNG/GeoTIFF للعرض
  ٦. Timeline   تواريخ + صور مصغّرة، مقارنة زمنية

الصدق التقني:
  • منطق المراحل (القرارات، البوابات) يعمل الآن.
  • المعالجة الفعلية للـ GeoTIFF تحتاج rasterio/GDAL (المرحلة ٣، الصور الحقيقية).
  • التخزين PostGIS يحتاج PostgreSQL (مؤجّل — SQLite الآن لـ metadata).
  • offline-first الموبايل = طبقة تطبيق (تُبنى مع الموبايل).

هذا الملف يعرّف الواجهات والقرارات، جاهزة للتوصيل بالصور الحقيقية.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

_logger = logging.getLogger(__name__)


class Satellite(str, Enum):
    S2_OPTICAL = "sentinel-2"  # بصري — 10م، كل 5 أيام، يحجبه السحب
    S1_RADAR = "sentinel-1"  # رادار — 10م، كل 6 أيام، يخترق السحب


class ImageQuality(str, Enum):
    USABLE = "usable"  # سحب < 20%
    CLOUDY = "cloudy"  # سحب > 20% → بديل
    FUSED = "fused"  # دمج S1+S2


@dataclass
class FieldAOI:
    """منطقة الاهتمام = حدود الحقل (تأتي من PostGIS / GeoJSON)."""

    tenant_id: str
    field_id: str
    # polygon vertices (lon, lat) — حدود الحقل الفعلية
    polygon: list[tuple[float, float]]
    min_lon: float = 0.0
    min_lat: float = 0.0
    max_lon: float = 0.0
    max_lat: float = 0.0

    def __post_init__(self):
        if self.polygon:
            lons = [p[0] for p in self.polygon]
            lats = [p[1] for p in self.polygon]
            self.min_lon, self.max_lon = min(lons), max(lons)
            self.min_lat, self.max_lat = min(lats), max(lats)


@dataclass
class AcquisitionPlan:
    """خطة الجلب — متى وأي قمر."""

    aoi: FieldAOI
    revisit_days: int = 5
    prefer: Satellite = Satellite.S2_OPTICAL
    fallback: Satellite = Satellite.S1_RADAR


def decide_source(cloud_cover_pct: float) -> tuple[Satellite, ImageQuality]:
    """بوابة السحب (C6): يقرّر المصدر حسب الغطاء السحابي.

    القرار الذي وصفه المستخدم: سحب → S1، أو دمج S1+S2.
    العتبة 20% تطابق connectors.base.CLOUD_THRESHOLD_PCT (مصدر الحقيقة الموحّد).
    """
    if cloud_cover_pct < 20:  # == base.CLOUD_THRESHOLD_PCT
        return Satellite.S2_OPTICAL, ImageQuality.USABLE
    if cloud_cover_pct < 60:
        # سحب جزئي → دمج (S2 المتاح + S1 لسدّ الفجوات)
        return Satellite.S2_OPTICAL, ImageQuality.FUSED
    # سحب كثيف → رادار فقط
    return Satellite.S1_RADAR, ImageQuality.CLOUDY


@dataclass
class RasterTile:
    """بلاطة مؤشر مكاني — تُعرض فوق الخريطة. metadata في SQLite،
    البيانات الفعلية (PNG/GeoTIFF) في ملف/PostGIS لاحقاً."""

    tenant_id: str
    field_id: str
    index_name: str  # ndvi / ndmi / salinity
    capture_date: str  # ISO
    satellite: str
    quality: str
    cloud_cover_pct: float
    # مسارات الأصول (تُملأ عند المعالجة الفعلية):
    geotiff_path: str = ""  # المصدر الخام
    png_overlay_path: str = ""  # للعرض فوق الخريطة
    thumbnail_path: str = ""  # للـ timeline
    # إحصاءات (تُحسب من الـ raster):
    mean_value: float | None = None
    min_value: float | None = None
    max_value: float | None = None


def compute_ndvi_from_bands(nir, red):
    """NDVI = (NIR - Red)/(NIR + Red). يعمل على numpy arrays.

    هذه المعادلة جاهزة؛ تستقبل band arrays من GeoTIFF الحقيقي.
    """
    try:
        import numpy as np

        nir = np.asarray(nir, dtype=float)
        red = np.asarray(red, dtype=float)
        denom = nir + red
        # تجنّب القسمة على صفر
        ndvi = np.where(denom != 0, (nir - red) / denom, np.nan)
        return ndvi
    except ImportError:
        return None


@dataclass
class TimelineEntry:
    """مدخل في شريط الزمن أسفل الخريطة — تاريخ + صورة مصغّرة."""

    capture_date: str
    index_name: str
    thumbnail_path: str
    mean_value: float | None
    quality: str


def build_timeline(tiles: list[RasterTile]) -> list[TimelineEntry]:
    """يبني شريط الزمن للمقارنة (الأحدث أولاً)."""
    entries = [
        TimelineEntry(
            capture_date=t.capture_date,
            index_name=t.index_name,
            thumbnail_path=t.thumbnail_path,
            mean_value=t.mean_value,
            quality=t.quality,
        )
        for t in tiles
    ]
    return sorted(entries, key=lambda e: e.capture_date, reverse=True)


def detect_temporal_change(
    timeline: list[TimelineEntry],
    index_name: str,
) -> dict:
    """كشف التغيّر الزمني (إنذار مبكر): هل المؤشر يتدهور؟"""
    series = [e for e in timeline if e.index_name == index_name and e.mean_value is not None]
    if len(series) < 2:
        return {"trend": "insufficient_data", "note_ar": "يحتاج صورتين على الأقل"}
    series.sort(key=lambda e: e.capture_date)
    latest = series[-1].mean_value
    previous = series[-2].mean_value
    change = latest - previous
    if abs(change) < 0.05:
        trend, note = "stable", "مستقر"
    elif change < 0:
        trend, note = "declining", f"⚠️ تدهور {abs(change):.2f} — انتبه (إنذار مبكر)"
    else:
        trend, note = "improving", f"تحسّن {change:.2f}"
    return {"trend": trend, "change": round(change, 3), "note_ar": note}


# ── مراجعة #4: حساب مساحة الحقل من الحدود (تلقائياً) ──
def polygon_area_ha(coords: list[tuple[float, float]]) -> float:
    """مساحة مضلّع بالهكتار من إحداثيات (lon, lat) بالدرجات.
    يستخدم صيغة Shoelace مع إسقاط متري تقريبي (يكفي لحقل صغير).
    للدقة العالية لاحقاً: إسقاط UTM كامل. coords مغلقة أو مفتوحة."""
    import math

    if len(coords) < 3:
        return 0.0
    # متوسط خط العرض لإسقاط تقريبي (متر/درجة)
    lat_mean = sum(c[1] for c in coords) / len(coords)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat_mean))
    # تحويل لأمتار نسبية
    pts = [
        ((lon - coords[0][0]) * m_per_deg_lon, (lat - coords[0][1]) * m_per_deg_lat)
        for lon, lat in coords
    ]
    # Shoelace
    area_m2 = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area_m2 += x1 * y2 - x2 * y1
    area_m2 = abs(area_m2) / 2.0
    return round(area_m2 / 10_000.0, 2)  # م² → هكتار


# ── مؤشر التربة العارية BSI + تقدير النسيج (S8) — موجّه لا حاكم ──
def compute_bsi_from_bands(swir1, red, nir, blue):
    """مؤشر التربة العارية (Bare Soil Index) من نطاقات Sentinel-2.
    BSI = ((SWIR1+Red) - (NIR+Blue)) / ((SWIR1+Red) + (NIR+Blue))
    مرتفع = تربة عارية/جافة؛ منخفض = غطاء نباتي/رطوبة.
    يُستخدم لتقدير *نوع* التربة على المناطق العارية فقط."""
    num = (swir1 + red) - (nir + blue)
    den = (swir1 + red) + (nir + blue)
    return num / den if den != 0 else 0.0


def estimate_soil_texture(bsi: float, ndvi: float) -> dict:
    """يقدّر نسيج التربة التقريبي (S8) من BSI + السطوع.
    ⚠️ موجّه لا حاكم: تقدير استرشادي للمناطق العارية، لا يرفع BLOCKED.
    الحاكمات الصارمة (ملوحة S3، pH S4) تبقى تتطلب المختبر."""
    # على الغطاء النباتي الكثيف لا يُقاس النسيج بصرياً
    if ndvi > 0.4:
        return {
            "texture": None,
            "confidence": "none",
            "note_ar": "غطاء نباتي كثيف — النسيج لا يُقاس بصرياً، يحتاج عيّنة حقلية",
        }
    # تصنيف تقريبي على التربة العارية (BSI أعلى ≈ أكثر رملية/جفافاً)
    if bsi >= 0.3:
        tex, conf = "رملي (تقديري)", "low"
    elif bsi >= 0.1:
        tex, conf = "طمي-رملي (تقديري)", "low"
    elif bsi >= -0.1:
        tex, conf = "طميي (تقديري)", "low"
    else:
        tex, conf = "طيني/رطب (تقديري)", "low"
    return {
        "texture": tex,
        "confidence": conf,
        "note_ar": f"{tex} — تقدير استشعاري استرشادي. للتأكيد: عيّنة حقلية أو مختبر.",
    }


# ── مؤشّرات تمييز التربة (تدقّق تصنيف النسيج) — موجّهة لا حاكمة ──
def clay_minerals_ratio(swir1, swir2):
    """نسبة المعادن الطينية = SWIR1/SWIR2 (نطاقا Sentinel-2 B11/B12).
    مرتفع = محتوى طيني أعلى. يميّز الطين عن الرمل أدقّ من BSI وحده."""
    return swir1 / swir2 if swir2 != 0 else 0.0


def iron_oxide_ratio(red, blue):
    """نسبة أكاسيد الحديد = Red/Blue. مرتفع = تربة غنية بالحديد (حمراء).
    شائع في بعض الأراضي اليمنية — يساعد تمييز نوع التربة."""
    return red / blue if blue != 0 else 0.0


def refine_soil_texture(
    bsi: float, ndvi: float, clay_ratio: float = None, iron_ratio: float = None
) -> dict:
    """يدقّق تقدير النسيج بدمج BSI مع مؤشّري الطين/الحديد (إن توفّرا).
    ⚠️ موجّه لا حاكم: ثقة منخفضة دائماً، يوجّه لعيّنة. الحاكمات للمختبر."""
    base = estimate_soil_texture(bsi, ndvi)
    if base["texture"] is None:  # تحت غطاء نباتي
        return base
    notes = [base["texture"]]
    # تدقيق بالطين (clay_ratio > 1.0 يدعم الطين)
    if clay_ratio is not None and clay_ratio > 1.05 and "رملي" in base["texture"]:
        notes.append("لكن نسبة الطين مرتفعة — قد يكون طميياً")
    # تدقيق بالحديد
    if iron_ratio is not None and iron_ratio > 1.3:
        notes.append("غنية بأكاسيد الحديد (تربة حمراء محتملة)")
    return {
        "texture": base["texture"],
        "confidence": "low",  # يبقى منخفضاً — استشعار لا مختبر
        "refined_with": [
            k for k, v in [("clay", clay_ratio), ("iron", iron_ratio)] if v is not None
        ],
        "note_ar": " · ".join(notes) + " — تقدير استشعاري. للتأكيد: تحليل مخبري.",
    }


# ── كشف مرحلة النمو من سلسلة NDVI الزمنية (يكمّل GDD في fao56) ──
def detect_growth_stage_from_ndvi(ndvi_series: list[tuple[int, float]]) -> dict:
    """يستنتج مرحلة النمو من شكل منحنى NDVI الزمني (يوم السنة, NDVI).
    مبني على أبحاث محكّمة (RMSE <2.9 يوم للقمح من Sentinel-2).

    يكمّل GDD (الذي يحسب المرحلة من الحرارة): NDVI يرى النبات فعلاً،
    GDD يتوقّع من المناخ. تقاطعهما يزيد الثقة.

    ⚠️ موجّه: الاستشعار يرى الغطاء؛ المزارع يؤكّد بالمشاهدة الميدانية."""
    if not ndvi_series or len(ndvi_series) < 3:
        return {
            "stage": None,
            "confidence": "none",
            "note_ar": "سلسلة NDVI قصيرة (<3 نقاط) — لا يمكن استنتاج المرحلة",
        }

    # تنعيم ضدّ تذبذب الغيوم (الأبحاث المحكّمة تنعّم السلسلة قبل التحليل).
    # متوسّط متحرّك ثلاثي يخفّف القيم الشاذّة (غيمة تخفض NDVI فجأة).
    _raw = sorted(ndvi_series, key=lambda p: p[0])
    _vals = [v for _, v in _raw]
    if len(_vals) >= 3:
        _smoothed = [_vals[0]]
        for i in range(1, len(_vals) - 1):
            _smoothed.append((_vals[i - 1] + _vals[i] + _vals[i + 1]) / 3.0)
        _smoothed.append(_vals[-1])
        # كشف الشذوذ: نمط V (هبوط حادّ ثم ارتفاع) يشير لغيمة عابرة.
        # النمو الطبيعي رتيب؛ الهبوط المفاجئ المتبوع بارتفاع = غيمة لا فيزيولوجيا.
        _cloud_flag = False
        for i in range(1, len(_vals) - 1):
            _dip = _vals[i] < _vals[i - 1] - 0.20 and _vals[i] < _vals[i + 1] - 0.20
            if _dip:
                _cloud_flag = True
                break
        ndvi_series = [(_raw[i][0], _smoothed[i]) for i in range(len(_raw))]
    else:
        _cloud_flag = False
    # رتّب زمنياً واستخرج القيم
    series = sorted(ndvi_series, key=lambda p: p[0])
    values = [v for _, v in series]
    current = values[-1]
    peak = max(values)
    peak_idx = values.index(peak)
    n = len(values)

    # تحليل الاتجاه (آخر نقطتين)
    rising = values[-1] > values[-2] if n >= 2 else True

    # استنتاج المرحلة من موضع القيمة على المنحنى
    if current < 0.25 and peak_idx >= n - 2:
        stage, stage_ar = "emergence", "الإنبات/البداية"
    elif rising and current < peak * 0.85:
        stage, stage_ar = "development", "النمو الخضري (التفريع/الاستطالة)"
    elif current >= peak * 0.85:
        stage, stage_ar = "mid_peak", "الذروة (الإزهار/امتلاء الحبوب)"
    elif not rising and current > 0.3:
        stage, stage_ar = "senescence", "الشيخوخة (نضج/قرب الحصاد)"
    else:
        stage, stage_ar = "late_harvest", "متأخّر (حصاد محتمل)"

    return {
        "stage": stage,
        "stage_ar": stage_ar,
        "current_ndvi": round(current, 3),
        "peak_ndvi": round(peak, 3),
        "confidence": "low" if _cloud_flag else "estimate",  # غيوم → ثقة أقل
        "cloud_noise_detected": _cloud_flag,
        "note_ar": (
            f"المرحلة المُقدَّرة: {stage_ar} (NDVI={current:.2f}). "
            + (
                "⚠️ تذبذب حادّ في السلسلة (غيوم محتملة) — الثقة منخفضة، أعد التحليل بصورة صافية. "
                if _cloud_flag
                else ""
            )
            + "تقدير من الأقمار — أكّده بالمشاهدة الميدانية أو GDD."
        ),
    }


def crop_type_consistency_check(
    observed_ndvi_peak: float, expected_crop: str, expected_peak_range: tuple[float, float]
) -> dict:
    """يتحقّق أن منحنى NDVI يطابق المحصول المُدخَل (يكشف الشذوذ).
    لا يستبدل إدخال المزارع للصنف — يؤكّده أو ينبّه لشذوذ."""
    lo, hi = expected_peak_range
    consistent = lo <= observed_ndvi_peak <= hi
    return {
        "expected_crop": expected_crop,
        "consistent": consistent,
        "confidence": "estimate",
        "note_ar": (
            f"ذروة NDVI ({observed_ndvi_peak:.2f}) "
            f"{'متّسقة مع' if consistent else 'لا تتّسق مع'} "
            f"المحصول المُدخَل ({expected_crop})."
            + ("" if consistent else " راجع الصنف أو ابحث عن إجهاد.")
        ),
    }


# ── LAI (مؤشّر مساحة الورقة) من الطيف — للكتلة الحيوية ──
def estimate_lai_from_ndvi(ndvi: float) -> dict:
    """يقدّر LAI (مساحة الورقة) من NDVI عبر علاقة لوغاريتمية تجريبية.
    LAI = -ln((NDVI_inf - NDVI)/(NDVI_inf - NDVI_soil)) / k  (تقريب مبسّط).
    مؤشّر للكتلة الحيوية → مدخل لتقدير الإنتاج النسبي.

    ⚠️ موجّه: تقدير طيفي. المعايرة الدقيقة تحتاج LAI meter ميداني (P4).
    لا يُنتج إنتاجاً مطلقاً — لا معايرة إنتاج بعد (مبدأ الصدق)."""
    # ── رصد جودة البيانات (إضافيّ فقط — لا يغيّر السلوك) ──
    # نُمرّر القيمة على سجلّ سياسات الجودة (api.data_quality) لتسجيل أيّ مخالفة
    # (مثل NDVI خارج [-1, 1]) كـ«مُلاحَظة» فقط. هذا يُظهِر مخالفات السياسة من
    # السجلّ دون لمس التحقّق القديم أدناه (فلتر «< 0» قرار زراعيّ مقصود يبقى كما هو).
    # الإنفاذ الكامل (استخدام السجلّ للبوابة/التنظيف) خطوة لاحقة مقصودة تحتاج
    # إقراراً زراعيّاً. ملفوف كاملاً بـ try/except كي لا يُسقِط المسار أبداً.
    try:
        from api.data_quality import evaluate_record

        _violations = evaluate_record({"ndvi": ndvi})
        for _v in _violations:
            _logger.warning(
                "مخالفة جودة بيانات [%s] في الحقل '%s' بالقيمة %r: %s",
                _v.get("rule_id"),
                _v.get("field"),
                _v.get("value"),
                _v.get("message_ar"),
            )
    except Exception:
        # api قد لا يكون قابلاً للاستيراد من core في بعض السياقات — نتجاوز بصمت.
        pass

    if ndvi is None or ndvi < 0:
        return {"lai": None, "confidence": "none", "note_ar": "NDVI غير صالح"}
    # تقريب تجريبي شائع: LAI ≈ (NDVI relationship)، مقصوص [0, 7]
    ndvi_soil, ndvi_inf, k = 0.15, 0.90, 0.55
    if ndvi <= ndvi_soil:
        lai = 0.0
    elif ndvi >= ndvi_inf:
        lai = 7.0
    else:
        import math

        lai = -math.log((ndvi_inf - ndvi) / (ndvi_inf - ndvi_soil)) / k
        lai = max(0.0, min(7.0, lai))
    # تصنيف الكثافة
    if lai < 1.0:
        density = "غطاء متناثر"
    elif lai < 3.0:
        density = "غطاء معتدل"
    elif lai < 5.0:
        density = "غطاء كثيف"
    else:
        density = "غطاء كثيف جداً"
    return {
        "lai": round(lai, 2),
        "density_ar": density,
        "confidence": "estimate",
        "note_ar": f"LAI تقديري ≈ {lai:.1f} ({density}). تقدير طيفي — للمعايرة: قياس LAI ميداني.",
    }
