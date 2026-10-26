// SAHOOL — features/maps/geo/geo_json.dart
// المحوّل الوحيد بين GeoJSON و LatLng في التطبيق. تستورده حزم الرسم والاستيراد
// (W2-08/W2-09) ولا تنسخه. يملكه وكيل الخرائط الأساسيّة (W2-07).
//
// العقد (RFC 7946 + ما يحفظه الخادم):
//   • الإحداثيّات في GeoJSON بترتيب [lon, lat] (قد يتبعها ارتفاع يُتجاهَل).
//   • في الذاكرة: كلّ حلقة **مفتوحة** (بلا تكرار نقطة الإغلاق) — الشكل الذي
//     يرسمه flutter_map. [FieldGeometry.toGeoJson] يغلق كلّ حلقة عند الإخراج.
//   • الاتّجاه: الحلقة الخارجيّة عكس عقارب الساعة (CCW) والثقوب مع عقارب الساعة
//     (CW). الخادم لا يطبّع الاتّجاه (gis_geometry_guard.py يحفظ الحلقة كما أُرسلت)،
//     لذا يطبّعه العميل هنا قبل الإرسال.
//   • يقبل Polygon و MultiPolygon و Feature و FeatureCollection (تُجمَّع المضلّعات
//     كلّها في هندسة واحدة) ونصّ JSON. أيّ عنصر غير مضلّعيّ يُحصى في
//     [FieldGeometry.skippedParts] لا يُسقَط بصمت.
//   • الثقوب محفوظة. اليوم يحسب الخادم المساحة من الحلقات الخارجيّة وحدها
//     (gis_geometry_guard.py::_combined_area_bbox) — انظر geo_measure.dart.
//
// الاستعمال:
//   final g = FieldGeometry.tryParse(field['geometry']);      // null إن غابت/تشوّهت
//   PolygonLayer(polygons: [for (final p in g!.polygons)
//       Polygon(points: p.outer, holePointsList: p.holes)]);
//   api.save(geometry: g.toGeoJson());                         // حلقات مغلقة، CCW
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter_map/flutter_map.dart' show LatLngBounds;
import 'package:latlong2/latlong.dart';

/// مضلّع واحد: حلقة خارجيّة + ثقوب. كلّ الحلقات مفتوحة.
@immutable
class GeoPolygon {
  GeoPolygon(List<LatLng> outer, [List<List<LatLng>> holes = const []])
    : outer = List.unmodifiable(outer),
      holes = List.unmodifiable(holes.map(List<LatLng>.unmodifiable));

  final List<LatLng> outer;
  final List<List<LatLng>> holes;

  /// الحلقات بترتيب GeoJSON: الخارجيّة أوّلاً.
  List<List<LatLng>> get rings => [outer, ...holes];

  int get vertexCount => rings.fold(0, (n, r) => n + r.length);

  /// المضلّع بلا ثقوب.
  GeoPolygon withoutHoles() => GeoPolygon(outer);

  /// يحتوي [p]؟ (داخل الخارجيّة وخارج كلّ ثقب؛ قاعدة زوجيّ-فرديّ على lon/lat).
  bool contains(LatLng p) {
    if (!ringContains(outer, p)) return false;
    for (final h in holes) {
      if (ringContains(h, p)) return false;
    }
    return true;
  }

  @override
  bool operator ==(Object other) =>
      other is GeoPolygon &&
      listEquals(outer, other.outer) &&
      other.holes.length == holes.length &&
      Iterable<int>.generate(
        holes.length,
      ).every((i) => listEquals(holes[i], other.holes[i]));

  @override
  int get hashCode => Object.hash(
    Object.hashAll(outer),
    Object.hashAll(holes.map(Object.hashAll)),
  );
}

/// هندسة حقل: مضلّع واحد أو أكثر (MultiPolygon)، بثقوبها.
@immutable
class FieldGeometry {
  FieldGeometry(List<GeoPolygon> polygons, {this.skippedParts = 0})
    : polygons = List.unmodifiable(polygons);

  /// مضلّع واحد من حلقة خارجيّة (مفتوحة أو مغلقة) وثقوب اختياريّة.
  factory FieldGeometry.polygon(
    List<LatLng> outer, [
    List<List<LatLng>> holes = const [],
  ]) => FieldGeometry([
    GeoPolygon(openRing(outer), holes.map(openRing).toList()),
  ]);

  final List<GeoPolygon> polygons;

  /// عناصر قُرئت لكنّها ليست مضلّعات (نقاط/خطوط في FeatureCollection) أو أجزاء
  /// متحلّلة (< 3 رؤوس متمايزة) أُسقطت. يعرضها المستدعي («أُهمل جزءان»).
  final int skippedParts;

  bool get isEmpty => polygons.isEmpty;
  bool get isMulti => polygons.length > 1;
  bool get hasHoles => polygons.any((p) => p.holes.isNotEmpty);
  int get vertexCount => polygons.fold(0, (n, p) => n + p.vertexCount);

