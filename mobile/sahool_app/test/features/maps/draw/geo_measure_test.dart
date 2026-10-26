// المساحة والمحور بصيغة الخادم. القيم المتوقَّعة حُسبت بتشغيل كود الخادم نفسه
// (api.gis_geometry_guard.guard_field_geometry و api.pivot_geometry) على المضلّعات
// ذاتها؛ فالاختبار يفشل إن عاد المعالج إلى تقريبٍ محلّيّ (كان +0.224٪).
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/features/maps/draw/geo_measure.dart';

List<LatLng> ring(List<List<double>> lonLat) => [
  for (final c in lonLat) LatLng(c[1], c[0]),
];

void main() {
  // fixture → (guard area ha 4dp, stored area ha 2dp) من الخادم.
  final fixtures = <String, (List<List<double>>, double, double)>{
    'small': (
      [
        [44.2001, 15.3501],
        [44.2004, 15.3501],
        [44.2004, 15.3503],
        [44.2001, 15.3503],
      ],
      0.0715,
      0.07,
    ),
    'square100': (
      [
        [44.20, 15.35],
        [44.2093, 15.35],
        [44.2093, 15.359],
        [44.20, 15.359],
      ],
      99.7956,
      99.8,
    ),
    'irregular (9-decimal input, rounded to 7 like the server)': (
      [
        [45.123456789, 14.987654321],
        [45.1301234, 14.9881111],
        [45.1322222, 14.9950005],
        [45.1255555, 14.9988888],
        [45.1199999, 14.9933333],
      ],
      106.764,
      106.76,
    ),
  };

  group('area equals the server formula', () {
    fixtures.forEach((name, f) {
      test(name, () {
        expect(serverGuardAreaHa(ring(f.$1)), f.$2);
        expect(serverStoredAreaHa(ring(f.$1)), f.$3);
      });
    });

    test('ring orientation and closure do not change the area', () {
      final r = ring(fixtures['square100']!.$1);
      expect(serverGuardAreaHa(r.reversed.toList()), 99.7956);
      expect(serverGuardAreaHa([...r, r.first]), 99.7956);
    });

    test('the old equirectangular R=6378137 estimate reads ~0.22% high', () {
      // الصيغة التي كان المعالج يعرضها — للتوثيق: الانحراف الذي أُزيل.
      final pts = ring(fixtures['square100']!.$1);
      const r = 6378137.0;
      final lat0 =
          pts.map((p) => p.latitude).reduce((a, b) => a + b) / pts.length;
      final k = math.cos(lat0 * math.pi / 180);
      var sum = 0.0;
      for (var i = 0; i < pts.length; i++) {
        final a = pts[i], b = pts[(i + 1) % pts.length];
        sum +=
            (r * a.longitude * math.pi / 180 * k) *
                (r * b.latitude * math.pi / 180) -
            (r * b.longitude * math.pi / 180 * k) *
                (r * a.latitude * math.pi / 180);
      }
      final old = sum.abs() / 2 / 10000;
      final drift = old / serverGuardAreaHa(pts)! - 1;
      expect(drift, greaterThan(0.002));
    });

    test('fewer than 3 distinct points is not a polygon', () {
      expect(
        serverGuardAreaHa(
          ring([
            [44.2, 15.3],
            [44.3, 15.3],
          ]),
        ),
        isNull,
      );
      expect(
        serverGuardAreaHa(
          ring([
            [44.2, 15.3],
            [44.2, 15.3],
            [44.3, 15.3],
          ]),
        ),
        isNull,
      );
    });
  });

  group('pivot polygon matches pivot_geometry.generate_pivot_polygon', () {
    final c = const LatLng(15.35, 44.2);
    final p = pivotPolygon(c, 400);

    test('96 vertices, north first, rounded to 7 decimals', () {
      expect(p, hasLength(96));
      expect(p[0], const LatLng(15.3535933, 44.2));
      expect(p[1], const LatLng(15.3535856, 44.2002437));
      expect(p[48], const LatLng(15.3464067, 44.2));
    });

    test('stored area equals the server (50.12 ha) and ~πr²', () {
      expect(serverGuardAreaHa(p), 50.1173);
      expect(serverStoredAreaHa(p), 50.12);
      final circle = math.pi * 400 * 400 / 10000;
      expect((serverGuardAreaHa(p)! - circle).abs() / circle, lessThan(0.005));
    });

    test(
      'vertices sit at the radius (old 111320 m/deg code gave 399.55 m)',
      () {
        for (final v in p) {
          expect(
            haversineM(c, v, earthRadiusM: kPivotEarthRadiusM),
            closeTo(400, 0.05),
          );
        }
      },
    );
  });

  test('pyRound rounds exact ties to even like Python', () {
    expect(pyRound(0.125, 2), 0.12);
    expect(pyRound(0.375, 2), 0.38);
    expect(pyRound(2.675, 2), 2.67); // 2.675 هو 2.67499… ثنائيّاً
    expect(pyRound(99.79564, 4), 99.7956);
    expect(pyRound(2.5, 0), 2.0);
    expect(pyRound(3.5, 0), 4.0);
    expect(pyRound(-0.125, 2), -0.12);
  });

  test('perimeter is the closed haversine length', () {
    final r = ring(fixtures['square100']!.$1);
    expect(perimeterM(r), closeTo(4 * 1000, 40));
  });

  test('metersPerPixel halves per zoom level', () {
    expect(metersPerPixel(15, 16) / metersPerPixel(15, 17), closeTo(2, 1e-9));
  });
}
