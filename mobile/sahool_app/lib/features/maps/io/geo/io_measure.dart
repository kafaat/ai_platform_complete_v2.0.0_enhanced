// SAHOOL — features/maps/io/geo/io_measure.dart
// قياس وتحقّق أدنى لحزمة io/. صيغة المساحة هي صيغة الخادم نفسها
// (services/sahool-platform/api/geospatial_integrity.py: polygon_area_m2 بنصف قطر
// 6371008.8) كي لا يرى المزارع رقمين مختلفين للحقل نفسه.
//
// توحيد: المسافة والمساحة والطول من maps/geo/geo_measure.dart (الصيغة نفسها
// حرفيّاً)؛ تُعاد تصديرها هنا كي لا يتغيّر استيراد ملفّات io/.
import 'dart:math' as math;

import 'package:latlong2/latlong.dart';

import '../../geo/geo_measure.dart';
import 'io_geometry.dart';

export '../../geo/geo_measure.dart'
    show haversineM, kEarthRadiusM, lineLengthM, ringAreaM2;

/// حدود الخادم (field_geometry_save_guard.py: ≤2000 رأس، ≥0.001 هـ).
const int kMaxServerVertices = 2000;
const double kMinFieldAreaHa = 0.001;

/// مساحة مضلّع بالهكتار (الخارجيّة ناقص الثقوب) — netAreaHa في geo لكن على IoPolygon.
double polygonAreaHa(IoPolygon p) {
  var m2 = ringAreaM2(p.outer);
  for (final h in p.holes) {
    m2 -= ringAreaM2(h);
  }
  return math.max(0, m2) / 10000;
}

/// هل تتقاطع أضلاع الحلقة (المفتوحة) مع بعضها؟ (فراشة/مسار مشي يعبر نفسه).
/// الخادم يُصلح ذلك بصمت إلى MultiPolygon؛ لذا يُحجَب هنا قبل الإرسال.
bool ringSelfIntersects(List<LatLng> ring) {
  final r = openRing(ring);
  final n = r.length;
  if (n < 4) return false;
  for (var i = 0; i < n; i++) {
    final a1 = r[i], a2 = r[(i + 1) % n];
    for (var j = i + 1; j < n; j++) {
      // الأضلاع المتجاورة تتشارك رأساً — ليست تقاطعاً.
      if (j == i || (j + 1) % n == i || (i + 1) % n == j) continue;
      final b1 = r[j], b2 = r[(j + 1) % n];
      if (_segmentsIntersect(a1, a2, b1, b2)) return true;
    }
  }
  return false;
}

double _cross(LatLng o, LatLng a, LatLng b) =>
    (a.longitude - o.longitude) * (b.latitude - o.latitude) -
    (a.latitude - o.latitude) * (b.longitude - o.longitude);

bool _onSegment(LatLng p, LatLng q, LatLng r) =>
    math.min(p.longitude, r.longitude) <= q.longitude &&
    q.longitude <= math.max(p.longitude, r.longitude) &&
    math.min(p.latitude, r.latitude) <= q.latitude &&
    q.latitude <= math.max(p.latitude, r.latitude);

bool _segmentsIntersect(LatLng p1, LatLng p2, LatLng q1, LatLng q2) {
  final d1 = _cross(q1, q2, p1);
  final d2 = _cross(q1, q2, p2);
  final d3 = _cross(p1, p2, q1);
  final d4 = _cross(p1, p2, q2);
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
      ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) {
    return true;
  }
  if (d1 == 0 && _onSegment(q1, p1, q2)) return true;
  if (d2 == 0 && _onSegment(q1, p2, q2)) return true;
  if (d3 == 0 && _onSegment(p1, q1, p2)) return true;
  if (d4 == 0 && _onSegment(p1, q2, p2)) return true;
  return false;
}

/// صندوق اليمن التقريبيّ (يطابق تحذير outside_yemen_bbox في الخادم بتسامح).
bool insideYemenBox(LatLng p) =>
    p.latitude >= 11.5 &&
    p.latitude <= 19.5 &&
    p.longitude >= 41.5 &&
    p.longitude <= 54.8;

/// مشكلة تحقّق على مضلّع. [blocking] ⇒ لا يُرسَل.
class GeometryIssue {
  const GeometryIssue(this.code, this.messageAr, {this.blocking = true});
  final String code;
  final String messageAr;
  final bool blocking;
}

/// فحوص ما قبل الإرسال. الخادم يقبل محاور معكوسة ومساحة صغيرة كتحذير فقط،
/// ويُصلح التقاطع الذاتيّ بصمت — لذا تُحجَب هنا صراحةً.
List<GeometryIssue> validateForSave(IoPolygon p) {
  final issues = <GeometryIssue>[];
  final outer = openRing(p.outer);
  if (outer.length < 3) {
    issues.add(
      const GeometryIssue(
        'too_few_vertices',
        'المضلّع يحتاج ثلاث نقاط مختلفة على الأقلّ.',
      ),
    );
    return issues;
  }
  if (p.vertexCount > kMaxServerVertices) {
    issues.add(
      GeometryIssue(
        'too_many_vertices',
        'عدد الرؤوس ${p.vertexCount} يتجاوز حدّ الخادم ($kMaxServerVertices) — بسّط الحدود.',
      ),
    );
  }
  if (ringSelfIntersects(outer)) {
    issues.add(
      const GeometryIssue(
        'self_intersection',
        'الحدّ يتقاطع مع نفسه — صحّح المسار قبل الحفظ.',
      ),
    );
  }
  if (polygonAreaHa(p) < kMinFieldAreaHa) {
    issues.add(
      const GeometryIssue(
        'area_too_small',
        'المساحة أصغر من 0.001 هـ (10 م²) — لا يُحفظ حقلاً.',
      ),
    );
  }
  final outside = outer.where((q) => !insideYemenBox(q)).length;
  if (outside == outer.length) {
    final swapped = outer.every(
      (q) => insideYemenBox(
        LatLng(q.longitude.clamp(-90.0, 90.0).toDouble(), q.latitude),
      ),
    );
    if (swapped) {
      issues.add(
        const GeometryIssue(
          'axes_swapped',
          'الإحداثيّات تبدو معكوسة (خطّ العرض مكان خطّ الطول). صدّر الملفّ بترتيب [lon,lat].',
        ),
      );
    } else {
      issues.add(
        const GeometryIssue(
          'outside_yemen',
          'الحدّ يقع خارج اليمن — تأكّد أنّه الحقل الصحيح.',
          blocking: false,
        ),
      );
    }
  }
  return issues;
}
