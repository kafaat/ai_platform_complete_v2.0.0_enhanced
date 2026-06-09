"""
core.spatial.indicators
========================
طبقة المؤشرات المكانية — تكشف *أين* المشكلة، بإحداثية يمكن الوصول لها.

المنطق المكاني (يعمل الآن بـ numpy، جاهز لـ GeoTIFF الحقيقي):
  ١. يستقبل grid من قيم مؤشر (NDVI/NDMI/SI...) + إطار جغرافي (bbox)
  ٢. يكشف "مناطق الاهتمام": بكسلات تحت/فوق عتبة، متجاورة (clusters)
  ٣. يحوّل كل منطقة لإحداثية مركزية (lat/lon) يمكن الوصول لها
  ٤. يربطها بمعرفة المزارع المكانية (إن وُجدت)
  ٥. يُخرج: منطقة + إحداثية + شدّة + تفسير محتمل

ما يصلح للعرض المكاني (يتغيّر عبر الحقل):
  NDVI, NDMI, NDWI, SI (ملوحة), CWSI
ما لا يصلح (قيمة واحدة للحقل): ET₀, السعر — تبقى في المايسترو العام.

التخزين الفعلي للـ raster (PostGIS) ومعالجة GeoTIFF = المرحلة ٣
(عند توفّر الصور الحقيقية). هذا المنطق يعمل عليها حين تصل.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


class SpatialIndex(str, Enum):
    """المؤشرات القابلة للعرض المكاني (لكل بكسل)."""

    NDVI = "ndvi"  # صحة الغطاء — منخفض = ضعف/إجهاد
    NDMI = "ndmi"  # رطوبة المحتوى — منخفض = جفاف
    NDWI = "ndwi"  # ماء — منخفض = جفاف
    SI = "salinity"  # ملوحة — مرتفع = بقعة مالحة
    CWSI = "cwsi"  # إجهاد مائي — مرتفع = إجهاد
    BSI = "bare_soil"  # نسيج/نوع التربة العارية — موجّه لا حاكم (S8)


# اتجاه القلق: هل القيمة المنخفضة أم المرتفعة هي المشكلة؟
_LOW_IS_PROBLEM = {SpatialIndex.NDVI, SpatialIndex.NDMI, SpatialIndex.NDWI}
_HIGH_IS_PROBLEM = {SpatialIndex.SI, SpatialIndex.CWSI}
# BSI ليس "مشكلة" بل تصنيف — يُفسَّر لا يُنذَر


@dataclass
class GeoBBox:
    """الإطار الجغرافي للـ grid (لتحويل البكسل لإحداثية)."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def pixel_to_lonlat(self, row: int, col: int, n_rows: int, n_cols: int):
        """يحوّل (صف، عمود) في الـ grid لإحداثية (lon, lat)."""
        lon = self.min_lon + (col + 0.5) / n_cols * (self.max_lon - self.min_lon)
        # row 0 = أعلى الصورة = أقصى شمال (lat الأكبر)
        lat = self.max_lat - (row + 0.5) / n_rows * (self.max_lat - self.min_lat)
        return round(lon, 5), round(lat, 5)


class Severity(str, Enum):
    HIGH = "🔴 شديد"
    MEDIUM = "🟡 متوسط"
    LOW = "🟢 طفيف"


@dataclass
class ZoneOfInterest:
    """منطقة اهتمام مكتشفة — بإحداثية يمكن الوصول لها."""

    index: SpatialIndex
    center_lon: float
    center_lat: float
    pixel_count: int
    mean_value: float
    field_mean: float  # متوسط الحقل (للمقارنة)
    severity: Severity
    interpretation_ar: str
    farmer_knowledge_match: str = ""  # معرفة المزارع المؤكِّدة (إن وُجدت)
    directs_sampling: bool = False  # هل يوجّه أخذ عينة (يسدّ BLOCKED)?


