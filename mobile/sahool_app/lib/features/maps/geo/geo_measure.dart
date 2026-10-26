// SAHOOL — features/maps/geo/geo_measure.dart
// القياس على الكرة بالطريقة نفسها التي يحسب بها الخادم مساحة الحقل، كي يرى المزارع
// الرقم نفسه في المعاينة وبعد الحفظ.
//
// المرجع (منقول حرفيّاً، لا تقريباً):
//   services/sahool-platform/api/geospatial_integrity.py
//     • haversine_m      — R = 6371008.8 م (نصف القطر المتوسّط لـWGS84)
//     • polygon_area_m2  — Σ Δλ·(2 + sin φ1 + sin φ2) · R² / 2 على الحلقة المغلقة
//   services/sahool-platform/api/gis_geometry_guard.py
//     • _normalize_ring  — تقريب الإحداثيّات إلى 7 منازل وإزالة المكرّر قبل الحساب
//     • _combined_area_bbox — مساحة الحقل = مجموع مساحات **الحلقات الخارجيّة**
//       لكلّ الأجزاء. الثقوب لا تُطرَح في الخادم اليوم.
//
// الكود القديم (معالج الإنشاء) استعمل إسقاطاً مستطيليّاً بـR = 6378137 فقرأ
// أعلى من الخادم بنحو 0.224٪. لذلك:
//   • [serverAreaHa] = ما سيخزّنه الخادم (يُعرَض كمساحة الحقل).
//   • [netAreaHa]    = المساحة الصافية بعد طرح الثقوب (للعرض المعلوماتيّ فقط؛
//     تختلف عن الخادم حين توجد ثقوب، وعلى الواجهة أن تقول ذلك).
import 'dart:math' as math;

import 'package:latlong2/latlong.dart';

import 'geo_json.dart';

/// نصف القطر المتوسّط للأرض (WGS84) بالمتر — قيمة الخادم.
const double kEarthRadiusM = 6371008.8;

/// منازل التقريب في حارس الخادم.
const int kServerCoordinatePrecision = 7;

double _rad(double deg) => deg * math.pi / 180.0;
double _deg(double rad) => rad * 180.0 / math.pi;

/// المسافة بالمتر بين نقطتين (haversine_m في الخادم).
double haversineM(LatLng a, LatLng b) {
  final phi1 = _rad(a.latitude), phi2 = _rad(b.latitude);
  final dphi = _rad(b.latitude - a.latitude);
  final dlam = _rad(b.longitude - a.longitude);
  final h =
      math.pow(math.sin(dphi / 2), 2) +
      math.cos(phi1) * math.cos(phi2) * math.pow(math.sin(dlam / 2), 2);
  return 2 * kEarthRadiusM * math.asin(math.sqrt(h));
}

/// مساحة حلقة واحدة بالمتر² (polygon_area_m2 في الخادم). الحلقة مفتوحة أو
/// مغلقة، بأيّ اتّجاه. أقلّ من 3 رؤوس ⇒ 0.
double ringAreaM2(List<LatLng> ring) {
  if (ring.length < 3) return 0;
  final coords = closeRing(ring);
  var total = 0.0;
  for (var i = 0; i < coords.length - 1; i++) {
    final p1 = coords[i], p2 = coords[i + 1];
    total +=
        _rad(p2.longitude - p1.longitude) *
        (2 + math.sin(_rad(p1.latitude)) + math.sin(_rad(p2.latitude)));
  }
  return (total * kEarthRadiusM * kEarthRadiusM / 2).abs();
}

/// الحلقة كما يطبّعها الخادم قبل الحساب: تقريب 7 منازل + إزالة المتتالي المكرّر.
List<LatLng> serverNormalizedRing(List<LatLng> ring) {
  double r(double v) {
    const f = 1e7;
    return (v * f).round() / f;
  }

  return openRing([
    for (final p in ring) LatLng(r(p.latitude), r(p.longitude)),
  ]);
}

/// المساحة بالهكتار **كما يحسبها الخادم**: مجموع الحلقات الخارجيّة لكلّ الأجزاء
/// بعد تقريب 7 منازل. هذه القيمة المعروضة كمساحة الحقل قبل الحفظ.
double serverAreaHa(FieldGeometry g) {
  var m2 = 0.0;
  for (final p in g.polygons) {
    m2 += ringAreaM2(serverNormalizedRing(p.outer));
  }
  return m2 / 10000.0;
}

/// المساحة الصافية بالهكتار (الخارجيّة − الثقوب). لا يخزّنها الخادم اليوم.
double netAreaHa(FieldGeometry g) {
  var m2 = 0.0;
  for (final p in g.polygons) {
    m2 += ringAreaM2(p.outer);
    for (final h in p.holes) {
      m2 -= ringAreaM2(h);
    }
  }
  return math.max(0, m2) / 10000.0;
}

/// محيط حلقة مغلقة بالمتر (haversine).
double ringPerimeterM(List<LatLng> ring) {
  if (ring.length < 2) return 0;
  final c = closeRing(ring);
  var sum = 0.0;
  for (var i = 0; i < c.length - 1; i++) {
    sum += haversineM(c[i], c[i + 1]);
  }
  return sum;
}

/// طول خطّ مفتوح بالمتر.
double lineLengthM(List<LatLng> line) {
  var sum = 0.0;
  for (var i = 0; i < line.length - 1; i++) {
    sum += haversineM(line[i], line[i + 1]);
  }
  return sum;
}

/// النقطة على بعد [distanceM] من [origin] باتّجاه [bearingDeg] (من الشمال، مع
/// عقارب الساعة) على كرة نصف قطرها [kEarthRadiusM]. ⇒ haversineM يعيد المسافة
/// نفسها تماماً (بخلاف تقريب 111320 م/درجة القديم: 399.55 م لنصف قطر 400).
LatLng destinationPoint(LatLng origin, double distanceM, double bearingDeg) {
  final delta = distanceM / kEarthRadiusM;
  final theta = _rad(bearingDeg);
  final phi1 = _rad(origin.latitude), lam1 = _rad(origin.longitude);
  final phi2 = math.asin(
    math.sin(phi1) * math.cos(delta) +
        math.cos(phi1) * math.sin(delta) * math.cos(theta),
  );
  final lam2 =
      lam1 +
      math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
      );
  final lon = (_deg(lam2) + 540) % 360 - 180;
  return LatLng(_deg(phi2), lon);
}

/// حلقة دائريّة مفتوحة (حقل محوريّ) حول [center] بنصف قطر [radiusM] متر،
/// عكس عقارب الساعة. كلّ رأس على بعد [radiusM] تماماً بقياس haversineM.
List<LatLng> circleRing(LatLng center, double radiusM, {int segments = 96}) {
  if (radiusM <= 0 || segments < 3) return const [];
  return [
    for (var i = 0; i < segments; i++)
      // الاتّجاه يتناقص ⇒ عكس عقارب الساعة.
      destinationPoint(center, radiusM, 360.0 - 360.0 * i / segments),
  ];
}
