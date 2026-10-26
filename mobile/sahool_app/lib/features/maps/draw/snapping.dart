// SAHOOL — features/maps/draw/snapping.dart
// التقاط رأسٍ إلى رؤوس الحقول القائمة أو أضلاعها، منقولٌ من `snapPoint` في الويب
// (frontend/src/lib/geo.ts): الرأس أوّلاً، ثمّ الضلع، ضمن تسامحٍ بالأمتار.
// خارج التسامح تُعاد النقطة كما هي — لا تحريك صامت.
//
// التسامح يُعطى بالأمتار؛ واجهة الرسم تحوّله من بكسلات الشاشة عبر
// `metersPerPixel` كي يبقى ثابتاً تحت الإصبع مهما كان التكبير.
import 'dart:math' as math;

import 'package:latlong2/latlong.dart';

import 'geo_measure.dart';

enum SnapKind { none, vertex, edge }

class SnapResult {
  const SnapResult(this.point, this.kind, this.distanceM);
  final LatLng point;
  final SnapKind kind;
  final double distanceM;
  bool get snapped => kind != SnapKind.none;
}

/// أقرب نقطة على القطعة [a]-[b] إلى [p] في إسقاطٍ محلّيّ متساوي المستطيلات
/// (دقيق بما يكفي لمسافات الالتقاط القصيرة)، مع المسافة بالأمتار.
(LatLng, double) nearestOnSegment(LatLng p, LatLng a, LatLng b) {
  final k = math.cos(p.latitude * math.pi / 180.0);
  final ax = (a.longitude - p.longitude) * k, ay = a.latitude - p.latitude;
  final bx = (b.longitude - p.longitude) * k, by = b.latitude - p.latitude;
  final dx = bx - ax, dy = by - ay;
  final len2 = dx * dx + dy * dy;
  var t = len2 == 0 ? 0.0 : -(ax * dx + ay * dy) / len2;
  t = t.clamp(0.0, 1.0);
  final q = LatLng(
    a.latitude + (b.latitude - a.latitude) * t,
    a.longitude + (b.longitude - a.longitude) * t,
  );
  return (q, haversineM(p, q));
}

/// يلتقط [p] لأقرب رأس ضمن [toleranceM]، وإلّا لأقرب ضلع. [targets]: حلقات
/// مفتوحة أو مغلقة؛ تُعامَل أضلاعها مع ضلع الإغلاق.
SnapResult snapPoint(
  LatLng p,
  Iterable<List<LatLng>> targets, {
  required double toleranceM,
}) {
  if (toleranceM <= 0) return SnapResult(p, SnapKind.none, 0);
  LatLng? bestV;
  var bestVd = double.infinity;
  LatLng? bestE;
  var bestEd = double.infinity;
  for (final ring in targets) {
    if (ring.isEmpty) continue;
    for (final v in ring) {
      final d = haversineM(p, v);
      if (d <= toleranceM && d < bestVd) {
        bestV = v;
        bestVd = d;
      }
    }
    final n = ring.length;
    if (n < 2) continue;
    final closed = ring.first == ring.last;
    final segs = closed ? n - 1 : n;
    for (var i = 0; i < segs; i++) {
      final (q, d) = nearestOnSegment(p, ring[i], ring[(i + 1) % n]);
      if (d <= toleranceM && d < bestEd) {
        bestE = q;
        bestEd = d;
      }
    }
  }
  if (bestV != null) return SnapResult(bestV, SnapKind.vertex, bestVd);
  if (bestE != null) return SnapResult(bestE, SnapKind.edge, bestEd);
  return SnapResult(p, SnapKind.none, 0);
}
