// SAHOOL — features/maps/draw/geo_measure.dart
// قياس حدود الحقل بصيغة الخادم نفسها، لا بتقريبٍ محلّيّ.
//
// كان المعالج يحسب المساحة بإسقاط متساوي المستطيلات ونصف قطر 6378137 م، فيقرأ
// أعلى من الخادم بـ+0.224٪؛ فيرى المزارع رقمين مختلفين للحقل نفسه. هنا منقولٌ
// حرفيّ لمسار الخادم:
//   • التطبيع: `gis_geometry_guard._normalize_ring` (تقريب 7 منازل، حذف الرؤوس
//     المتتالية المكرّرة، إغلاق الحلقة).
//   • المساحة: `geospatial_integrity.polygon_area_m2` (الزيادة الكرويّة،
//     R = 6371008.8) على الحلقة الخارجيّة وحدها.
//   • التقريب: `guard_field_geometry` يقرّب إلى 4 منازل، ثمّ `_persist_field`
//     يخزّن `round(area_ha, 2)`.
//   • المحور: `pivot_geometry.generate_pivot_polygon` (96 رأساً جيوديسيّاً،
//     R = 6378137، الزاوية 0 = الشمال).
//
// توحيد مع maps/geo/geo_measure.dart: haversineM مشترك من هناك (الصيغة نفسها
// حرفيّاً). ما بقي هنا يختلف دلاليّاً، وسبب كلّ اختلاف مكتوب عند الدالّة.
import 'dart:math' as math;

import 'package:latlong2/latlong.dart';

import '../geo/geo_measure.dart' show haversineM, kEarthRadiusM;

export '../geo/geo_measure.dart' show haversineM;

/// نصف قطر الأرض الوسطيّ الذي يستعمله الخادم للمساحة والمسافة (WGS84 mean).
const double kServerEarthRadiusM = kEarthRadiusM;

/// نصف القطر الاستوائيّ الذي يولّد به الخادم مضلّع المحور (pivot).
const double kPivotEarthRadiusM = 6378137.0;

/// عدد رؤوس مضلّع المحور القانونيّ (يطابق الويب والخادم).
const int kPivotVertices = 96;

double _rad(double d) => d * math.pi / 180.0;
double _deg(double r) => r * 180.0 / math.pi;

/// تقريب بمنطق Python `round(x, n)`: يقرّب القيمة الثنائيّة **الدقيقة** إلى
/// الأقرب، والتعادل التامّ إلى الزوجيّ. `toStringAsFixed` في Dart دقيق أيضاً لكنّه
/// يقرّب التعادل التامّ إلى الأعلى (0.125 ⇒ 0.13 بينما Python ⇒ 0.12).
double pyRound(double x, int n) {
  if (!x.isFinite || x.abs() >= 1e20) return x;
  final up = double.parse(x.toStringAsFixed(n));
  final exact = x.abs().toStringAsFixed(20);
  final dot = exact.indexOf('.');
  final frac = exact.substring(dot + 1);
  final isTie =
      frac[n] == '5' && frac.substring(n + 1).replaceAll('0', '').isEmpty;
  if (!isTie) return up;
  final truncated = exact.substring(0, n == 0 ? dot : dot + 1 + n);
  if (int.parse(truncated[truncated.length - 1]).isOdd) return up;
  final t = double.parse(truncated);
  return x.isNegative ? -t : t;
}

/// يختلف عن geo/serverNormalizedRing: تقريب Python (التعادل إلى الزوجيّ) وحلقة [lon,lat] مغلقة.
/// يطبّع الحلقة كما يطبّعها الخادم: [lon,lat] مقرّبة إلى 7 منازل، بلا تكرار
/// متتالٍ، ومغلقة (الأوّل = الأخير). المدخل حلقة مفتوحة أو مغلقة من [LatLng].
List<List<double>> serverNormalizedRing(List<LatLng> ring) {
  final out = <List<double>>[];
  List<double>? last;
  for (final p in ring) {
    final lon = pyRound(p.longitude, 7);
    final lat = pyRound(p.latitude, 7);
    if (last != null && last[0] == lon && last[1] == lat) continue;
    final cur = [lon, lat];
    out.add(cur);
    last = cur;
  }
  if (out.isNotEmpty &&
      (out.first[0] != out.last[0] || out.first[1] != out.last[1])) {
    out.add([out.first[0], out.first[1]]);
  }
  return out;
}

