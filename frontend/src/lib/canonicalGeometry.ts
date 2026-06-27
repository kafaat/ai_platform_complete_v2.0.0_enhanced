// العقد الموحَّد لهندسة الحقل الكنسيّة (CanonicalFieldGeometry) — جانب الواجهة.
//
// يُطابق 1:1 مصدرَ الحقيقة في Python: shared/domain/field_geometry.py،
// وكذلك نموذج Dart: mobile/sahool_app/lib/models/canonical_field_geometry.dart.
//
// الشكل نفسه الذي يُنتجه حارس الخلفيّة:
//   services/sahool-platform/api/gis_geometry_guard.py::guard_field_geometry
// (GeoJSON Polygon في EPSG:4326 + area_ha + bbox). نلتزم بمفاتيح bbox الحرفيّة
// min_lng/max_lng (لا lon) لمطابقة الخلفيّة صدقاً.
//
// أنواع فقط (types/contract) — لا تغيير في السلوك.

/** GeoJSON Polygon في EPSG:4326 (بلا عضو crs، حلقات مُغلقة). */
export interface GeoJsonPolygon {
  type: 'Polygon';
  coordinates: number[][][];
}

/** GeoJSON MultiPolygon في EPSG:4326 — حقل مكوّن من أجزاء منفصلة. */
export interface GeoJsonMultiPolygon {
  type: 'MultiPolygon';
  coordinates: number[][][][];
}

export type GeoJsonFieldGeometry = GeoJsonPolygon | GeoJsonMultiPolygon;

/** الحدود الصندوقيّة بالدرجات — مفاتيح مطابقة لحارس الـGIS. */
export interface BBox {
  min_lng: number;
  min_lat: number;
  max_lng: number;
  max_lat: number;
}

/** الشكل الكنسيّ الموحَّد لهندسة الحقل عبر المنصّات. */
export interface CanonicalFieldGeometry {
  geometry: GeoJsonFieldGeometry;
  area_ha: number;
  bbox: BBox;
  /** رقم مراجعة الحقل، أو null إن لم يُعرَف. */
  revision: number | null;
  /** مصدر الهندسة (مثل "gis-guard-v1" أو "mobile-draw"). */
  source: string;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isBBox(value: unknown): value is BBox {
  if (typeof value !== 'object' || value === null) return false;
  const b = value as Record<string, unknown>;
  return (
    isFiniteNumber(b.min_lng) &&
    isFiniteNumber(b.min_lat) &&
    isFiniteNumber(b.max_lng) &&
    isFiniteNumber(b.max_lat)
  );
}

function isGeoJsonFieldGeometry(value: unknown): value is GeoJsonFieldGeometry {
  if (typeof value !== 'object' || value === null) return false;
  const g = value as Record<string, unknown>;
  return (g.type === 'Polygon' || g.type === 'MultiPolygon') && Array.isArray(g.coordinates);
}

/** حارس نوع — يُرجِع true إن طابق الكائن العقد الكنسيّ بدقّة. */
export function isCanonicalFieldGeometry(value: unknown): value is CanonicalFieldGeometry {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    isGeoJsonFieldGeometry(v.geometry) &&
    isFiniteNumber(v.area_ha) &&
    isBBox(v.bbox) &&
    (v.revision === null || (typeof v.revision === 'number' && Number.isInteger(v.revision))) &&
    typeof v.source === 'string'
  );
}