def detect_zones_of_interest(
    grid: list[list[float]],  # قيم المؤشر (raster مبسّط)
    index: SpatialIndex,
    bbox: GeoBBox,
    threshold_std: float = 1.0,  # كم انحراف معياري عن المتوسط = منطقة اهتمام
    min_cluster: int = 3,  # أقل عدد بكسلات متجاورة
) -> list[ZoneOfInterest]:
    """يكشف مناطق القيم الشاذّة (أعلى/أقل من المتوسط بانحراف معياري).

    لا يخترع: يقارن كل بكسل بإحصاء الحقل نفسه. منطقة الاهتمام = انحراف حقيقي.
    """
    if not _HAS_NUMPY:
        return []
    arr = np.array(grid, dtype=float)
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return []

    field_mean = float(np.mean(valid))
    field_std = float(np.std(valid))
    if field_std == 0:
        return []  # الحقل متجانس — لا منطقة اهتمام

    n_rows, n_cols = arr.shape
    low_problem = index in _LOW_IS_PROBLEM

    # قناع البكسلات الشاذّة في الاتجاه المقلق
    if low_problem:
        mask = arr < (field_mean - threshold_std * field_std)
    else:
        mask = arr > (field_mean + threshold_std * field_std)

    # تجميع البكسلات المتجاورة (connected components مبسّط)
    clusters = _connected_components(mask, min_cluster)

    zones = []
    for cluster in clusters:
        rows = [r for r, c in cluster]
        cols = [c for r, c in cluster]
        cr, cc = int(np.mean(rows)), int(np.mean(cols))
        lon, lat = bbox.pixel_to_lonlat(cr, cc, n_rows, n_cols)
        vals = [arr[r, c] for r, c in cluster]
        mean_val = float(np.mean(vals))

        deviation = abs(mean_val - field_mean) / field_std
        severity = (
            Severity.HIGH
            if deviation >= 2.0
            else Severity.MEDIUM
            if deviation >= 1.5
            else Severity.LOW
        )

        zones.append(
            ZoneOfInterest(
                index=index,
                center_lon=lon,
                center_lat=lat,
                pixel_count=len(cluster),
                mean_value=round(mean_val, 3),
                field_mean=round(field_mean, 3),
                severity=severity,
                interpretation_ar=_interpret(index, mean_val, field_mean),
                directs_sampling=(index in (SpatialIndex.NDVI, SpatialIndex.SI)),
            )
        )
    return sorted(zones, key=lambda z: -z.pixel_count)


def _connected_components(mask, min_size: int) -> list[list[tuple]]:
    """تجميع البكسلات الشاذّة المتجاورة (4-connectivity)."""
    n_rows, n_cols = mask.shape
    visited = set()
    clusters = []
    for r in range(n_rows):
        for c in range(n_cols):
            if mask[r, c] and (r, c) not in visited:
                # BFS
                stack = [(r, c)]
                comp = []
                while stack:
                    cr, cc = stack.pop()
                    if (cr, cc) in visited:
                        continue
                    if not (0 <= cr < n_rows and 0 <= cc < n_cols):
                        continue
                    if not mask[cr, cc]:
                        continue
                    visited.add((cr, cc))
                    comp.append((cr, cc))
                    stack += [(cr + 1, cc), (cr - 1, cc), (cr, cc + 1), (cr, cc - 1)]
                if len(comp) >= min_size:
                    clusters.append(comp)
    return clusters


def _interpret(index: SpatialIndex, val: float, field_mean: float) -> str:
    """تفسير محتمل (فرضية، لا تشخيص قاطع)."""
    if index == SpatialIndex.NDVI:
        return (
            "غطاء نباتي ضعيف — فرضيات محتملة: ملوحة، نقص ري، "
            "نقص تغذية، أو إصابة. يحتاج تحقّقاً ميدانياً."
        )
    if index == SpatialIndex.SI:
        return "مؤشر ملوحة مرتفع — بقعة مالحة محتملة. خذ عينة تربة (S3)."
    if index in (SpatialIndex.NDMI, SpatialIndex.NDWI):
        return "رطوبة منخفضة — منطقة جافة محتملة. راجع توزيع الري."
    if index == SpatialIndex.CWSI:
        return "إجهاد مائي مرتفع — يحتاج ري عاجل في هذه البقعة."
    return "قيمة شاذّة تحتاج فحصاً."


