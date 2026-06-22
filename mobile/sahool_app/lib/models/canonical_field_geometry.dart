// العقد الموحَّد لهندسة الحقل الكنسيّة (CanonicalFieldGeometry) — جانب التطبيق.
//
// يُطابق 1:1 مصدرَ الحقيقة في Python: shared/domain/field_geometry.py،
// وواجهة TypeScript: frontend/src/lib/canonicalGeometry.ts.
//
// الشكل نفسه الذي يُنتجه حارس الخلفيّة:
//   services/sahool-platform/api/gis_geometry_guard.py::guard_field_geometry
// (GeoJSON Polygon في EPSG:4326 + area_ha + bbox). نلتزم بمفاتيح bbox الحرفيّة
// min_lng/max_lng (لا lon) لمطابقة الخلفيّة صدقاً.
//
// نموذج فقط (fromJson/toJson) — لا تغيير في السلوك.

/// الحدود الصندوقيّة بالدرجات (EPSG:4326) — مفاتيح مطابقة لحارس الـGIS.
class BBox {
  const BBox({
    required this.minLng,
    required this.minLat,
    required this.maxLng,
    required this.maxLat,
  });

  final double minLng;
  final double minLat;
  final double maxLng;
  final double maxLat;

  factory BBox.fromJson(Map<String, dynamic> json) => BBox(
        minLng: (json['min_lng'] as num).toDouble(),
        minLat: (json['min_lat'] as num).toDouble(),
        maxLng: (json['max_lng'] as num).toDouble(),
        maxLat: (json['max_lat'] as num).toDouble(),
      );

  Map<String, dynamic> toJson() => {
        'min_lng': minLng,
        'min_lat': minLat,
        'max_lng': maxLng,
        'max_lat': maxLat,
      };
}

/// الشكل الكنسيّ الموحَّد لهندسة الحقل عبر المنصّات.
class CanonicalFieldGeometry {
  const CanonicalFieldGeometry({
    required this.geometry,
    required this.areaHa,
    required this.bbox,
    this.revision,
    this.source = 'unknown',
  });

  /// GeoJSON Polygon في EPSG:4326 (بلا عضو crs، حلقات مُغلقة).
  final Map<String, dynamic> geometry;

  /// المساحة بالهكتار (محسوبة من الخلفيّة).
  final double areaHa;

  /// الحدود الصندوقيّة {min_lng, min_lat, max_lng, max_lat}.
  final BBox bbox;

  /// رقم مراجعة الحقل، أو null إن لم يُعرَف.
  final int? revision;

  /// مصدر الهندسة (مثل "gis-guard-v1" أو "mobile-draw").
  final String source;

  factory CanonicalFieldGeometry.fromJson(Map<String, dynamic> json) =>
      CanonicalFieldGeometry(
        geometry: Map<String, dynamic>.from(json['geometry'] as Map),
        areaHa: (json['area_ha'] as num).toDouble(),
        bbox: BBox.fromJson(Map<String, dynamic>.from(json['bbox'] as Map)),
        revision: json['revision'] as int?,
        source: (json['source'] as String?) ?? 'unknown',
      );

  Map<String, dynamic> toJson() => {
        'geometry': geometry,
        'area_ha': areaHa,
        'bbox': bbox.toJson(),
        'revision': revision,
        'source': source,
      };
}
