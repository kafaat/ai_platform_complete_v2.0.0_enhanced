// قياس، تحقّق ما قبل الإرسال، وتبسيط Douglas–Peucker.
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/features/maps/io/geo/douglas_peucker.dart';
import 'package:sahool_app/features/maps/io/geo/io_geometry.dart';
import 'package:sahool_app/features/maps/io/geo/io_measure.dart';

import 'fixtures.dart';

List<LatLng> ll(List<List<double>> ring) =>
    openRing([for (final c in ring) LatLng(c[1], c[0])]);

void main() {
  group('measure', () {
    test('area matches the server spherical formula (~1.19 ha square)', () {
      // 0.001° × 0.001° at 15.35°N: 111.2 km × cos(15.35°) × 111.2 km × 1e-6.
      final expected =
          (0.001 * math.pi / 180 * kEarthRadiusM) *
          (0.001 * math.pi / 180 * kEarthRadiusM) *
          math.cos(15.3505 * math.pi / 180) /
          10000;
      final got = polygonAreaHa(IoPolygon([ll(square)]));
      expect((got - expected).abs() / expected, lessThan(0.001));
    });

    test('holes are subtracted', () {
      final full = polygonAreaHa(IoPolygon([ll(square)]));
      final holed = polygonAreaHa(IoPolygon([ll(square), ll(hole)]));
      expect(holed, closeTo(full * 0.91, full * 0.005));
    });

    test('haversine of 0.001° latitude ≈ 111 m', () {
      expect(
        haversineM(const LatLng(15, 44), const LatLng(15.001, 44)),
        closeTo(111.2, 0.2),
      );
    });
  });

  group('validateForSave', () {
    test('a bow-tie is blocked (the server would silently repair it)', () {
      expect(ringSelfIntersects(ll(bowtie)), isTrue);
      final codes = validateForSave(IoPolygon([ll(bowtie)])).map((i) => i.code);
      expect(codes, contains('self_intersection'));
    });

    test('a clean square passes with no issues', () {
      expect(ringSelfIntersects(ll(square)), isFalse);
      expect(validateForSave(IoPolygon([ll(square)])), isEmpty);
    });

    test('swapped axes are blocked; elsewhere-in-world only warns', () {
      // [lat,lon] written as [lon,lat]: latitude 44.2, longitude 15.35.
      final swapped = [for (final c in square) LatLng(c[0], c[1])];
      final issues = validateForSave(IoPolygon([openRing(swapped)]));
      final axes = issues.firstWhere((i) => i.code == 'axes_swapped');
      expect(axes.blocking, isTrue);
      // A real place outside Yemen (Chad, 14.2N 15.35E) only warns.
      final abroad = [for (final c in square) LatLng(c[0] - 30, c[1])];
      final far = validateForSave(IoPolygon([openRing(abroad)]));
      expect(
        far.firstWhere((i) => i.code == 'outside_yemen').blocking,
        isFalse,
      );
      expect(far.map((i) => i.code), isNot(contains('axes_swapped')));
    });

    test('below 0.001 ha is blocked', () {
      final tiny = [
        const LatLng(15.35, 44.2),
        const LatLng(15.35, 44.20001),
        const LatLng(15.35001, 44.20001),
      ];
      expect(
        validateForSave(IoPolygon([tiny])).map((i) => i.code),
        contains('area_too_small'),
      );
    });
  });

  group('Douglas–Peucker', () {
    test('collinear walking noise collapses to the corners', () {
      // 100 m edges sampled every ~1 m with ±0.5 m lateral noise.
      final pts = <LatLng>[];
      final rnd = math.Random(7);
      const d = 0.00001; // ~1.1 m
      for (var i = 0; i < 90; i++) {
        pts.add(
          LatLng(15.35 + (rnd.nextDouble() - 0.5) * d * 0.4, 44.2 + i * d),
        );
      }
      for (var i = 0; i < 90; i++) {
        pts.add(
          LatLng(15.35 + i * d, 44.2009 + (rnd.nextDouble() - 0.5) * d * 0.4),
        );
      }
      for (var i = 0; i < 90; i++) {
        pts.add(
          LatLng(15.3509 + (rnd.nextDouble() - 0.5) * d * 0.4, 44.2009 - i * d),
        );
      }
      final out = simplifyRing(pts, 3);
      expect(out.length, lessThanOrEqualTo(5));
      expect(out.length, greaterThanOrEqualTo(3));
      // Area is preserved within 2 %.
      final a0 = polygonAreaHa(IoPolygon([pts]));
      final a1 = polygonAreaHa(IoPolygon([out]));
      expect((a1 - a0).abs() / a0, lessThan(0.02));
    });

    test('a real corner is kept; zero tolerance is the identity', () {
      final line = [
        const LatLng(15.35, 44.2),
        const LatLng(15.35, 44.2005),
        const LatLng(15.3505, 44.2005),
      ];
      expect(simplifyPolyline(line, 3), hasLength(3));
      expect(simplifyPolyline(line, 0), line);
    });

    test('never collapses a ring below three vertices', () {
      final thin = [
        const LatLng(15.35, 44.2),
        const LatLng(15.35, 44.2005),
        const LatLng(15.350001, 44.2010),
        const LatLng(15.350001, 44.2002),
      ];
      expect(simplifyRing(thin, 50).length, greaterThanOrEqualTo(3));
    });
  });
}
