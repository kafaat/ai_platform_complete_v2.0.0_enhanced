// الطبقات: حقول (MultiPolygon + ثقوب + تسميات + نقر)، مؤشّر بترويسة مصادقة،
// دبابيس الكشف، الرسومات.
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/features/maps/data/maps_api.dart';
import 'package:sahool_app/features/maps/geo/geo_json.dart';
import 'package:sahool_app/features/maps/presentation/layers/drawings_layer.dart';
import 'package:sahool_app/features/maps/presentation/layers/fields_layer.dart';
import 'package:sahool_app/features/maps/presentation/layers/indicator_raster_layer.dart';
import 'package:sahool_app/features/maps/presentation/layers/scouting_pins_layer.dart';
import 'package:sahool_app/features/maps/presentation/widgets/sahool_map.dart';
import 'package:sahool_app/features/maps/presentation/widgets/sahool_map_controller.dart';

import '../../core/fake_http.dart';
import 'map_test_harness.dart';

void main() {
  group('fields layer', () {
    test('a MultiPolygon field with a hole is kept (was dropped before)', () {
      final f = MapField.fromSummary(summary('f1', multiWithHole));
      expect(f.hasGeometry, isTrue);
      final polys = buildFieldPolygons([
        f,
      ], tokens: const SahoolTokens(SahoolColors.light));
      expect(polys, hasLength(2), reason: 'one flutter_map polygon per part');
      expect(polys[0].holePointsList, hasLength(1));
      expect(polys.every((p) => p.hitValue == 'f1'), isTrue);
      expect(
        polys.where((p) => p.label != null),
        hasLength(1),
        reason: 'label once, on the largest part',
      );
      expect(polys[0].label, 'حقل');
    });

    test('fieldAt respects holes, parts and draw order', () {
      final fields = [
        MapField.fromSummary(summary('f1', multiWithHole)),
        MapField.fromSummary(
          summary('f2', {
            'type': 'Polygon',
            'coordinates': [
              [
                [44.008, 15.008],
                [44.012, 15.008],
                [44.012, 15.012],
                [44.008, 15.012],
                [44.008, 15.008],
              ],
            ],
          }),
        ),
      ];
      expect(fieldAt(fields, const LatLng(15.001, 44.001))?.id, 'f1');
      expect(
        fieldAt(fields, const LatLng(15.0045, 44.0045)),
        isNull,
        reason: 'hole',
      );
      expect(
        fieldAt(fields, const LatLng(15.001, 44.022))?.id,
        'f1',
        reason: 'second part',
      );
      expect(
        fieldAt(fields, const LatLng(15.009, 44.009))?.id,
        'f2',
        reason: 'top-most wins where they overlap',
      );
      expect(fieldAt(fields, const LatLng(14.0, 43.0)), isNull);
    });

    test(
      'status from quality_grade; unknown grade and missing geometry are honest',
      () {
        expect(
          MapField.fromSummary(summary('a', null, grade: 'BLOCKED')).status,
          FieldMapStatus.blocked,
        );
        expect(
          MapField.fromSummary(summary('a', null, grade: 'PENDING_LAB')).status,
          FieldMapStatus.pendingLab,
        );
        expect(
          MapField.fromSummary(summary('a', null, grade: 'WHATEVER')).status,
          FieldMapStatus.unknown,
        );
        final noGeom = MapField.fromSummary(summary('a', {'type': 'Polygon'}));
        expect(noGeom.hasGeometry, isFalse);
        expect(fieldsBounds([noGeom]), isNull);
      },
    );

    test('fill colour comes from status unless a measured NDVI is given', () {
      const t = SahoolTokens(SahoolColors.light);
      final f = MapField.fromSummary(
        summary('f', multiWithHole, grade: 'BLOCKED'),
      );
      expect(buildFieldPolygons([f], tokens: t).first.borderColor, t.danger);
      final withNdvi = f.copyWith(ndvi: 0.8);
      expect(
        buildFieldPolygons([withNdvi], tokens: t).first.borderColor,
        ndviColor(0.8),
      );
    });

    test('workspace route string', () {
      expect(
        fieldWorkspaceRoute('f 1/x'),
        '/fields/workspace?field_id=f+1%2Fx',
      );
    });
  });

  group('indicator raster layer', () {
    testWidgets('sends the Bearer token as a header, not in the URL', (
      t,
    ) async {
      final tok = fakeJwt(const Duration(hours: 1));
      final api = MapsApi(
        testClient(
          FakeAdapter((_) async => const FakeReply(200, {})),
          MemoryTokenStore(accessToken: tok),
        ),
      );
      final ctrl = SahoolMapController();
      addTearDown(ctrl.dispose);
      await t.pumpWidget(
        mapHost(
          SahoolMap(
            controller: ctrl,
            tileProviderFactory: MemoryTileProvider.new,
            layers: [
              IndicatorRasterLayer(
                fieldId: 'f1',
                mapsApi: api,
                geometry: FieldGeometry.fromGeoJson(multiWithHole),
              ),
            ],
          ),
        ),
      );
      for (var i = 0; i < 5; i++) {
        await t.pump(const Duration(milliseconds: 50));
      }
      final layers = t
          .widgetList<TileLayer>(find.byType(TileLayer))
          .where((l) => l.urlTemplate?.contains('/v1/fields/f1/') ?? false)
          .toList();
      expect(layers, hasLength(1));
      expect(layers.single.urlTemplate, isNot(contains('access_token')));
      expect(
        layers.single.tileProvider.headers['Authorization'],
        'Bearer $tok',
      );
      // إزالة الطبقة تلغي مؤقّت تجديد التوكن (لا مؤقّت معلّق).
      await t.pumpWidget(const SizedBox());
    });

    testWidgets('no session ⇒ no indicator layer (no anonymous requests)', (
      t,
    ) async {
      final api = MapsApi(
        testClient(
          FakeAdapter((_) async => const FakeReply(200, {})),
          MemoryTokenStore(),
        ),
      );
      final ctrl = SahoolMapController();
      addTearDown(ctrl.dispose);
      await t.pumpWidget(
        mapHost(
          SahoolMap(
            controller: ctrl,
            tileProviderFactory: MemoryTileProvider.new,
            layers: [IndicatorRasterLayer(fieldId: 'f1', mapsApi: api)],
          ),
        ),
      );
      await t.pump(const Duration(milliseconds: 100));
      expect(
        t
            .widgetList<TileLayer>(find.byType(TileLayer))
            .where((l) => l.urlTemplate?.contains('/v1/fields/') ?? false),
        isEmpty,
      );
      await t.pumpWidget(const SizedBox());
    });
  });

  testWidgets('scouting pins: 48dp targets, tap returns the pin', (t) async {
    ScoutingPin? tapped;
    final ctrl = SahoolMapController();
    addTearDown(ctrl.dispose);
    await t.pumpWidget(
      mapHost(
        SahoolMap(
          controller: ctrl,
          view: const MapViewTarget.center(LatLng(15.0, 44.0), zoom: 14),
          tileProviderFactory: MemoryTileProvider.new,
          layers: [
            ScoutingPinsLayer(
              pins: [
                ScoutingPin(
                  id: 'p1',
                  point: const LatLng(15.0, 44.0),
                  severity: PinSeverity.parse('high'),
                  label: 'منّ',
                ),
              ],
              onTap: (p) => tapped = p,
            ),
          ],
        ),
      ),
    );
    for (var i = 0; i < 5; i++) {
      await t.pump(const Duration(milliseconds: 50));
    }
    final pin = find.byKey(const ValueKey('scout-pin-p1'));
    expect(t.getSize(pin).width, greaterThanOrEqualTo(48));
    await t.tap(pin);
    expect(tapped?.id, 'p1');
    expect(tapped?.severity, PinSeverity.high);
    expect(find.bySemanticsLabel(RegExp('شدّة عالية')), findsOneWidget);
  });

  test(
    'drawings parse every server geometry type; broken ones are skipped',
    () {
      final zone = MapDrawing.fromJson({
        'id': 'd1',
        'kind': 'exclusion-zone',
        'geometry': multiWithHole,
        'properties': {'name': 'بئر'},
      })!;
      expect(zone.polygons!.polygons, hasLength(2));
      expect(zone.name, 'بئر');
      final path = MapDrawing.fromJson({
        'id': 'd2',
        'kind': 'path',
        'geometry': {
          'type': 'LineString',
          'coordinates': [
            [44.0, 15.0],
            [44.1, 15.1],
          ],
        },
      })!;
      expect(path.lines.single, hasLength(2));
      final pin = MapDrawing.fromJson({
        'id': 'd3',
        'kind': 'scout-pin',
        'geometry': {
          'type': 'Point',
          'coordinates': [44.0, 15.0],
        },
      })!;
      expect(pin.points.single, const LatLng(15.0, 44.0));
      expect(
        MapDrawing.fromJson({
          'id': 'bad',
          'kind': 'field',
          'geometry': {'type': 'Polygon', 'coordinates': []},
        }),
        isNull,
      );
    },
  );

  testWidgets('drawings layer renders zones, lines and points', (t) async {
    final ctrl = SahoolMapController();
    addTearDown(ctrl.dispose);
    await t.pumpWidget(
      mapHost(
        SahoolMap(
          controller: ctrl,
          tileProviderFactory: MemoryTileProvider.new,
          layers: [
            DrawingsLayer(
              drawings: [
                MapDrawing.fromJson({
                  'id': 'd1',
                  'kind': 'management-zone',
                  'geometry': multiWithHole,
                })!,
                MapDrawing.fromJson({
                  'id': 'd2',
                  'kind': 'path',
                  'geometry': {
                    'type': 'LineString',
                    'coordinates': [
                      [44.0, 15.0],
                      [44.1, 15.1],
                    ],
                  },
                })!,
              ],
            ),
          ],
        ),
      ),
    );
    await t.pump(const Duration(milliseconds: 100));
    expect(t.takeException(), isNull);
    expect(find.byType(PolygonLayer), findsOneWidget);
    expect(find.byType(PolylineLayer), findsOneWidget);
  });
}