def link_farmer_knowledge(
    zones: list[ZoneOfInterest],
    farmer_knowledge: list,  # FarmerKnowledge مكانية مُتحقَّقة
) -> list[ZoneOfInterest]:
    """يربط منطقة الاهتمام بمعرفة المزارع المكانية (إن طابقت النطاق)."""
    for z in zones:
        for fk in farmer_knowledge:
            scope = getattr(fk, "spatial_scope", "").lower()
            # ربط بسيط بالاتجاه (north/south/...) — يُحسّن بـ polygon لاحقاً
            if any(d in scope for d in ["north", "شمال"]) and z.center_lat > z.field_mean:
                z.farmer_knowledge_match = getattr(fk, "content_ar", "")
    return zones


@dataclass
class SoilZone:
    """منطقة تربة مصنّفة من BSI — لخريطة تنوّع النسيج (موجّه لا حاكم)."""

    center_lon: float
    center_lat: float
    pixel_count: int
    texture_class: str  # رملي / طمي-رملي / طميي / طيني (تقديري)
    mean_bsi: float
    confidence: str = "low"  # دائماً low — استشعار لا مختبر
    directs_sampling: bool = True  # دائماً يوجّه لعيّنة تأكيد
    note_ar: str = ""


def classify_soil_zones(
    bsi_grid: list[list[float]],
    ndvi_grid: list[list[float]],
    bbox: GeoBBox,
    min_cluster: int = 3,
) -> list[SoilZone]:
    """يقسّم الحقل لمناطق نسيج تربة من شبكة BSI — خريطة تنوّع التربة.

    يختلف عن detect_zones_of_interest: لا يكشف شذوذاً، بل يصنّف كل بكسل
    لفئة نسيج ثم يجمّع المتجاور. موجّه لا حاكم: ثقة low دائماً،
    يتخطّى البكسلات تحت الغطاء النباتي (NDVI>0.4)، يوجّه دائماً لعيّنة.
    """
    if not _HAS_NUMPY:
        return []
    bsi = np.array(bsi_grid, dtype=float)
    ndvi = np.array(ndvi_grid, dtype=float)
    if bsi.shape != ndvi.shape or bsi.size == 0:
        return []

    n_rows, n_cols = bsi.shape

    # صنّف كل بكسل عارٍ (NDVI<=0.4) لفئة نسيج برمز رقمي
    def texture_code(b: float) -> int:
        if b >= 0.3:
            return 4  # رملي
        if b >= 0.1:
            return 3  # طمي-رملي
        if b >= -0.1:
            return 2  # طميي
        return 1  # طيني/رطب

    _CODE_AR = {
        4: "رملي (تقديري)",
        3: "طمي-رملي (تقديري)",
        2: "طميي (تقديري)",
        1: "طيني/رطب (تقديري)",
    }

    # شبكة الفئات (0 = مُتخطّى: غطاء نباتي أو NaN)
    codes = np.zeros((n_rows, n_cols), dtype=int)
    for r in range(n_rows):
        for c in range(n_cols):
            if np.isnan(bsi[r, c]) or np.isnan(ndvi[r, c]) or ndvi[r, c] > 0.4:
                continue
            codes[r, c] = texture_code(float(bsi[r, c]))

    # جمّع البكسلات المتجاورة من نفس الفئة
    zones: list[SoilZone] = []
    for cls in (1, 2, 3, 4):
        mask = codes == cls
        for cluster in _connected_components(mask, min_cluster):
            rows = [r for r, c in cluster]
            cols = [c for r, c in cluster]
            cr, cc = int(np.mean(rows)), int(np.mean(cols))
            lon, lat = bbox.pixel_to_lonlat(cr, cc, n_rows, n_cols)
            mean_b = float(np.mean([bsi[r, c] for r, c in cluster]))
            tex = _CODE_AR[cls]
            zones.append(
                SoilZone(
                    center_lon=lon,
                    center_lat=lat,
                    pixel_count=len(cluster),
                    texture_class=tex,
                    mean_bsi=round(mean_b, 3),
                    note_ar=f"{tex} — تقدير استشعاري. للتأكيد: عيّنة حقلية أو مختبر.",
                )
            )
    return sorted(zones, key=lambda z: -z.pixel_count)