/// صيغة geo/ringAreaM2 نفسها، لكن على أزواج [lon,lat] خامّ قد تقع خارج مدى LatLng.
/// `polygon_area_m2` من الخادم حرفيّاً. [coords] أزواج [lon,lat].
double serverPolygonAreaM2(List<List<double>> coords) {
  if (coords.length < 3) return 0;
  var c = coords;
  if (c.first[0] != c.last[0] || c.first[1] != c.last[1]) {
    c = [...c, c.first];
  }
  var total = 0.0;
  for (var i = 0; i < c.length - 1; i++) {
    final lng1 = c[i][0], lat1 = c[i][1];
    final lng2 = c[i + 1][0], lat2 = c[i + 1][1];
    total +=
        _rad(lng2 - lng1) * (2 + math.sin(_rad(lat1)) + math.sin(_rad(lat2)));
  }
  return (total * kServerEarthRadiusM * kServerEarthRadiusM / 2).abs();
}

/// المساحة بالهكتار كما يحسبها حارس الخادم (قبل تقريب الحفظ، 4 منازل).
/// null إن لم تكن الحلقة مضلّعاً (أقلّ من 4 رؤوس بعد التطبيع مع الإغلاق).
double? serverGuardAreaHa(List<LatLng> ring) {
  final n = serverNormalizedRing(ring);
  if (n.length < 4) return null;
  return pyRound(serverPolygonAreaM2(n) / 10000.0, 4);
}

/// المساحة التي سيخزّنها الخادم في `fields.area_ha` (منزلتان).
double? serverStoredAreaHa(List<LatLng> ring) {
  final a = serverGuardAreaHa(ring);
  return a == null ? null : pyRound(a, 2);
}

/// يختلف عن geo/ringPerimeterM: رأسان ⇒ طول الخطّ لا ذهاباً وإياباً.
/// محيط الحلقة بالأمتار (مغلقة عند ≥3 رؤوس، وإلّا طول الخطّ).
double perimeterM(List<LatLng> ring) {
  if (ring.length < 2) return 0;
  var total = 0.0;
  for (var i = 0; i < ring.length - 1; i++) {
    total += haversineM(ring[i], ring[i + 1]);
  }
  if (ring.length >= 3 && ring.first != ring.last) {
    total += haversineM(ring.last, ring.first);
  }
  return total;
}

/// يختلف عن geo/destinationPoint: نصف القطر الاستوائيّ للمحور والزاوية بالراديان.
/// نقطة الوصول الجيوديسيّة (`_destination_point` في الخادم). [bearingRad]: 0 = الشمال.
LatLng destinationPoint(LatLng from, double distanceM, double bearingRad) {
  final lat1 = _rad(from.latitude);
  final lon1 = _rad(from.longitude);
  final ang = distanceM / kPivotEarthRadiusM;
  final lat2 = math.asin(
    math.sin(lat1) * math.cos(ang) +
        math.cos(lat1) * math.sin(ang) * math.cos(bearingRad),
  );
  final lon2 =
      lon1 +
      math.atan2(
        math.sin(bearingRad) * math.sin(ang) * math.cos(lat1),
        math.cos(ang) - math.sin(lat1) * math.sin(lat2),
      );
  return LatLng(_deg(lat2), _deg(lon2));
}

/// مضلّع المحور كما يولّده الخادم (دائرة كاملة): 96 رأساً مقرّبة إلى 7 منازل،
/// والحلقة المُعادة **مفتوحة** (بلا تكرار الأوّل في الآخر).
List<LatLng> pivotPolygon(
  LatLng center,
  double radiusM, {
  int vertices = kPivotVertices,
}) {
  if (radiusM <= 0) return const [];
  final steps = math.max(12, vertices);
  final out = <LatLng>[];
  for (var i = 0; i < steps; i++) {
    final p = destinationPoint(center, radiusM, _rad(360.0 * i / steps));
    out.add(LatLng(pyRound(p.latitude, 7), pyRound(p.longitude, 7)));
  }
  return out;
}

/// أمتار لكلّ بكسل في إسقاط ويب ميركاتور عند [zoom] و[latitude].
/// يحوّل تسامح الالتقاط من بكسلات الشاشة إلى أمتار.
double metersPerPixel(double latitude, double zoom) =>
    156543.03392 * math.cos(_rad(latitude)) / math.pow(2, zoom);