  /// كلّ الرؤوس (للتأطير).
  Iterable<LatLng> get allPoints sync* {
    for (final p in polygons) {
      for (final r in p.rings) {
        yield* r;
      }
    }
  }

  /// الإطار المحيط؛ null لهندسة فارغة.
  LatLngBounds? get bounds {
    final pts = allPoints.toList();
    return pts.isEmpty ? null : LatLngBounds.fromPoints(pts);
  }

  /// هل تقع [p] داخل أيّ جزء (مع احترام الثقوب)؟ لاختبار النقر.
  bool contains(LatLng p) => polygons.any((poly) => poly.contains(p));

  // ── القراءة ──────────────────────────────────────────────────────────

  /// يقرأ GeoJSON (Map أو نصّ JSON). يرمي [FormatException] بسبب عربيّ صريح
  /// إن لم يكن الشكل مضلّعيّاً أو كانت الإحداثيّات تالفة.
  static FieldGeometry fromGeoJson(Object? json) {
    final reader = _Reader();
    reader.read(_decode(json));
    if (reader.polygons.isEmpty) {
      throw FormatException(
        reader.skipped > 0
            ? 'لا مضلّع صالح في البيانات (أُهمل ${reader.skipped} عنصر غير مضلّعيّ)'
            : 'لا مضلّع في البيانات',
      );
    }
    return FieldGeometry(reader.polygons, skippedParts: reader.skipped);
  }

  /// مثل [fromGeoJson] لكن يردّ null بدل الرمي (عرض قائمة الحقول: حقل بلا هندسة
  /// يبقى في القائمة ولا يُرسَم).
  static FieldGeometry? tryParse(Object? json) {
    if (json == null) return null;
    try {
      return fromGeoJson(json);
    } on FormatException {
      return null;
    }
  }

  // ── الكتابة ──────────────────────────────────────────────────────────

  /// GeoJSON geometry: `Polygon` لجزء واحد، `MultiPolygon` لأكثر (أو دائماً مع
  /// [forceMulti]). الحلقات مغلقة، [lon, lat]، الخارجيّة CCW والثقوب CW.
  /// [decimals] يقرّب الإحداثيّات (الخادم يقرّب إلى 7 منازل؛ null ⇒ بلا تقريب).
  Map<String, dynamic> toGeoJson({bool forceMulti = false, int? decimals}) {
    if (isEmpty) throw StateError('هندسة فارغة لا تُكتب GeoJSON');
    List<List<double>> ring(List<LatLng> r, {required bool ccw}) {
      final oriented = orientRing(r, counterClockwise: ccw);
      final closed = closeRing(oriented);
      return [
        for (final p in closed)
          [_round(p.longitude, decimals), _round(p.latitude, decimals)],
      ];
    }

    List<List<List<double>>> poly(GeoPolygon p) => [
      ring(p.outer, ccw: true),
      for (final h in p.holes) ring(h, ccw: false),
    ];

    if (polygons.length == 1 && !forceMulti) {
      return {'type': 'Polygon', 'coordinates': poly(polygons.first)};
    }
    return {
      'type': 'MultiPolygon',
      'coordinates': [for (final p in polygons) poly(p)],
    };
  }

  /// Feature يلفّ [toGeoJson].
  Map<String, dynamic> toFeature({
    Map<String, dynamic> properties = const {},
  }) => {'type': 'Feature', 'properties': properties, 'geometry': toGeoJson()};

  @override
  bool operator ==(Object other) =>
      other is FieldGeometry && listEquals(polygons, other.polygons);

  @override
  int get hashCode => Object.hashAll(polygons);
}

// ── مساعدات الحلقات (عامّة: يستعملها الرسم والاستيراد) ─────────────────

/// حلقة مغلقة (آخر نقطة = الأولى). لا تُكرِّر إن كانت مغلقة أصلاً.
List<LatLng> closeRing(List<LatLng> ring) {
  if (ring.isEmpty) return const [];
  if (_same(ring.first, ring.last) && ring.length > 1) return List.of(ring);
  return [...ring, ring.first];
}

/// حلقة مفتوحة: تُزيل نقطة الإغلاق المكرّرة والرؤوس المتتالية المكرّرة.
List<LatLng> openRing(List<LatLng> ring) {
  final out = <LatLng>[];
  for (final p in ring) {
    if (out.isEmpty || !_same(out.last, p)) out.add(p);
  }
  while (out.length > 1 && _same(out.first, out.last)) {
    out.removeLast();
  }
  return out;
}

/// المساحة الموقَّعة المستوية للحلقة على (lon, lat) بالدرجات² (shoelace).
/// موجبة ⇒ عكس عقارب الساعة (CCW) حين يكون الشمال للأعلى والشرق لليمين.
/// للاتّجاه فقط — المساحة الحقيقيّة في geo_measure.dart.
double ringSignedArea(List<LatLng> ring) {
  final r = openRing(ring);
  if (r.length < 3) return 0;
  var sum = 0.0;
  for (var i = 0; i < r.length; i++) {
    final a = r[i];
    final b = r[(i + 1) % r.length];
    sum += a.longitude * b.latitude - b.longitude * a.latitude;
  }
  return sum / 2;
}

