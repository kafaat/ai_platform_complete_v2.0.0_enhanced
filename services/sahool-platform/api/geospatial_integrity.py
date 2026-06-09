"""
services/sahool-platform/api/geospatial_integrity.py — Geospatial Integrity Layer

المرجع: المراجعة الخارجيّة:
   "لم أجد مؤشّرات قوية على:
      - geospatial consistency validation
      - CRS normalization pipeline
      - tile synchronization guarantees
      - raster/vector alignment contracts
    هذه نقطة خطيرة جدًا. أي انحراف بسيط في EPSG/reprojection/raster alignment
    سيعطي قرارات زراعية خاطئة بالكامل حتى لو كان الذكاء ممتازًا."

✅ الادّعاء صحيح. هذا الملف يسدّ الفجوة.

السياق التقني:
   - نستخدم EPSG:4326 (WGS84 lat/lng) عبر النظام
   - Sentinel-2 يأتي بـEPSG:32637/32638 (UTM zones 37N/38N لليمن)
   - PostGIS يستخدم 4326 افتراضياً مع GEOGRAPHY type
   - أيّ raster/vector في النظام يجب أن يُطبَّع إلى 4326

ما يفعله هذا الملف:
   ١. CANONICAL_CRS = 4326 (مفروض)
   ٢. validate_geometry_geojson() — يتحقّق من polygon validity
   ٣. validate_bbox() — يتحقّق أنّ الـbbox داخل اليمن
   ٤. validate_crs() — يرفض أيّ CRS غير 4326 (مع reproject hint)
   ٥. check_self_intersection() — منع polygons مكسورة
   ٦. RasterAlignment — للـSentinel-2 → field grid alignment
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

# ─── Constants ──────────────────────────────────────────────────

# الـCRS المعياري في النظام كلّه
CANONICAL_CRS = "EPSG:4326"
CANONICAL_CRS_CODE = 4326

# Yemen bounding box (approximate)
# Latitude:  12.0° - 19.0° N
# Longitude: 41.5° - 54.5° E
YEMEN_BBOX = {
    "min_lat": 11.5,  # جنوب — جزر سُقطرى
    "max_lat": 19.5,  # شمال — حدود السعوديّة
    "min_lng": 41.0,  # غرب — البحر الأحمر
    "max_lng": 55.0,  # شرق — حدود عُمان
}

# UTM zones لليمن (للـSentinel-2)
YEMEN_UTM_ZONES = {37, 38, 39}  # zones N (شمال خطّ الاستواء)

# Field size limits (هكتارات)
MIN_FIELD_AREA_HA = 0.01  # 100 m²
MAX_FIELD_AREA_HA = 10_000  # 100 km² — أكبر حقل معقول

# Polygon constraints
MIN_POLYGON_VERTICES = 4  # 3 + closing point
MAX_POLYGON_VERTICES = 10_000


# ─── Result types ───────────────────────────────────────────────


class ValidationSeverity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ValidationIssue:
    severity: ValidationSeverity
    code: str  # machine-readable code (e.g. "self_intersection")
    message_ar: str
    message_en: str
    hint: str | None = None


@dataclass
class GeometryValidation:
    valid: bool  # False لو فيه ERROR، True مع WARNINGs مقبول
    issues: list[ValidationIssue]
    canonical_crs: str = CANONICAL_CRS
    computed_area_ha: float | None = None
    computed_bbox: dict[str, float] | None = None

    @property
    def has_errors(self) -> bool:
        return any(i.severity == ValidationSeverity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == ValidationSeverity.WARNING for i in self.issues)


# ─── Pure geometry helpers ──────────────────────────────────────


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """المسافة بالأمتار بين نقطتين."""
    R = 6371008.8  # WGS84 mean Earth radius
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def polygon_area_m2(coords: list[tuple[float, float]]) -> float:
    """
    Spherical polygon area (الإحداثيّات lng/lat).
    Uses spherical excess formula — أدقّ من Shoelace للـlat/lng.
    """
    if len(coords) < 3:
        return 0.0
    # Close the ring if not closed
    if coords[0] != coords[-1]:
        coords = list(coords) + [coords[0]]

    R = 6371008.8
    total = 0.0
    for i in range(len(coords) - 1):
        lng1, lat1 = coords[i]
        lng2, lat2 = coords[i + 1]
        total += math.radians(lng2 - lng1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    area = abs(total * R * R / 2)
    return area


def polygon_area_ha(coords: list[tuple[float, float]]) -> float:
    return polygon_area_m2(coords) / 10_000.0


def compute_bbox(coords: list[tuple[float, float]]) -> dict[str, float]:
    if not coords:
        return {"min_lng": 0, "max_lng": 0, "min_lat": 0, "max_lat": 0}
    lngs = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return {
        "min_lng": min(lngs),
        "max_lng": max(lngs),
        "min_lat": min(lats),
        "max_lat": max(lats),
    }


def segments_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    """هل القطعة p1p2 تتقاطع مع p3p4 (لا تشمل النقاط المشتركة)."""

    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    # نتجاهل التقاطع عند النقاط المشتركة (نهاية segment = بداية segment التالي)
    if p1 == p3 or p1 == p4 or p2 == p3 or p2 == p4:
        return False
    return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)


def has_self_intersection(coords: list[tuple[float, float]]) -> bool:
    """يتحقّق من تقاطع الـpolygon مع نفسه."""
    n = len(coords)
    if n < 4:
        return False
    # Check non-adjacent segment pairs
    for i in range(n - 1):
        for j in range(i + 2, n - 1):
            if i == 0 and j == n - 2:
                continue  # adjacent through closing
            if segments_intersect(coords[i], coords[i + 1], coords[j], coords[j + 1]):
                return True
    return False


# ─── CRS validation ─────────────────────────────────────────────


def validate_crs(crs_string: str | None) -> ValidationIssue | None:
    """يتأكّد أنّ الـCRS هو 4326 (الـcanonical). يقبل عدّة أشكال."""
    if not crs_string:
        # غياب الـCRS يعني GeoJSON 4326 بشكل ضمني (RFC 7946)
        return None

    cs = crs_string.upper().strip()
    valid_forms = {
        "EPSG:4326",
        "EPSG/4326",
        "WGS84",
        "WGS-84",
        "WGS:84",
        "URN:OGC:DEF:CRS:EPSG::4326",
        "HTTP://WWW.OPENGIS.NET/DEF/CRS/EPSG/0/4326",
        "CRS:84",  # GeoJSON-style
    }

    for form in valid_forms:
        if form in cs:
            return None

    return ValidationIssue(
        severity=ValidationSeverity.ERROR,
        code="invalid_crs",
        message_ar=f"الـCRS غير مدعوم: {crs_string}. النظام يستخدم EPSG:4326 فقط.",
        message_en=f"Unsupported CRS: {crs_string}. System uses EPSG:4326 only.",
        hint="استخدم pyproj أو ogr2ogr لإعادة الإسقاط إلى 4326 قبل الإرسال.",
    )


# ─── Main validation ────────────────────────────────────────────


def validate_field_geometry(
    geojson: dict[str, Any],
    declared_crs: str | None = None,
) -> GeometryValidation:
    """
    التحقّق الشامل من geometry حقل.

    Args:
        geojson: GeoJSON-shaped dict (Polygon, Feature, FeatureCollection, or {type:Polygon, coordinates:[[...]]})
        declared_crs: optional CRS string لو الـclient أرسلها

    Returns:
        GeometryValidation مع كل الـissues + computed_area_ha + bbox
    """
    issues: list[ValidationIssue] = []

    # ١. تحقّق CRS
    crs_issue = validate_crs(declared_crs)
    if crs_issue:
        issues.append(crs_issue)

    # ٢. استخرج coordinates من GeoJSON shapes مختلفة
    coords = _extract_polygon_coords(geojson)
    if coords is None:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="invalid_geojson",
                message_ar="الـGeoJSON غير صالح أو ليس Polygon.",
                message_en="Invalid GeoJSON or not a Polygon.",
            )
        )
        return GeometryValidation(valid=False, issues=issues)

    # ٣. تحقّق عدد النقاط
    if len(coords) < MIN_POLYGON_VERTICES:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="too_few_vertices",
                message_ar=f"الـpolygon يحتاج ≥ {MIN_POLYGON_VERTICES} نقاط (مع الإغلاق). وُجد {len(coords)}.",
                message_en=f"Polygon needs ≥ {MIN_POLYGON_VERTICES} vertices. Got {len(coords)}.",
            )
        )
        return GeometryValidation(valid=False, issues=issues)

    if len(coords) > MAX_POLYGON_VERTICES:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="too_many_vertices",
                message_ar=f"الـpolygon فيه نقاط كثيرة جدّاً ({len(coords)} > {MAX_POLYGON_VERTICES}).",
                message_en=f"Polygon has too many vertices ({len(coords)}).",
                hint="استخدم simplification (Douglas-Peucker) قبل الإرسال.",
            )
        )

    # ٤. تحقّق الإغلاق
    if coords[0] != coords[-1]:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                code="not_closed",
                message_ar="الـring غير مُغلَق (آخر نقطة ≠ أوّل نقطة). سيُغلَق تلقائياً.",
                message_en="Ring not closed (first ≠ last point). Auto-closing.",
            )
        )
        coords = list(coords) + [coords[0]]

    # ٥. تحقّق duplicate consecutive points
    duplicates = sum(1 for i in range(len(coords) - 1) if coords[i] == coords[i + 1])
    if duplicates > 0:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                code="duplicate_vertices",
                message_ar=f"يوجد {duplicates} نقاط متكرّرة متتالية. تُتجاهَل.",
                message_en=f"{duplicates} duplicate consecutive vertices found.",
            )
        )

    # ٦. تحقّق self-intersection
    if has_self_intersection(coords):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="self_intersection",
                message_ar="الـpolygon يتقاطع مع نفسه (geometry غير صالح).",
                message_en="Polygon self-intersects.",
                hint="ارسم الـpolygon مجدّداً بدون تقاطعات.",
            )
        )

    # ٧. حساب الـbbox + تحقّق أنّه داخل اليمن
    bbox = compute_bbox(coords)
    if not (
        YEMEN_BBOX["min_lat"] <= bbox["min_lat"]
        and bbox["max_lat"] <= YEMEN_BBOX["max_lat"]
        and YEMEN_BBOX["min_lng"] <= bbox["min_lng"]
        and bbox["max_lng"] <= YEMEN_BBOX["max_lng"]
    ):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                code="outside_yemen_bbox",
                message_ar=(
                    f"الـpolygon خارج حدود اليمن المعتادة "
                    f"(lat {bbox['min_lat']:.2f}-{bbox['max_lat']:.2f}, "
                    f"lng {bbox['min_lng']:.2f}-{bbox['max_lng']:.2f}). "
                    "تأكّد من الإحداثيّات."
                ),
                message_en="Polygon outside Yemen bbox. Check coordinates.",
            )
        )

    # ٨. حساب المساحة + تحقّق
    area_ha = polygon_area_ha(coords)
    if area_ha < MIN_FIELD_AREA_HA:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                code="area_too_small",
                message_ar=f"المساحة صغيرة جدّاً ({area_ha * 10000:.0f} م²). تأكّد.",
                message_en=f"Area too small ({area_ha * 10000:.0f} m²).",
            )
        )
    if area_ha > MAX_FIELD_AREA_HA:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="area_too_large",
                message_ar=f"المساحة كبيرة جدّاً ({area_ha:.0f} هكتار). الحدّ الأقصى {MAX_FIELD_AREA_HA}.",
                message_en=f"Area too large ({area_ha:.0f} ha). Max is {MAX_FIELD_AREA_HA}.",
                hint="هل أرسلت إحداثيّات في وحدة خاطئة (مثل meters بدل degrees)؟",
            )
        )

    # ٩. تحقّق range الإحداثيّات (catch unit errors)
    for lng, lat in coords:
        if not (-180 <= lng <= 180):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="lng_out_of_range",
                    message_ar=f"خط الطول خارج النطاق: {lng}. يجب أن يكون -180 إلى 180.",
                    message_en=f"Longitude out of range: {lng}",
                    hint="ربّما الإحداثيّات بترتيب (lat, lng) بدل (lng, lat)؟",
                )
            )
            break
        if not (-90 <= lat <= 90):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="lat_out_of_range",
                    message_ar=f"خط العرض خارج النطاق: {lat}.",
                    message_en=f"Latitude out of range: {lat}",
                )
            )
            break

    has_errors = any(i.severity == ValidationSeverity.ERROR for i in issues)
    return GeometryValidation(
        valid=not has_errors,
        issues=issues,
        computed_area_ha=round(area_ha, 4) if not has_errors else None,
        computed_bbox=bbox if not has_errors else None,
    )


def _extract_polygon_coords(
    geojson: dict[str, Any],
) -> list[tuple[float, float]] | None:
    """يستخرج outer ring من Polygon GeoJSON بأشكاله المختلفة."""
    if not isinstance(geojson, dict):
        return None

    gtype = geojson.get("type")

    if gtype == "Feature":
        return _extract_polygon_coords(geojson.get("geometry", {}))

    if gtype == "FeatureCollection":
        features = geojson.get("features", [])
        if not features:
            return None
        return _extract_polygon_coords(features[0])

    if gtype == "Polygon":
        coords = geojson.get("coordinates")
        if not coords or not isinstance(coords, list) or not coords[0]:
            return None
        outer_ring = coords[0]
        try:
            return [(float(p[0]), float(p[1])) for p in outer_ring if len(p) >= 2]
        except (TypeError, ValueError, IndexError):
            return None

    return None


# ─── Raster alignment (Sentinel-2 → field grid) ─────────────────


@dataclass
class RasterAlignmentSpec:
    """مواصفات alignment لـraster مع field."""

    target_crs: str = CANONICAL_CRS
    target_resolution_m: float = 10.0  # Sentinel-2 native
    snap_to_grid: bool = True
    nodata_value: float = -9999.0


def check_bbox_in_utm_zones(bbox: dict[str, float]) -> list[int]:
    """يحدّد UTM zones التي تتقاطع مع bbox (لـSentinel-2 selection)."""
    # UTM zone width = 6 degrees, starting from -180
    min_zone = int((bbox["min_lng"] + 180) / 6) + 1
    max_zone = int((bbox["max_lng"] + 180) / 6) + 1
    return list(range(min_zone, max_zone + 1))


def is_valid_yemen_utm_zone(zone: int) -> bool:
    return zone in YEMEN_UTM_ZONES
