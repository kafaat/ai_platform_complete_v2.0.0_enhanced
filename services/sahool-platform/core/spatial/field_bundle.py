"""
sahool_core.spatial.field_bundle
=================================
حزمة عرض الحقل — تجمع كل الطبقات المكانية في استجابة واحدة منظّمة.

الفجوة المسدودة: الواجهة كانت تطلب الحدود من مكان، المؤشّرات من آخر،
العيّنات من ثالث، الحسّاسات من رابع — وتركّب يدوياً. هذه الوحدة تنتج
"بطاقة الحقل البصرية" الكاملة: استجابة واحدة، الواجهة تركّبها.

النموذج المعياري:
  FieldVisualBundle:
    - boundary: حدود الحقل (Polygon GeoJSON)
    - zones: مناطق الاهتمام (FeatureCollection)
    - raster_current: PNG imageOverlay الحالي (bytes أو path)
    - timeline: قائمة snapshots تاريخية (للشريط الزمني)
    - sample_points: نقاط أخذ العيّنات (lab_requests بإحداثيات)
    - sensors: مواقع الحسّاسات (Geo-tagged observations)
    - activities: نقاط أحداث المزرعة (activity_log بإحداثيات)
    - legend: وسيلة إيضاح الألوان (للمؤشّر الحالي)

هذا النموذج هو "العقد" بين النواة والواجهة — يضمن أن كل عنصر يصل
بنمط محدّد، الواجهة لا تحتاج معرفة كيف تُجلب البيانات.

النواة محايدة العارض: نُنتج GeoJSON معياري + PNG، أيّ مكتبة (Leaflet/
Mapbox/MapLibre) تستهلكها.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field


@dataclass
class TimelineSnapshot:
    """نقطة على شريط الزمن — مرجع لا raster كامل."""

    snapshot_id: str
    captured_at: str
    indicator: str
    coverage_pct: float
    cloud_pct: float | None
    source: str
    has_png: bool  # هل PNG محفوظ في DB (للعرض السريع)؟


@dataclass
class SamplePoint:
    """موقع أخذ عيّنة تربة/ماء."""

    request_id: int
    lon: float
    lat: float
    sample_purpose: str  # nutrient / salinity / texture / ph
    status: str  # pending / received / cancelled
    requested_at: str


@dataclass
class SensorLocation:
    """موقع حسّاس مع آخر قراءة (مرجع لا سلسلة)."""

    device_id: str
    sensor_type: str
    lon: float
    lat: float
    last_value: float | None
    last_reading_at: str | None
    confidence: str  # medium دائماً للحسّاسات (مبدأ سهول)


@dataclass
class ActivityMarker:
    """علامة نشاط على الخريطة."""

    activity_id: str
    activity_type: str
    status: str
    lon: float
    lat: float
    planned_date: str | None
    completed_date: str | None


@dataclass
class FieldVisualBundle:
    field_id: str
    boundary_geojson: dict | None  # Polygon Feature
    zones_geojson: dict | None  # FeatureCollection
    raster_png_base64: str | None  # data URI جاهز للـimg src
    raster_bounds: dict | None  # {south,west,north,east}
    indicator: str | None  # ndvi / ndmi / bivariate
    timeline: list[TimelineSnapshot] = field(default_factory=list)
    sample_points: list[SamplePoint] = field(default_factory=list)
    sensors: list[SensorLocation] = field(default_factory=list)
    activities: list[ActivityMarker] = field(default_factory=list)
    legend: list[dict] = field(default_factory=list)
    warnings_ar: list[str] = field(default_factory=list)

    def to_response(self) -> dict:
        """تحويل لاستجابة JSON قياسية. لا اختراع — None يبقى null صريح."""
        return {
            "field_id": self.field_id,
            "boundary": self.boundary_geojson,
            "zones": self.zones_geojson,
            "raster": {
                "png_base64": self.raster_png_base64,
                "bounds": self.raster_bounds,
                "indicator": self.indicator,
            }
            if self.raster_png_base64
            else None,
            "timeline": [
                {
                    "snapshot_id": t.snapshot_id,
                    "captured_at": t.captured_at,
                    "indicator": t.indicator,
                    "coverage_pct": t.coverage_pct,
                    "cloud_pct": t.cloud_pct,
                    "source": t.source,
                    "has_png": t.has_png,
                }
                for t in self.timeline
            ],
            "sample_points": [
                {
                    "request_id": s.request_id,
                    "lon": s.lon,
                    "lat": s.lat,
                    "purpose": s.sample_purpose,
                    "status": s.status,
                    "requested_at": s.requested_at,
                }
                for s in self.sample_points
            ],
            "sensors": [
                {
                    "device_id": s.device_id,
                    "sensor_type": s.sensor_type,
                    "lon": s.lon,
                    "lat": s.lat,
                    "last_value": s.last_value,
                    "last_reading_at": s.last_reading_at,
                    "confidence": s.confidence,
                }
                for s in self.sensors
            ],
            "activities": [
                {
                    "activity_id": a.activity_id,
                    "type": a.activity_type,
                    "status": a.status,
                    "lon": a.lon,
                    "lat": a.lat,
                    "planned_date": a.planned_date,
                    "completed_date": a.completed_date,
                }
                for a in self.activities
            ],
            "legend": self.legend,
            "warnings_ar": self.warnings_ar,
        }


def png_to_data_uri(png_bytes: bytes) -> str:
    """يحوّل PNG bytes إلى data URI جاهز لـ <img src='...'/> أو L.imageOverlay."""
    if not png_bytes:
        return ""
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def build_bundle(
    *,
    field_id: str,
    boundary_polygon: list | None = None,
    zones_feature_collection: dict | None = None,
    raster_png_bytes: bytes | None = None,
    raster_bounds: dict | None = None,
    indicator: str | None = None,
    timeline: list | None = None,
    sample_points: list | None = None,
    sensors: list | None = None,
    activities: list | None = None,
    legend: list | None = None,
) -> FieldVisualBundle:
    """يبني FieldVisualBundle جاهز للإرجاع للواجهة.

    لا اختراع: أي بيانات ناقصة تُصاغ None/[] صراحة لا قيماً وهمية.
    الواجهة تتلقّى الحقيقة (متوفّر/غير متوفّر) وتقرّر العرض."""

    warnings: list[str] = []

    # حدود الحقل → Feature GeoJSON (يقبل polygon خام لتسهيل الاستدعاء)
    boundary_gj = None
    if boundary_polygon:
        # نقبل قائمة (lon, lat) أو dict {lon, lat}
        coords = []
        for pt in boundary_polygon:
            if isinstance(pt, dict):
                lon = pt.get("lon") or pt.get("longitude") or pt.get("lng")
                lat = pt.get("lat") or pt.get("latitude")
            elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                lon, lat = pt[0], pt[1]
            else:
                continue
            if lon is not None and lat is not None:
                coords.append([float(lon), float(lat)])
        if coords and coords[0] != coords[-1]:
            coords.append(coords[0])
        if len(coords) >= 4:
            boundary_gj = {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {"field_id": field_id},
            }
        else:
            warnings.append("حدود الحقل غير كافية (أقلّ من 3 نقاط) — تم تجاهلها")

    if not boundary_gj:
        warnings.append("لا حدود حقل — العرض سيعتمد على الـraster bounds فقط")

    # raster → data URI (إن وُجد)
    raster_uri = png_to_data_uri(raster_png_bytes) if raster_png_bytes else None

    if not zones_feature_collection and not raster_uri:
        warnings.append("لا طبقات بصرية — استخدم detect_zones_of_interest أو raster_export")

    return FieldVisualBundle(
        field_id=field_id,
        boundary_geojson=boundary_gj,
        zones_geojson=zones_feature_collection,
        raster_png_base64=raster_uri,
        raster_bounds=raster_bounds,
        indicator=indicator,
        timeline=timeline or [],
        sample_points=sample_points or [],
        sensors=sensors or [],
        activities=activities or [],
        legend=legend or [],
        warnings_ar=warnings,
    )
