"""العقد الموحَّد لهندسة الحقل الكنسيّة (CanonicalFieldGeometry).

مصدر الحقيقة الوحيد للشكل الكنسيّ المُتبادَل بين الواجهة (web) والتطبيق (mobile)
والخلفيّة (backend) والتحليلات (analytics). يجب أن تُطابق التعاريف في:

    * frontend/src/lib/canonicalGeometry.ts   (واجهة TypeScript)
    * mobile/sahool_app/lib/models/canonical_field_geometry.dart (نموذج Dart)

ملاحظة عقديّة مهمّة:
``services/sahool-platform/api/gis_geometry_guard.py::guard_field_geometry`` يُنتج
هذا الشكل الكنسيّ نفسه (GeoJSON Polygon في EPSG:4326 + ``area_ha`` + ``bbox``).
يستخدم الحارس مفاتيح ``min_lng``/``max_lng`` للحدود الصندوقيّة (وليس ``lon``)؛
ولذلك نلتزم هنا بالأسماء نفسها حرفيّاً حتّى يبقى العقد صادقاً 1:1.

هذا الملف يعرّف الشكل فقط (types/contract) دون أيّ تغيير في السلوك.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


class BBox(TypedDict):
    """الحدود الصندوقيّة بالدرجات (EPSG:4326). تُطابق مفاتيح حارس الـGIS."""

    min_lng: float
    min_lat: float
    max_lng: float
    max_lat: float


class CanonicalFieldGeometryDict(TypedDict):
    """تمثيل القاموس (JSON) للعقد الكنسيّ — يُطابق ``to_dict`` أدناه."""

    geometry: dict[str, Any]  # GeoJSON Polygon في EPSG:4326
    area_ha: float
    bbox: BBox
    revision: int | None
    source: str


# مفاتيح الحدود الصندوقيّة المطلوبة — مصدر واحد للتحقّق.
_BBOX_KEYS: tuple[str, ...] = ("min_lng", "min_lat", "max_lng", "max_lat")


@dataclass(frozen=True)
class CanonicalFieldGeometry:
    """الشكل الكنسيّ الموحَّد لهندسة الحقل.

    الحقول:
        geometry: GeoJSON Polygon في EPSG:4326 (بلا عضو ``crs``، حلقات مُغلقة).
        area_ha:  المساحة بالهكتار (محسوبة من الخلفيّة).
        bbox:     الحدود الصندوقيّة ``{min_lng, min_lat, max_lng, max_lat}``.
        revision: رقم مراجعة الحقل (اختياريّ) — ``None`` إن لم يُعرَف.
        source:   مصدر الهندسة (مثل ``"gis-guard-v1"`` أو ``"mobile-draw"``).
    """

    geometry: dict[str, Any]
    area_ha: float
    bbox: BBox
    revision: int | None = None
    source: str = "unknown"

    def __post_init__(self) -> None:
        # تحقّق خفيف عند الإنشاء حتّى لا يتسرّب شكل غير مطابق للعقد.
        validate_canonical_field_geometry(self.to_dict())

    def to_dict(self) -> CanonicalFieldGeometryDict:
        """يُرجِع تمثيل JSON المطابق للعقد عبر المنصّات."""
        return {
            "geometry": self.geometry,
            "area_ha": self.area_ha,
            "bbox": self.bbox,
            "revision": self.revision,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanonicalFieldGeometry:
        """يبني الكائن من قاموس بعد التحقّق من مطابقته للعقد."""
        validate_canonical_field_geometry(data)
        return cls(
            geometry=data["geometry"],
            area_ha=float(data["area_ha"]),
            bbox=data["bbox"],
            revision=data.get("revision"),
            source=data.get("source", "unknown"),
        )


def is_canonical_field_geometry(data: Any) -> bool:
    """حارس نوع لطيف (لا يرمي) — يُرجِع True إن طابق الشكل العقد."""
    try:
        validate_canonical_field_geometry(data)
        return True
    except (ValueError, TypeError):
        return False


def validate_canonical_field_geometry(data: Any) -> None:
    """يتحقّق صرامةً من الشكل الكنسيّ؛ يرمي ``ValueError`` عند المخالفة."""
    if not isinstance(data, dict):
        raise ValueError("CanonicalFieldGeometry must be a mapping")

    geometry = data.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise ValueError("geometry must be a GeoJSON Polygon")
    if not isinstance(geometry.get("coordinates"), list):
        raise ValueError("geometry.coordinates must be a list")

    area_ha = data.get("area_ha")
    if not isinstance(area_ha, (int, float)) or isinstance(area_ha, bool):
        raise ValueError("area_ha must be a number")

    bbox = data.get("bbox")
    if not isinstance(bbox, dict):
        raise ValueError("bbox must be a mapping")
    for key in _BBOX_KEYS:
        value = bbox.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"bbox.{key} must be a number")

    revision = data.get("revision")
    if revision is not None and (not isinstance(revision, int) or isinstance(revision, bool)):
        raise ValueError("revision must be an int or None")

    source = data.get("source")
    if not isinstance(source, str):
        raise ValueError("source must be a string")


__all__ = [
    "BBox",
    "CanonicalFieldGeometry",
    "CanonicalFieldGeometryDict",
    "is_canonical_field_geometry",
    "validate_canonical_field_geometry",
]
