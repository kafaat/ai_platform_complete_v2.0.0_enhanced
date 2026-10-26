// المساحة بصيغة الخادم نفسها. القيم المتوقّعة حُسبت بتشغيل كود الخادم الحقيقيّ
// على هذه المدخلات نفسها:
//   from api import gis_geometry_guard as g
//   g._combined_area_bbox(g.normalize_geojson_polygonal(geom))[0]
// (services/sahool-platform/api/gis_geometry_guard.py + geospatial_integrity.py).
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/features/maps/geo/geo_json.dart';
import 'package:sahool_app/features/maps/geo/geo_measure.dart';

const _fixtures = <String, (Map<String, Object>, double)>{
  'sanaa_small': (
    {
      'type': 'Polygon',
      'coordinates': [
        [
          [44.20612, 15.35481],
          [44.20731, 15.35477],
          [44.20745, 15.35569],
          [44.20660, 15.35601],
          [44.20601, 15.35552],
          [44.20612, 15.35481],
        ],
      ],
    },
    1.6375000437295402,
  ),
  'jawf_100ha': (
    {
      'type': 'Polygon',
      'coordinates': [
        [
          [44.70, 16.20],
          [44.70941, 16.20],
          [44.70941, 16.209],
          [44.70, 16.209],
          [44.70, 16.20],
        ],
      ],
    },
    100.55355735901693,
  ),
  'tihama_large': (
    {
      'type': 'Polygon',
      'coordinates': [
        [
          [43.10, 14.50],
          [43.30, 14.48],
          [43.32, 14.65],
          [43.12, 14.68],
          [43.10, 14.50],
        ],
      ],
    },
    42480.28082116118,
  ),
  // الخادم يجمع الحلقات الخارجيّة ولا يطرح الثقب.
  'multi_with_hole': (
    {
      'type': 'MultiPolygon',
      'coordinates': [
        [
          [
            [45.00, 15.00],
            [45.01, 15.00],
            [45.01, 15.01],
            [45.00, 15.01],
            [45.00, 15.00],
          ],
          [
            [45.003, 15.003],
            [45.003, 15.006],
            [45.006, 15.006],
            [45.006, 15.003],
            [45.003, 15.003],
          ],
        ],
        [
          [
            [45.02, 15.00],
            [45.025, 15.00],
            [45.025, 15.004],
            [45.02, 15.00],
          ],
        ],
      ],
    },
    131.37054603116096,
  ),
};

/// صيغة المعالج القديمة (إسقاط مستطيليّ، R = 6378137) — للبرهنة على الفرق.
double _legacyWizardAreaHa(List<LatLng> pts) {
  const r = 6378137.0;
  final lat0 =
      pts.map((p) => p.latitude).reduce((a, b) => a + b) /
      pts.length *
      math.pi /
      180;
  double x(LatLng p) => p.longitude * math.pi / 180 * r * math.cos(lat0);
  double y(LatLng p) => p.latitude * math.pi / 180 * r;
  var s = 0.0;
  for (var i = 0; i < pts.length; i++) {
    final a = pts[i], b = pts[(i + 1) % pts.length];
    s += x(a) * y(b) - x(b) * y(a);
  }
  return s.abs() / 2 / 10000;
}

void main() {
  group('serverAreaHa matches the server on fixtures within 0.01%', () {
    _fixtures.forEach((name, f) {
      test(name, () {
        final g = FieldGeometry.fromGeoJson(f.$1);
        final got = serverAreaHa(g);
        final rel = (got - f.$2).abs() / f.$2;
        expect(rel, lessThan(1e-4), reason: 'got $got expected ${f.$2}');
      });
    });
  });

  test('orientation does not change the area', () {
    final g = FieldGeometry.fromGeoJson(_fixtures['jawf_100ha']!.$1);
    final reversed = FieldGeometry.polygon(
      g.polygons.single.outer.reversed.toList(),
    );
    expect(serverAreaHa(reversed), closeTo(serverAreaHa(g), 1e-9));
  });

  test(
    'netAreaHa subtracts holes; serverAreaHa does not (server behaviour)',
    () {
      final g = FieldGeometry.fromGeoJson(_fixtures['multi_with_hole']!.$1);
      final hole = ringAreaM2(g.polygons.first.holes.single) / 10000;
      expect(netAreaHa(g), closeTo(serverAreaHa(g) - hole, 1e-6));
      expect(hole, greaterThan(9));
    },
  );

  test('the old wizard formula disagrees with the server by ~0.22%', () {
    final g = FieldGeometry.fromGeoJson(_fixtures['jawf_100ha']!.$1);
    final legacy = _legacyWizardAreaHa(g.polygons.single.outer);
    final rel =
        (legacy - _fixtures['jawf_100ha']!.$2) / _fixtures['jawf_100ha']!.$2;
    expect(rel, greaterThan(0.002), reason: 'the bug this file fixes');
  });

  test('haversine matches the server radius', () {
    // درجة طول واحدة على خطّ الاستواء = 2πR/360.
    final d = haversineM(const LatLng(0, 0), const LatLng(0, 1));
    expect(d, closeTo(2 * math.pi * kEarthRadiusM / 360, 1e-6));
  });

  test('circleRing vertices sit exactly at the radius, CCW', () {
    const c = LatLng(15.35, 44.2);
    final ring = circleRing(c, 400, segments: 96);
    expect(ring, hasLength(96));
    for (final p in ring) {
      expect(haversineM(c, p), closeTo(400, 1e-6));
    }
    expect(isCounterClockwise(ring), isTrue);
    // مساحة الدائرة ≈ πr² (96 ضلعاً: خطأ المضلّع المنتظم < 0.1٪).
    final ha = serverAreaHa(FieldGeometry.polygon(ring));
    expect(ha, closeTo(math.pi * 400 * 400 / 10000, 0.05));
  });

  test('perimeter and line length', () {
    final g = FieldGeometry.fromGeoJson(_fixtures['jawf_100ha']!.$1);
    final per = ringPerimeterM(g.polygons.single.outer);
    expect(per, closeTo(4011, 15)); // ≈1003م × 4
    expect(
      lineLengthM(const [LatLng(0, 0), LatLng(0, 1)]),
      closeTo(haversineM(const LatLng(0, 0), const LatLng(0, 1)), 1e-9),
    );
  });
}
