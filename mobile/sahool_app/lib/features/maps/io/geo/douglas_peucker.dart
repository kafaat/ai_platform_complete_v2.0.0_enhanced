// SAHOOL — features/maps/io/geo/douglas_peucker.dart
// تبسيط Douglas–Peucker بتسامح بالأمتار. مسار المشي حول الحقل يجمع مئات
// القراءات؛ الخادم يقبل ≤2000 رأس، والرؤوس المتقاربة على خطّ مستقيم لا تضيف
// دقّة بل ضجيج GPS. الإسقاط محلّيّ متساوي المسافات حول أوّل نقطة (خطأ مهمَل على
// مقياس حقل).
import 'dart:math' as math;

import 'package:latlong2/latlong.dart';

import 'io_measure.dart' show kEarthRadiusM;

class _Xy {
  const _Xy(this.x, this.y);
  final double x;
  final double y;
}

List<_Xy> _project(List<LatLng> pts) {
  final lat0 = pts.first.latitude * math.pi / 180;
  final k = math.cos(lat0);
  return [
    for (final p in pts)
      _Xy(
        p.longitude * math.pi / 180 * kEarthRadiusM * k,
        p.latitude * math.pi / 180 * kEarthRadiusM,
      ),
  ];
}

double _segDist(_Xy p, _Xy a, _Xy b) {
  final dx = b.x - a.x, dy = b.y - a.y;
  final len2 = dx * dx + dy * dy;
  if (len2 == 0) {
    return math.sqrt(math.pow(p.x - a.x, 2) + math.pow(p.y - a.y, 2));
  }
  final t = (((p.x - a.x) * dx + (p.y - a.y) * dy) / len2).clamp(0.0, 1.0);
  final cx = a.x + t * dx, cy = a.y + t * dy;
  return math.sqrt(math.pow(p.x - cx, 2) + math.pow(p.y - cy, 2));
}

/// يبسّط خطّاً مفتوحاً مع الإبقاء على الطرفين. [toleranceM] ≤ 0 ⇒ بلا تغيير.
List<LatLng> simplifyPolyline(List<LatLng> points, double toleranceM) {
  if (points.length < 3 || toleranceM <= 0) return List.of(points);
  final xy = _project(points);
  final keep = List<bool>.filled(points.length, false);
  keep[0] = true;
  keep[points.length - 1] = true;
  // مكدّس صريح بدل العودية (مسارات طويلة لا تُفيض المكدّس).
  final stack = <(int, int)>[(0, points.length - 1)];
  while (stack.isNotEmpty) {
    final (s, e) = stack.removeLast();
    var maxD = -1.0;
    var idx = -1;
    for (var i = s + 1; i < e; i++) {
      final d = _segDist(xy[i], xy[s], xy[e]);
      if (d > maxD) {
        maxD = d;
        idx = i;
      }
    }
    if (idx > 0 && maxD > toleranceM) {
      keep[idx] = true;
      stack
        ..add((s, idx))
        ..add((idx, e));
    }
  }
  return [
    for (var i = 0; i < points.length; i++)
      if (keep[i]) points[i],
  ];
}

/// يبسّط حلقة مفتوحة (بلا نقطة إغلاق). تُقسَم عند أبعد نقطة عن الأولى كي لا
/// يكون للطرفين امتياز، ثمّ تُبسَّط كلّ نصف. لا تنزل عن ثلاث نقاط: إن انهارت
/// الحلقة تُعاد كما هي (لا مضلّع مُشوَّه بصمت).
List<LatLng> simplifyRing(List<LatLng> ring, double toleranceM) {
  if (ring.length <= 3 || toleranceM <= 0) return List.of(ring);
  final xy = _project(ring);
  var far = 1;
  var farD = -1.0;
  for (var i = 1; i < ring.length; i++) {
    final d = math.sqrt(
      math.pow(xy[i].x - xy[0].x, 2) + math.pow(xy[i].y - xy[0].y, 2),
    );
    if (d > farD) {
      farD = d;
      far = i;
    }
  }
  final a = simplifyPolyline(ring.sublist(0, far + 1), toleranceM);
  final b = simplifyPolyline([...ring.sublist(far), ring.first], toleranceM);
  final out = [...a, ...b.sublist(1, b.length - 1)];
  return out.length >= 3 ? out : List.of(ring);
}
