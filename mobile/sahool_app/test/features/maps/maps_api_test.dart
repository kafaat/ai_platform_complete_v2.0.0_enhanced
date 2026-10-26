// عقد روابط بلاطات خدمة الراستر ومصادقتها وتوفّر التضاريس، وسجلّ خرائط الأساس.
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/maps/data/basemaps.dart';
import 'package:sahool_app/features/maps/data/maps_api.dart';
import 'package:sahool_app/features/maps/geo/geo_json.dart';

import '../../core/fake_http.dart';

void main() {
  final geom = FieldGeometry.polygon(const [
    LatLng(15.0, 44.0),
    LatLng(15.0, 44.01),
    LatLng(15.01, 44.01),
    LatLng(15.01, 44.0),
  ]);

  MapsApi api(FakeAdapter a, {String? token}) =>
      MapsApi(testClient(a, MemoryTokenStore(accessToken: token)));

  group('indicatorTileUrl (web contract: indicatorTileUrl.ts)', () {
    final a = FakeAdapter((_) async => const FakeReply(200, {}));

    test('live CDSE path clips with poly + bbox and omits date=latest', () {
      final url = api(a).indicatorTileUrl(
        fieldId: 'f 1',
        index: 'ndvi',
        date: 'latest',
        geometry: geom,
      );
      expect(
        url,
        startsWith(
          'https://api.test.invalid/api/raster/v1/fields/f%201/'
          'cdse-tiles/{z}/{x}/{y}.png?',
        ),
      );
      final q = Uri.parse(url.replaceAll(RegExp(r'[{}]'), '')).queryParameters;
      expect(q['index'], 'ndvi');
      expect(q.containsKey('date'), isFalse);
      expect(q['bbox_w'], '44.0');
      expect(q['bbox_e'], '44.01');
      expect(q['bbox_s'], '15.0');
      expect(q['bbox_n'], '15.01');
      expect(q['poly'], '44.0,15.0;44.01,15.0;44.01,15.01;44.0,15.01');
    });

    test('persisted COG path carries the date and no clip', () {
      final url = api(a).indicatorTileUrl(
        fieldId: 'f1',
        index: 'ndmi',
        date: '2026-10-01',
        geometry: geom,
        preferPersistedCog: true,
      );
      expect(url, contains('/v1/fields/f1/tiles/{z}/{x}/{y}.png?'));
      expect(url, contains('date=2026-10-01'));
      expect(url, isNot(contains('poly=')));
    });

    test('never puts the JWT in the URL', () {
      final url = api(
        a,
        token: fakeJwt(const Duration(hours: 1)),
      ).indicatorTileUrl(fieldId: 'f1', geometry: geom);
      expect(url, isNot(contains('access_token')));
      expect(url, isNot(contains('tenant_id')));
    });
  });

  test('tileHeaders sends a Bearer token; none without a session', () async {
    final a = FakeAdapter((_) async => const FakeReply(200, {}));
    final tok = fakeJwt(const Duration(hours: 1));
    expect(await api(a, token: tok).tileHeaders(), {
      'Authorization': 'Bearer $tok',
    });
    expect(await api(a).tileHeaders(), isEmpty);
  });

  test('terrainTileJson reads availability from the raster service', () async {
    final a = FakeAdapter(
      (o) async => const FakeReply(200, {
        'available': false,
        'user_message': 'لا نموذج ارتفاع مُهيّأ',
        'minzoom': 8,
        'maxzoom': 17,
      }),
    );
    final t = await api(
      a,
      token: fakeJwt(const Duration(hours: 1)),
    ).terrainTileJson();
    expect(t.available, isFalse);
    expect(t.userMessage, 'لا نموذج ارتفاع مُهيّأ');
    final r = a.requests.single;
    expect(r.path, '/api/raster/v1/terrain/tilejson');
    expect(r.headers['Authorization'], startsWith('Bearer '));
  });

  test('terrainTileJson surfaces 503 as a typed ApiException', () async {
    final a = FakeAdapter((_) async => const FakeReply(503, {'detail': 'x'}));
    expect(
      api(a, token: fakeJwt(const Duration(hours: 1))).terrainTileJson(),
      throwsA(
        isA<ApiException>().having(
          (e) => e.kind,
          'kind',
          ApiErrorKind.unavailable,
        ),
      ),
    );
  });

  group('basemap registry (web layerRegistry.ts)', () {
    test('every basemap has an attribution, a max zoom and {z}/{x}/{y}', () {
      for (final b in Basemaps.all) {
        expect(b.attribution.trim(), isNotEmpty, reason: b.id);
        expect(b.maxZoom, greaterThan(0));
        expect(b.urlTemplate, contains('{z}'));
        expect(b.urlTemplate, contains('{x}'));
        expect(b.urlTemplate, contains('{y}'));
      }
    });

    test('satellite and streets match the web URLs and attributions', () {
      expect(
        Basemaps.satellite.urlTemplate,
        'https://server.arcgisonline.com/ArcGIS/rest/services/'
        'World_Imagery/MapServer/tile/{z}/{y}/{x}',
      );
      expect(Basemaps.satellite.attribution, contains('Esri'));
      expect(
        Basemaps.streets.urlTemplate,
        'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
      );
      expect(Basemaps.streets.attribution, contains('OpenStreetMap'));
      expect(Basemaps.streets.attribution, contains('CARTO'));
      expect(Basemaps.streets.subdomains, isNotEmpty);
    });

    test('token basemaps are hidden when no key is compiled in', () {
      // الاختبارات تُبنى بلا --dart-define للمفاتيح.
      expect(Basemaps.available.map((b) => b.id), ['satellite', 'light']);
      expect(Basemaps.byId('mapbox-satellite').id, 'satellite');
    });

    test('attributionForUrl names the provider of an arbitrary URL', () {
      expect(
        Basemaps.attributionForUrl(Basemaps.satellite.urlTemplate),
        Basemaps.satellite.attribution,
      );
      expect(
        Basemaps.attributionForUrl('https://tiles.example.org/{z}/{x}/{y}'),
        '© tiles.example.org',
      );
    });
  });
}
