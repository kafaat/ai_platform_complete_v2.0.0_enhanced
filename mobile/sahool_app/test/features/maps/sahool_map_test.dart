// الخريطة المشتركة: نسبة ظاهرة، كاميرا تتبع الحالة، تدوير معطّل افتراضيّاً،
// أدوات بمواضع اتّجاهيّة، منتقي خريطة الأساس، «موقعي».
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/features/maps/data/basemaps.dart';
import 'package:sahool_app/features/maps/data/device_location.dart';
import 'package:sahool_app/features/maps/data/maps_api.dart';
import 'package:sahool_app/features/maps/presentation/widgets/sahool_map.dart';
import 'package:sahool_app/features/maps/presentation/widgets/sahool_map_controller.dart';

import '../../core/fake_http.dart';
import 'map_test_harness.dart';

Future<void> settle(WidgetTester t) async {
  for (var i = 0; i < 5; i++) {
    await t.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  late SahoolMapController ctrl;
  setUp(() => ctrl = SahoolMapController());
  tearDown(() => ctrl.dispose());

  Widget map({
    MapViewTarget? view,
    bool allowRotation = false,
    LocateFn? locate,
    MapsApi? api,
  }) => mapHost(
    SahoolMap(
      controller: ctrl,
      view: view,
      allowRotation: allowRotation,
      locate: locate ?? () async => throw const LocationUnavailable('x'),
      mapsApi: api,
      tileProviderFactory: MemoryTileProvider.new,
    ),
  );

  testWidgets('attribution of the basemap is visible without a tap', (t) async {
    await t.pumpWidget(map());
    await settle(t);
    final attribution = find.byKey(const ValueKey('map-attribution'));
    expect(attribution, findsOneWidget);
    expect(t.widget<Text>(attribution).data, contains('Esri'));
    expect(attribution.hitTestable(), findsOneWidget, reason: 'on screen');
  });

  testWidgets('camera follows the view target when the state changes', (
    t,
  ) async {
    const a = LatLng(15.35, 44.20);
    const b = LatLng(16.20, 44.70);
    await t.pumpWidget(map(view: const MapViewTarget.center(a, zoom: 14)));
    await settle(t);
    expect(ctrl.camera!.center.latitude, closeTo(a.latitude, 1e-6));
    await t.pumpWidget(map(view: const MapViewTarget.center(b, zoom: 15)));
    await settle(t);
    expect(ctrl.camera!.center.latitude, closeTo(b.latitude, 1e-6));
    expect(ctrl.camera!.center.longitude, closeTo(b.longitude, 1e-6));
    expect(ctrl.camera!.zoom, closeTo(15, 1e-6));

    // تأطير حدود: المركز داخلها.
    final bounds = LatLngBounds(
      const LatLng(14.0, 43.0),
      const LatLng(14.2, 43.3),
    );
    await t.pumpWidget(map(view: MapViewTarget.bounds(bounds)));
    await settle(t);
    expect(bounds.contains(ctrl.camera!.center), isTrue);
  });

  testWidgets(
    'controller commands issued before the map is ready are applied',
    (t) async {
      ctrl.moveTo(const LatLng(13.5, 44.0), zoom: 12);
      await t.pumpWidget(map());
      await settle(t);
      expect(ctrl.camera!.center.latitude, closeTo(13.5, 1e-6));
      expect(ctrl.camera!.zoom, closeTo(12, 1e-6));
    },
  );

  testWidgets('rotation is off by default; compass appears when allowed', (
    t,
  ) async {
    await t.pumpWidget(map());
    await settle(t);
    var fm = t.widget<FlutterMap>(find.byType(FlutterMap));
    expect(
      InteractiveFlag.hasRotate(fm.options.interactionOptions.flags),
      isFalse,
    );
    expect(find.byKey(const ValueKey('map-compass')), findsNothing);

    await t.pumpWidget(map(allowRotation: true));
    await settle(t);
    fm = t.widget<FlutterMap>(find.byType(FlutterMap));
    expect(
      InteractiveFlag.hasRotate(fm.options.interactionOptions.flags),
      isTrue,
    );
    ctrl.map.rotate(35);
    await settle(t);
    await t.tap(find.byKey(const ValueKey('map-compass')));
    await settle(t);
    expect(ctrl.camera!.rotation, 0);
  });

  testWidgets('controls sit on the end side in RTL; buttons are 48dp', (
    t,
  ) async {
    await t.pumpWidget(map());
    await settle(t);
    final mapRect = t.getRect(find.byType(FlutterMap));
    final zoomIn = t.getRect(find.byKey(const ValueKey('map-zoom-in')));
    final attribution = t.getRect(
      find.byKey(const ValueKey('map-attribution')),
    );
    // RTL: النهاية = اليسار، البداية = اليمين.
    expect(zoomIn.center.dx, lessThan(mapRect.center.dx));
    expect(attribution.center.dx, greaterThan(mapRect.center.dx));
    final btn = t.getSize(
      find.descendant(
        of: find.byKey(const ValueKey('map-zoom-in')),
        matching: find.byType(IconButton),
      ),
    );
    expect(btn.width, greaterThanOrEqualTo(48));
    expect(btn.height, greaterThanOrEqualTo(48));
  });

  testWidgets('zoom buttons change the camera', (t) async {
    await t.pumpWidget(
      map(view: const MapViewTarget.center(LatLng(15, 44), zoom: 10)),
    );
    await settle(t);
    await t.tap(find.byKey(const ValueKey('map-zoom-in')));
    await settle(t);
    expect(ctrl.camera!.zoom, closeTo(11, 1e-6));
  });

  testWidgets('basemap switch changes the tile URL and the attribution', (
    t,
  ) async {
    Basemap? changed;
    await t.pumpWidget(
      mapHost(
        SahoolMap(
          controller: ctrl,
          tileProviderFactory: MemoryTileProvider.new,
          onBasemapChanged: (b) => changed = b,
        ),
      ),
    );
    await settle(t);
    String baseUrl() => t
        .widget<TileLayer>(
          find
                  .byKey(const ValueKey('basemap-layer-satellite'))
                  .evaluate()
                  .isNotEmpty
              ? find.byKey(const ValueKey('basemap-layer-satellite'))
              : find.byKey(const ValueKey('basemap-layer-light')),
        )
        .urlTemplate!;
    expect(baseUrl(), Basemaps.satellite.urlTemplate);

    await t.tap(find.byKey(const ValueKey('map-layers')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const ValueKey('basemap-light')));
    await t.pumpAndSettle();

    expect(changed?.id, 'light');
    expect(baseUrl(), Basemaps.streets.urlTemplate);
    expect(
      t.widget<Text>(find.byKey(const ValueKey('map-attribution'))).data,
      contains('CARTO'),
    );
  });

  testWidgets('terrain stays off and says why when the server has no DEM', (
    t,
  ) async {
    final a = FakeAdapter(
      (_) async => const FakeReply(200, {
        'available': false,
        'user_message': 'التضاريس غير مُهيّأة (لا DEM)',
      }),
    );
    final api = MapsApi(
      testClient(
        a,
        MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
      ),
    );
    await t.pumpWidget(map(api: api));
    await settle(t);
    await t.tap(find.byKey(const ValueKey('map-layers')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const ValueKey('terrain-toggle')));
    await t.pumpAndSettle();
    expect(find.text('التضاريس غير مُهيّأة (لا DEM)'), findsOneWidget);
    expect(find.byKey(const ValueKey('terrain-hillshade')), findsNothing);
  });

  testWidgets('terrain hillshade layer is added when available', (t) async {
    final a = FakeAdapter(
      (_) async => const FakeReply(200, {'available': true}),
    );
    final api = MapsApi(
      testClient(
        a,
        MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
      ),
    );
    await t.pumpWidget(map(api: api));
    await settle(t);
    await t.tap(find.byKey(const ValueKey('map-layers')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const ValueKey('terrain-toggle')));
    await t.pumpAndSettle();
    final layer = t.widget<TileLayer>(
      find.byKey(const ValueKey('terrain-hillshade')),
    );
    expect(
      layer.urlTemplate,
      'https://api.test.invalid/api/raster/v1/elevation/hillshade/{z}/{x}/{y}.png',
    );
    expect(layer.tileProvider.headers['Authorization'], startsWith('Bearer '));
  });

  testWidgets('locate-me moves the camera and draws the accuracy circle', (
    t,
  ) async {
    const here = LatLng(15.40, 44.21);
    await t.pumpWidget(
      map(
        view: const MapViewTarget.center(LatLng(13, 45), zoom: 8),
        locate: () async => const LocationFix(here, accuracyM: 12),
      ),
    );
    await settle(t);
    await t.tap(find.byKey(const ValueKey('map-locate')));
    await settle(t);
    expect(ctrl.camera!.center.latitude, closeTo(here.latitude, 1e-6));
    expect(ctrl.camera!.zoom, greaterThanOrEqualTo(16));
    final circles = t.widget<CircleLayer>(find.byType(CircleLayer)).circles;
    expect(circles.single.radius, 12);
    expect(circles.single.useRadiusInMeter, isTrue);
  });

  testWidgets('locate-me failure is reported, no position is invented', (
    t,
  ) async {
    await t.pumpWidget(
      map(
        locate: () async => throw const LocationUnavailable('إذن الموقع مرفوض'),
      ),
    );
    await settle(t);
    await t.tap(find.byKey(const ValueKey('map-locate')));
    await settle(t);
    expect(find.text('إذن الموقع مرفوض'), findsOneWidget);
    expect(find.byType(CircleLayer), findsNothing);
  });

  testWidgets('a missing offline pack falls back to the network honestly', (
    t,
  ) async {
    await t.pumpWidget(
      mapHost(
        SahoolMap(
          controller: ctrl,
          tileProviderFactory: MemoryTileProvider.new,
          offlinePackPath: '/nonexistent/region.mbtiles',
        ),
      ),
    );
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await settle(t);
    expect(
      t.widget<Text>(find.byKey(const ValueKey('map-source-badge'))).data,
      contains('غير متاحة'),
    );
  });
}