bool isCounterClockwise(List<LatLng> ring) => ringSignedArea(ring) > 0;

/// يعيد الحلقة (مفتوحة) بالاتّجاه المطلوب. عند العكس يبقى الرأس الأوّل أوّلاً
/// (أوّل نقطة رسمها المستخدم تبقى نقطة البداية/الإغلاق).
List<LatLng> orientRing(List<LatLng> ring, {required bool counterClockwise}) {
  final r = openRing(ring);
  final area = ringSignedArea(r);
  if (area == 0 || (area > 0) == counterClockwise) return r;
  return [r.first, ...r.sublist(1).reversed];
}

/// نقطة داخل حلقة؟ (زوجيّ-فرديّ، الحلقة مفتوحة أو مغلقة).
bool ringContains(List<LatLng> ring, LatLng p) {
  final r = openRing(ring);
  if (r.length < 3) return false;
  var inside = false;
  final x = p.longitude, y = p.latitude;
  for (var i = 0, j = r.length - 1; i < r.length; j = i++) {
    final xi = r[i].longitude, yi = r[i].latitude;
    final xj = r[j].longitude, yj = r[j].latitude;
    final crosses =
        (yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

/// موضع GeoJSON [lon, lat, (alt)] ⇒ LatLng. يرمي FormatException للموضع التالف
/// أو الخارج عن نطاق WGS84.
LatLng latLngFromPosition(Object? position) {
  if (position is! List || position.length < 2) {
    throw const FormatException('موضع GeoJSON يجب أن يكون [lon, lat]');
  }
  final lon = _toDouble(position[0]);
  final lat = _toDouble(position[1]);
  if (lon == null || lat == null || !lon.isFinite || !lat.isFinite) {
    throw const FormatException('إحداثيّة غير رقميّة في GeoJSON');
  }
  if (lat.abs() > 90 || lon.abs() > 180) {
    throw FormatException('إحداثيّة خارج نطاق WGS84: [$lon, $lat]');
  }
  return LatLng(lat, lon);
}

/// LatLng ⇒ موضع GeoJSON [lon, lat].
List<double> positionFromLatLng(LatLng p) => [p.longitude, p.latitude];

/// قائمة مواضع (LineString/حلقة) ⇒ LatLng.
List<LatLng> latLngsFromPositions(Object? positions) {
  if (positions is! List) {
    throw const FormatException('قائمة مواضع GeoJSON غير صالحة');
  }
  return [for (final p in positions) latLngFromPosition(p)];
}

// ── داخليّ ─────────────────────────────────────────────────────────────

Object? _decode(Object? json) {
  if (json is String) {
    try {
      return jsonDecode(json);
    } on FormatException {
      throw const FormatException('نصّ GeoJSON ليس JSON صالحاً');
    }
  }
  return json;
}

class _Reader {
  final polygons = <GeoPolygon>[];
  var skipped = 0;

  void read(Object? node) {
    if (node is! Map) throw const FormatException('GeoJSON يجب أن يكون كائناً');
    switch (node['type']) {
      case 'FeatureCollection':
        final features = node['features'];
        if (features is! List) {
          throw const FormatException('FeatureCollection بلا features');
        }
        for (final f in features) {
          read(f);
        }
      case 'Feature':
        final g = node['geometry'];
        if (g == null) {
          skipped++;
        } else {
          read(g);
        }
      case 'GeometryCollection':
        final gs = node['geometries'];
        if (gs is! List) {
          throw const FormatException('GeometryCollection بلا geometries');
        }
        for (final g in gs) {
          read(g);
        }
      case 'Polygon':
        _addPolygon(node['coordinates']);
      case 'MultiPolygon':
        final parts = node['coordinates'];
        if (parts is! List) {
          throw const FormatException('MultiPolygon بلا coordinates');
        }
        for (final part in parts) {
          _addPolygon(part);
        }
      case 'Point' || 'MultiPoint' || 'LineString' || 'MultiLineString':
        skipped++;
      default:
        throw FormatException('نوع GeoJSON غير مدعوم: ${node['type']}');
    }
  }

  void _addPolygon(Object? rings) {
    if (rings is! List || rings.isEmpty) {
      throw const FormatException('Polygon بلا حلقات');
    }
    final parsed = [for (final r in rings) openRing(latLngsFromPositions(r))];
    if (parsed.first.length < 3) {
      skipped++; // حلقة خارجيّة متحلّلة ⇒ لا جزء
      return;
    }
    final holes = <List<LatLng>>[];
    for (final h in parsed.skip(1)) {
      if (h.length >= 3) {
        holes.add(h);
      } else {
        skipped++;
      }
    }
    polygons.add(GeoPolygon(parsed.first, holes));
  }
}

bool _same(LatLng a, LatLng b) =>
    a.latitude == b.latitude && a.longitude == b.longitude;

double? _toDouble(Object? v) => v is num ? v.toDouble() : null;

double _round(double v, int? decimals) {
  if (decimals == null) return v;
  final f = math.pow(10, decimals).toDouble();
  return (v * f).round() / f;
}
