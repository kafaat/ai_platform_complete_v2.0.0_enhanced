// تحليل GeoJSON/KML على الجهاز: Polygon، MultiPolygon/MultiGeometry، الثقوب،
// الأجزاء المُهمَلة المُعلَنة، والمدخلات التالفة/غير الآمنة.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/maps/io/geo/boundary_writer.dart';
import 'package:sahool_app/features/maps/io/geo/import_model.dart';
import 'package:sahool_app/features/maps/io/geo/io_geometry.dart';

import 'fixtures.dart';

void main() {
  group('GeoJSON', () {
    test('bare Polygon: closing point removed, [lon,lat] axis order kept', () {
      final r = parseBoundaryText(polygonJson([square]));
      expect(r.format, BoundaryFormat.geojson);
      expect(r.shapes, hasLength(1));
      final outer = r.shapes.single.polygon.outer;
      expect(outer, hasLength(4)); // مفتوحة
      expect(outer.first.longitude, 44.2);
      expect(outer.first.latitude, 15.35);
    });

    test(
      'FeatureCollection: every polygon, holes, multipolygon parts, names',
      () {
        final r = parseBoundaryText(featureCollection());
        // Feature 1 (with hole) + MultiPolygon square2 (2nd part is a valid triangle).
        expect(r.shapes, hasLength(3));
        final first = r.shapes[0];
        expect(first.name, 'حقل البنّ');
        expect(first.polygon.holes, hasLength(1));
        expect(first.partIndex, isNull);
        expect(r.shapes[1].partIndex, 0);
        expect(r.shapes[2].partIndex, 1);
        expect(r.shapes[1].suggestedName(1), 'المدرّجات — جزء 1');
        // The Point is reported, not silently dropped.
        expect(r.warnings.join(), contains('Point'));
      },
    );

    test(
      'malformed JSON and polygon-free input throw an Arabic FormatException',
      () {
        expect(
          () => parseBoundaryText('{"type": "Polygon", '),
          throwsA(isA<FormatException>()),
        );
        expect(
          () => parseBoundaryText(
            '{"type":"Feature","geometry":{"type":"Point","coordinates":[44,15]}}',
          ),
          throwsA(
            isA<FormatException>().having(
              (e) => e.message,
              'message',
              contains('لا يوجد مضلّع'),
            ),
          ),
        );
      },
    );

    test(
      'NaN/out-of-range coordinates invalidate the ring, not the import',
      () {
        final r = parseBoundaryText(
          '{"type":"MultiPolygon","coordinates":[[${_ringJson(square)}],'
          '[[[200,15],[201,15],[201,16],[200,15]]]]}',
        );
        expect(r.shapes, hasLength(1));
        expect(r.warnings.single, contains('تالفة'));
      },
    );

    test('unknown text is rejected with guidance', () {
      expect(() => parseBoundaryText('hello'), throwsA(isA<FormatException>()));
      expect(() => parseBoundaryText('   '), throwsA(isA<FormatException>()));
    });
  });

  group('KML', () {
    for (final prefix in ['', 'kml:']) {
      test(
        'Placemark + MultiGeometry + innerBoundaryIs (prefix "$prefix")',
        () {
          final r = parseBoundaryText(kmlDoc(prefix: prefix));
          expect(r.format, BoundaryFormat.kml);
          expect(r.shapes, hasLength(3));
          expect(r.shapes[0].name, 'حقل البنّ & الذرة'); // CDATA + &
          expect(r.shapes[0].polygon.holes, hasLength(1));
          expect(r.shapes[0].polygon.outer, hasLength(4));
          expect(r.shapes[1].name, 'المدرّجات');
          expect(r.shapes[1].partIndex, 0);
          // "lon, lat" with a space after the comma still parses.
          expect(r.shapes[2].polygon.outer.first.longitude, 44.204);
          expect(r.warnings.join(), contains('ليس مضلّعاً'));
        },
      );
    }

    test('commented-out placemarks are ignored', () {
      final r = parseBoundaryText(kmlDoc());
      expect(r.shapes.map((s) => s.name), isNot(contains('معلَّق')));
    });

    test('DOCTYPE/ENTITY is refused (no entity expansion, like defusedxml)', () {
      const evil =
          '<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY x "y">]>'
          '<kml><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>'
          '44,15 44.1,15 44.1,15.1 44,15</coordinates></LinearRing>'
          '</outerBoundaryIs></Polygon></Placemark></kml>';
      expect(
        () => parseBoundaryText(evil),
        throwsA(
          isA<FormatException>().having(
            (e) => e.message,
            'message',
            contains('غير آمن'),
          ),
        ),
      );
    });

    test('KML with only a LineString has no polygon', () {
      expect(
        () => parseBoundaryText(
          '<kml><Placemark><LineString><coordinates>44,15 44.1,15'
          '</coordinates></LineString></Placemark></kml>',
        ),
        throwsA(isA<FormatException>()),
      );
    });

    test('bad coordinate token skips that polygon with a warning', () {
      final r = parseBoundaryText(
        '<kml><Placemark><MultiGeometry>'
        '<Polygon><outerBoundaryIs><LinearRing><coordinates>abc</coordinates>'
        '</LinearRing></outerBoundaryIs></Polygon>'
        '<Polygon><outerBoundaryIs><LinearRing><coordinates>${coords(square)}'
        '</coordinates></LinearRing></outerBoundaryIs></Polygon>'
        '</MultiGeometry></Placemark></kml>',
      );
      expect(r.shapes, hasLength(1));
      expect(r.warnings.first, contains('غير صالحة'));
    });
  });

  group('GeoJSON output', () {
    test('closed rings, CCW outer, CW hole (RFC 7946)', () {
      final p = parseBoundaryText(featureCollection()).shapes.first.polygon;
      final coords = polygonCoordinates(p);
      expect(coords.first.first, coords.first.last);
      double signed(List<List<double>> r) {
        var s = 0.0;
        for (var i = 0; i < r.length - 1; i++) {
          s += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1];
        }
        return s;
      }

      expect(signed(coords[0]), greaterThan(0));
      expect(signed(coords[1]), lessThan(0));
    });

    test('export round-trips through both parsers with parts and holes', () {
      final fieldRow = {
        'field_id': 'fld_1',
        'name': 'حقل <1>',
        'area_ha': 1.2,
        'geometry': {
          'type': 'MultiPolygon',
          'coordinates': [
            [square, hole],
            [square2],
          ],
        },
      };
      final b = ExportBoundary.fromField(fieldRow)!;
      for (final fmt in BoundaryFormat.values) {
        final file = buildExport([b], fmt, baseName: 'حقل 1');
        final back = parseBoundaryText(file.content);
        expect(back.shapes, hasLength(2), reason: fmt.name);
        expect(back.shapes[0].polygon.holes, hasLength(1), reason: fmt.name);
        expect(back.shapes[0].name, 'حقل <1>', reason: fmt.name);
        expect(back.shapes[1].polygon.outer, hasLength(4), reason: fmt.name);
      }
      expect(
        buildExport([b], BoundaryFormat.kml, baseName: 'حقل 1').fileName,
        'حقل_1.kml',
      );
    });

    test('a field without geometry is not exported', () {
      expect(
        ExportBoundary.fromField({'field_id': 'x', 'geometry': null}),
        isNull,
      );
    });
  });
}

String _ringJson(List<List<double>> ring) =>
    '[${ring.map((c) => '[${c[0]},${c[1]}]').join(',')}]';
