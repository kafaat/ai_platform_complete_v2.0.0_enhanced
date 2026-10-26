// محوّل GeoJSON ↔ LatLng: ترتيب المحاور، الإغلاق، الاتّجاه، الثقوب، MultiPolygon.
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/features/maps/geo/geo_json.dart';
import 'package:sahool_app/features/maps/geo/geojson_codec.dart' as codec;

// حلقة مع عقارب الساعة (CW) عمداً — يجب أن تخرج CCW.
const _outerCw = [
  [44.0, 15.0],
  [44.0, 15.01],
  [44.01, 15.01],
  [44.01, 15.0],
  [44.0, 15.0],
];
// ثقب عكس عقارب الساعة (CCW) عمداً — يجب أن يخرج CW.
const _holeCcw = [
  [44.003, 15.003],
  [44.006, 15.003],
  [44.006, 15.006],
  [44.003, 15.006],
  [44.003, 15.003],
];

List<LatLng> _ring(List<List<double>> c) => [
  for (final p in c) LatLng(p[1], p[0]),
];

void main() {
  group('reading', () {
    test('Polygon: [lon,lat] order, ring kept open in memory', () {
      final g = FieldGeometry.fromGeoJson({
        'type': 'Polygon',
        'coordinates': [_outerCw],
      });
      expect(g.polygons, hasLength(1));
      final outer = g.polygons.single.outer;
      expect(outer, hasLength(4), reason: 'closing vertex dropped');
      expect(outer.first.latitude, 15.0);
      expect(outer.first.longitude, 44.0);
    });

    test('MultiPolygon with a hole keeps every part and the hole', () {
      final g = FieldGeometry.fromGeoJson({
        'type': 'MultiPolygon',
        'coordinates': [
          [_outerCw, _holeCcw],
          [
            [
              [44.02, 15.0],
              [44.03, 15.0],
              [44.03, 15.01],
              [44.02, 15.0],
            ],
          ],
        ],
      });
      expect(g.isMulti, isTrue);
      expect(g.polygons[0].holes, hasLength(1));
      expect(g.polygons[1].holes, isEmpty);
      expect(g.hasHoles, isTrue);
    });

    test(
      'Feature, FeatureCollection and JSON text; non-polygons are counted',
      () {
        final fc =
            '''
      {"type":"FeatureCollection","features":[
        {"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[${_outerCw.toString()}]}},
        {"type":"Feature","properties":{},"geometry":{"type":"Point","coordinates":[44,15]}},
        {"type":"Feature","properties":{},"geometry":null}
      ]}''';
        final g = FieldGeometry.fromGeoJson(fc);
        expect(g.polygons, hasLength(1));
        expect(g.skippedParts, 2);
      },
    );

    test('third coordinate (altitude) is ignored', () {
      final g = FieldGeometry.fromGeoJson({
        'type': 'Polygon',
        'coordinates': [
          [
            [44.0, 15.0, 1200],
            [44.01, 15.0, 1201],
            [44.01, 15.01, 1202],
            [44.0, 15.0, 1200],
          ],
        ],
      });
      expect(g.polygons.single.outer, hasLength(3));
    });

    test('bad input throws FormatException; tryParse returns null', () {
      for (final bad in <Object?>[
        {'type': 'Polygon', 'coordinates': []},
        {
          'type': 'Polygon',
          'coordinates': [
            [
              ['a', 15],
              [44, 15],
              [44, 16],
            ],
          ],
        },
        {
          'type': 'Polygon',
          'coordinates': [
            [
              [15, 95],
              [16, 95],
              [16, 96],
            ],
          ],
        },
        {
          'type': 'Point',
          'coordinates': [44, 15],
        },
        {'type': 'Circle'},
        'not json',
      ]) {
        expect(
          () => FieldGeometry.fromGeoJson(bad),
          throwsFormatException,
          reason: '$bad',
        );
        expect(FieldGeometry.tryParse(bad), isNull);
      }
      expect(FieldGeometry.tryParse(null), isNull);
    });

    test('degenerate hole is dropped and counted, not kept', () {
      final g = FieldGeometry.fromGeoJson({
        'type': 'Polygon',
        'coordinates': [
          _outerCw,
          [
            [44.003, 15.003],
            [44.004, 15.004],
            [44.003, 15.003],
          ],
        ],
      });
      expect(g.polygons.single.holes, isEmpty);
      expect(g.skippedParts, 1);
    });
  });

  group('writing', () {
    test('rings are closed, outer CCW, holes CW (RFC 7946)', () {
      final g = FieldGeometry.polygon(_ring(_outerCw), [_ring(_holeCcw)]);
      final out = g.toGeoJson();
      expect(out['type'], 'Polygon');
      final rings = out['coordinates'] as List;
      final outer = (rings[0] as List).cast<List<double>>();
      final hole = (rings[1] as List).cast<List<double>>();
      expect(outer.first, outer.last, reason: 'closed');
      expect(hole.first, hole.last, reason: 'closed');
      expect(isCounterClockwise(_ring(outer)), isTrue);
      expect(isCounterClockwise(_ring(hole)), isFalse);
      // [lon, lat]
      expect(outer.first[0], closeTo(44.0, 1e-12));
      expect(outer.first[1], closeTo(15.0, 1e-12));
    });

    test('one part ⇒ Polygon, several ⇒ MultiPolygon, forceMulti honoured', () {
      final one = FieldGeometry.polygon(_ring(_outerCw));
      expect(one.toGeoJson()['type'], 'Polygon');
      expect(one.toGeoJson(forceMulti: true)['type'], 'MultiPolygon');
      final two = FieldGeometry([
        GeoPolygon(_ring(_outerCw)),
        GeoPolygon(_ring(_holeCcw)),
      ]);
      expect(two.toGeoJson()['type'], 'MultiPolygon');
    });

    test('decimals rounds like the server guard (7 places)', () {
      final g = FieldGeometry.polygon(const [
        LatLng(15.123456789, 44.123456789),
        LatLng(15.2, 44.123456789),
        LatLng(15.2, 44.2),
      ]);
      final first =
          ((g.toGeoJson(decimals: 7)['coordinates'] as List)[0] as List)[0]
              as List<double>;
      expect(first, [44.1234568, 15.1234568]);
    });

    test('empty geometry cannot be written', () {
      expect(() => FieldGeometry(const []).toGeoJson(), throwsStateError);
    });
  });

  group('round trip', () {
    test('MultiPolygon with holes survives read → write → read', () {
      final src = {
        'type': 'MultiPolygon',
        'coordinates': [
          [_outerCw, _holeCcw],
          [
            [
              [44.02, 15.0],
              [44.03, 15.0],
              [44.03, 15.01],
              [44.02, 15.0],
            ],
          ],
        ],
      };
      final a = FieldGeometry.fromGeoJson(src);
      final b = FieldGeometry.fromGeoJson(a.toGeoJson());
      expect(b.polygons, hasLength(2));
      expect(b.polygons[0].holes, hasLength(1));
      // نفس الرؤوس (قد ينعكس الترتيب لتصحيح الاتّجاه).
      expect(b.polygons[0].outer.toSet(), a.polygons[0].outer.toSet());
      expect(b.polygons[0].holes[0].toSet(), a.polygons[0].holes[0].toSet());
      // كتابة ثانية مستقرّة.
      expect(FieldGeometry.fromGeoJson(b.toGeoJson()), b);
    });
  });

  group('helpers', () {
    test('closeRing/openRing are inverse and idempotent', () {
      final open = _ring(_outerCw).sublist(0, 4);
      final closed = closeRing(open);
      expect(closed, hasLength(5));
      expect(closeRing(closed), hasLength(5));
      expect(openRing(closed), open);
      expect(openRing(open), open);
    });

    test('contains respects holes and every MultiPolygon part', () {
      final g = FieldGeometry([
        GeoPolygon(_ring(_outerCw), [_ring(_holeCcw)]),
        GeoPolygon(
          _ring(const [
            [44.02, 15.0],
            [44.03, 15.0],
            [44.03, 15.01],
            [44.02, 15.01],
          ]),
        ),
      ]);
      expect(g.contains(const LatLng(15.001, 44.001)), isTrue);
      expect(
        g.contains(const LatLng(15.0045, 44.0045)),
        isFalse,
        reason: 'inside the hole',
      );
      expect(
        g.contains(const LatLng(15.005, 44.025)),
        isTrue,
        reason: 'second part',
      );
      expect(g.contains(const LatLng(15.005, 44.015)), isFalse);
    });

    test('bounds cover every part', () {
      final g = FieldGeometry.fromGeoJson({
        'type': 'MultiPolygon',
        'coordinates': [
          [_outerCw],
          [
            [
              [44.02, 15.0],
              [44.03, 15.0],
              [44.03, 15.02],
              [44.02, 15.0],
            ],
          ],
        ],
      });
      final b = g.bounds!;
      expect(b.west, 44.0);
      expect(b.east, 44.03);
      expect(b.north, 15.02);
    });

    test('geojson_codec.dart re-exports the same converter', () {
      expect(
        codec.FieldGeometry.tryParse({
          'type': 'Polygon',
          'coordinates': [_outerCw],
        }),
        isA<FieldGeometry>(),
      );
    });
  });
}
