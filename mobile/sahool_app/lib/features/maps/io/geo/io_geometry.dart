// SAHOOL — features/maps/io/geo/io_geometry.dart
// نموذج هندسة صغير خاصّ بحزمة الاستيراد/التصدير/مشي GPS: مضلّع = حلقات LatLng
// (الأولى خارجيّة، والبقيّة ثقوب)، كلّ حلقة **مفتوحة** (بلا تكرار نقطة الإغلاق).
//
// للدمج لاحقاً: حزمة الخرائط الأساسيّة (W2-07) تملك geo/geojson_codec.dart
// (FieldGeometry). لم يكن في هذه الشجرة حين كُتب هذا الملفّ، فهذا محوّل أدنى
// خاصّ بمجلّد io/ يُستبدَل به عند الدمج دون تغيير سلوك.
import 'package:latlong2/latlong.dart';

/// مضلّع واحد: [rings].first خارجيّة، والباقي ثقوب. الحلقات مفتوحة.
class IoPolygon {
  IoPolygon(List<List<LatLng>> rings)
    : rings = List.unmodifiable(rings.map(List<LatLng>.unmodifiable));

  final List<List<LatLng>> rings;

  List<LatLng> get outer => rings.first;
  List<List<LatLng>> get holes =>
      rings.length > 1 ? rings.sublist(1) : const [];
  int get vertexCount => rings.fold(0, (n, r) => n + r.length);

  /// المضلّع بلا ثقوب (ما يحفظه مسار الاستيراد في الخادم اليوم).
  IoPolygon outerOnly() => IoPolygon([outer]);
}

/// حدود مستطيلة (لملاءمة الكاميرا).
class IoBounds {
  const IoBounds(this.south, this.west, this.north, this.east);
  final double south;
  final double west;
  final double north;
  final double east;

  static IoBounds? of(Iterable<LatLng> points) {
    double? s, w, n, e;
    for (final p in points) {
      s = s == null || p.latitude < s ? p.latitude : s;
      n = n == null || p.latitude > n ? p.latitude : n;
      w = w == null || p.longitude < w ? p.longitude : w;
      e = e == null || p.longitude > e ? p.longitude : e;
    }
    if (s == null) return null;
    return IoBounds(s, w!, n!, e!);
  }
}

/// يزيل نقطة الإغلاق المكرّرة والتكرارات المتتالية. لا يمسّ الترتيب.
List<LatLng> openRing(Iterable<LatLng> points) {
  final out = <LatLng>[];
  for (final p in points) {
    if (out.isNotEmpty && _same(out.last, p)) continue;
    out.add(p);
  }
  while (out.length > 1 && _same(out.first, out.last)) {
    out.removeLast();
  }
  return out;
}

bool _same(LatLng a, LatLng b) =>
    a.latitude == b.latitude && a.longitude == b.longitude;

/// مساحة مستوية موقَّعة على (lon,lat) — للاتّجاه فقط (موجب = عكس عقارب الساعة).
double signedPlanarArea(List<LatLng> ring) {
  var sum = 0.0;
  for (var i = 0; i < ring.length; i++) {
    final a = ring[i];
    final b = ring[(i + 1) % ring.length];
    sum += a.longitude * b.latitude - b.longitude * a.latitude;
  }
  return sum / 2;
}

/// حلقة GeoJSON مُغلقة `[[lon,lat],...]` باتّجاه مطلوب (RFC 7946: الخارجيّة
/// عكس عقارب الساعة، والثقوب معها).
List<List<double>> ringToGeoJson(List<LatLng> ring, {required bool ccw}) {
  final open = openRing(ring);
  final isCcw = signedPlanarArea(open) > 0;
  final ordered = isCcw == ccw ? open : open.reversed.toList();
  return [
    for (final p in ordered) [p.longitude, p.latitude],
    if (ordered.isNotEmpty) [ordered.first.longitude, ordered.first.latitude],
  ];
}

/// إحداثيّات Polygon بصيغة GeoJSON.
List<List<List<double>>> polygonCoordinates(IoPolygon polygon) => [
  ringToGeoJson(polygon.outer, ccw: true),
  for (final h in polygon.holes) ringToGeoJson(h, ccw: false),
];

/// GeoJSON Polygon (`{type, coordinates}`).
Map<String, dynamic> polygonToGeoJson(IoPolygon polygon) => {
  'type': 'Polygon',
  'coordinates': polygonCoordinates(polygon),
};

/// يقرأ هندسة حقل من الخادم (Polygon أو MultiPolygon) إلى مضلّعات. شكل غير
/// معروف ⇒ قائمة فارغة (لا مضلّع مختلَق).
List<IoPolygon> polygonsFromGeoJson(Object? geometry) {
  if (geometry is! Map) return const [];
  final type = geometry['type'];
  final coords = geometry['coordinates'];
  if (coords is! List) return const [];
  if (type == 'Polygon') {
    final p = _polygonFromCoords(coords);
    return p == null ? const [] : [p];
  }
  if (type == 'MultiPolygon') {
    return [
      for (final part in coords)
        if (part is List) ?_polygonFromCoords(part),
    ];
  }
  return const [];
}

IoPolygon? _polygonFromCoords(List<dynamic> rings) {
  final out = <List<LatLng>>[];
  for (final r in rings) {
    if (r is! List) return null;
    final ring = <LatLng>[];
    for (final p in r) {
      if (p is! List || p.length < 2 || p[0] is! num || p[1] is! num) {
        return null;
      }
      final lon = (p[0] as num).toDouble();
      final lat = (p[1] as num).toDouble();
      if (!lon.isFinite || !lat.isFinite || lat.abs() > 90 || lon.abs() > 180) {
        return null;
      }
      ring.add(LatLng(lat, lon));
    }
    final open = openRing(ring);
    if (open.length < 3) {
      if (out.isEmpty) return null; // حلقة خارجيّة غير صالحة
      continue; // ثقب متدهور يُهمَل
    }
    out.add(open);
  }
  return out.isEmpty ? null : IoPolygon(out);
}
