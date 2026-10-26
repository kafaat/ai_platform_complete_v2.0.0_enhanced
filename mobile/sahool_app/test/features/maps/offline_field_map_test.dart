// الودجت القديم المثبَّت (lib/widgets/offline_field_map.dart): كلّ اختبار هنا كان
// يفشل قبل إصلاحه — النسبة غائبة، الكاميرا لا تتبع، التدوير مفعّل، دائرة 399.55م،
// طقس مُختلَق، والحزمة لا تُعاد قراءتها.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:mbtiles/mbtiles.dart';
import 'package:sahool_app/features/maps/geo/geo_measure.dart';
import 'package:sahool_app/widgets/offline_field_map.dart';

import 'map_test_harness.dart';

const _tiles = 'http://localhost:1/{z}/{x}/{y}.png';

final _poly = [
  Polygon(
    points: const [
      LatLng(15.0, 44.0),
      LatLng(15.0, 44.01),
      LatLng(15.01, 44.01),
    ],
  ),
];

MapCamera _camera(WidgetTester t) =>
    MapCamera.of(t.element(find.byType(PolygonLayer)));

Future<void> _settle(WidgetTester t) async {
  for (var i = 0; i < 5; i++) {
    await t.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  testWidgets('Esri imagery is shown with a visible attribution', (t) async {
    await t.pumpWidget(
      mapHost(
        OfflineFieldMap(center: const LatLng(15, 44), fieldPolygons: _poly),
      ),
    );
    await _settle(t);
    final text = t.widget<Text>(find.byKey(const ValueKey('map-attribution')));
    expect(text.data, contains('Esri'));
  });

  testWidgets('rotation gesture is disabled', (t) async {
    await t.pumpWidget(
      mapHost(
        OfflineFieldMap(center: const LatLng(15, 44), networkTileUrl: _tiles),
      ),
    );
    await _settle(t);
    final fm = t.widget<FlutterMap>(find.byType(FlutterMap));
    expect(
      InteractiveFlag.hasRotate(fm.options.interactionOptions.flags),
      isFalse,
    );
  });

  testWidgets('camera follows a new center (GPS vertex off-screen)', (t) async {
    Widget host(LatLng c) => mapHost(
      OfflineFieldMap(center: c, networkTileUrl: _tiles, fieldPolygons: _poly),
    );
    await t.pumpWidget(host(const LatLng(15.0, 44.0)));
    await _settle(t);
    expect(_camera(t).center.latitude, closeTo(15.0, 1e-6));
    await t.pumpWidget(host(const LatLng(16.2, 44.7)));
    await _settle(t);
    expect(_camera(t).center.latitude, closeTo(16.2, 1e-6));
    expect(_camera(t).center.longitude, closeTo(44.7, 1e-6));
  });

  testWidgets('camera re-fits when the bounds change', (t) async {
    Widget host(LatLngBounds b) => mapHost(
      OfflineFieldMap(
        center: const LatLng(15, 44),
        bounds: b,
        networkTileUrl: _tiles,
        fieldPolygons: _poly,
      ),
    );
    await t.pumpWidget(
      host(LatLngBounds(const LatLng(15.0, 44.0), const LatLng(15.1, 44.1))),
    );
    await _settle(t);
    final b2 = LatLngBounds(const LatLng(13.0, 45.0), const LatLng(13.2, 45.3));
    await t.pumpWidget(host(b2));
    await _settle(t);
    expect(b2.contains(_camera(t).center), isTrue);
  });

  test('circlePolygon vertices sit at the requested radius (was 399.55 m)', () {
    const c = LatLng(15.35, 44.2);
    final ring = OfflineFieldMap.circlePolygon(c, 400);
    expect(ring, hasLength(48));
    for (final p in ring) {
      expect(haversineM(c, p), closeTo(400, 1e-6));
    }
    // البداية شرقاً كالسابق (توافق المستدعين).
    expect(ring.first.longitude, greaterThan(c.longitude));
    expect(ring.first.latitude, closeTo(c.latitude, 1e-6));
  });

  group('weather overlay paints only measured values', () {
    Finder overlay() => find.byWidgetPredicate(
      (w) =>
          w is CustomPaint &&
          w.painter.runtimeType.toString() == '_WeatherWindOverlayPainter',
    );

    testWidgets('no values ⇒ nothing painted (was 30 °C / wind 315°)', (
      t,
    ) async {
      await t.pumpWidget(
        mapHost(
          OfflineFieldMap(
            center: const LatLng(15, 44),
            networkTileUrl: _tiles,
            showWeatherOverlay: true,
          ),
        ),
      );
      await _settle(t);
      expect(overlay(), paintsNothing);
    });

    testWidgets(
      'a measured temperature tints, no wind lines without direction',
      (t) async {
        await t.pumpWidget(
          mapHost(
            OfflineFieldMap(
              center: const LatLng(15, 44),
              networkTileUrl: _tiles,
              showWeatherOverlay: true,
              weatherTempC: 40,
            ),
          ),
        );
        await _settle(t);
        expect(overlay(), paints..rect());
        expect(overlay(), isNot(paints..path()));
      },
    );
  });

  testWidgets('a pack path set later is opened and rendered (was dead code)', (
    t,
  ) async {
    final dir = await t.runAsync(
      () async => Directory.systemTemp.createTempSync('sahool_ofm_'),
    );
    addTearDown(() => dir!.deleteSync(recursive: true));
    final path = '${dir!.path}/region.mbtiles';
    await t.runAsync(() async {
      MbTiles.create(
        mbtilesPath: path,
        metadata: const MbTilesMetadata(name: 'r', format: 'png'),
      ).dispose();
    });
    Widget host(String? p) => mapHost(
      OfflineFieldMap(
        center: const LatLng(15, 44),
        networkTileUrl: _tiles,
        offlinePackFilePath: p,
      ),
    );
    await t.pumpWidget(host(null));
    await _settle(t);
    Text badge() =>
        t.widget<Text>(find.byKey(const ValueKey('offline-map-source')));
    expect(badge().data, 'خريطة الشبكة');
    await t.pumpWidget(host(path));
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await _settle(t);
    expect(badge().data, 'خريطة محفوظة');
    await t.pumpWidget(host(null));
    await _settle(t);
    expect(badge().data, 'خريطة الشبكة');
    await t.pumpWidget(const SizedBox());
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
  });

  testWidgets('disposing while the pack is opening does not call setState', (
    t,
  ) async {
    await t.pumpWidget(
      mapHost(
        OfflineFieldMap(
          center: const LatLng(15, 44),
          networkTileUrl: _tiles,
          offlinePackFilePath: '/nonexistent/x.pmtiles',
        ),
      ),
    );
    await t.pumpWidget(const SizedBox());
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 100)),
    );
    await t.pump();
    expect(t.takeException(), isNull);
  });
}
