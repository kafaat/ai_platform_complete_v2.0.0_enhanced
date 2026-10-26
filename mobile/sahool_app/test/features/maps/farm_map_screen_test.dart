// شاشة «خريطة حقولي» بعميل HTTP مزيّف: محمَّلة، نقر حقل ← بطاقته ← مساحة العمل،
// 503 صادق، فارغة، وحقول بلا حدود تُعدّ صراحةً.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/maps/data/offline_pack_store.dart';
import 'package:sahool_app/features/maps/maps_routes.dart';
import 'package:sahool_app/features/maps/presentation/farm_map_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/fake_http.dart';
import 'map_test_harness.dart';

class _NoPacks extends OfflinePackStore {
  @override
  Future<String?> activePath() async => null;
}

final _square = {
  'type': 'Polygon',
  'coordinates': [
    [
      [44.0, 15.0],
      [44.01, 15.0],
      [44.01, 15.01],
      [44.0, 15.01],
      [44.0, 15.0],
    ],
  ],
};

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<List<String>> pumpScreen(
    WidgetTester t,
    FakeReply reply, {
    bool canAdd = true,
  }) async {
    final pushed = <String>[];
    final adapter = FakeAdapter((_) async => reply);
    final api = FieldsApi(
      testClient(
        adapter,
        MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
      ),
    );
    await t.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        locale: const Locale('ar'),
        supportedLocales: const [Locale('ar')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: FarmMapScreen(
          fieldsApi: api,
          packStore: _NoPacks(),
          canAddField: canAdd,
          tileProviderFactory: MemoryTileProvider.new,
        ),
        onGenerateRoute: (s) {
          pushed.add(s.name!);
          return MaterialPageRoute(builder: (_) => Text('route:${s.name}'));
        },
      ),
    );
    for (var i = 0; i < 8; i++) {
      await t.pump(const Duration(milliseconds: 100));
    }
    return pushed;
  }

  testWidgets('loaded: MultiPolygon field drawn, missing geometry counted', (
    t,
  ) async {
    await pumpScreen(
      t,
      FakeReply(200, [
        summary('f1', multiWithHole, name: 'الحقل الشماليّ'),
        summary('f2', null, name: 'بلا حدود'),
      ]),
    );
    final layer = t.widget<PolygonLayer<String>>(
      find.byType(PolygonLayer<String>),
    );
    expect(layer.polygons, hasLength(2));
    expect(layer.polygons.first.holePointsList, hasLength(1));
    expect(find.textContaining('1 من حقولك بلا حدود مرسومة'), findsOneWidget);
    expect(find.text('جاهز للقرار'), findsOneWidget, reason: 'legend');
  });

  testWidgets('tap a field ⇒ card ⇒ opens the field workspace route', (
    t,
  ) async {
    final pushed = await pumpScreen(
      t,
      FakeReply(200, [summary('f 9', _square, name: 'حقل البنّ')]),
    );
    await t.tapAt(t.getCenter(find.byType(FlutterMap)));
    await t.pump(const Duration(milliseconds: 300));
    expect(find.text('حقل البنّ'), findsOneWidget);
    expect(
      find.text('المساحة: 12.5 هـ'),
      findsOneWidget,
      reason: 'server area_ha, not recomputed',
    );
    await t.tap(find.text('فتح مساحة عمل الحقل'));
    await t.pumpAndSettle();
    expect(pushed, ['/fields/workspace?field_id=f+9']);
  });

  testWidgets('503 shows the honest ApiException message with retry', (
    t,
  ) async {
    await pumpScreen(t, const FakeReply(503, {'detail': 'db down'}));
    expect(
      find.text('الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).'),
      findsOneWidget,
    );
    expect(find.text('إعادة المحاولة'), findsOneWidget);
  });

  testWidgets('empty: no invented fields; add only for editors', (t) async {
    final pushed = await pumpScreen(t, const FakeReply(200, []));
    expect(find.text('لا حقول بعد'), findsOneWidget);
    expect(find.byType(PolygonLayer<String>), findsOneWidget);
    expect(
      t
          .widget<PolygonLayer<String>>(find.byType(PolygonLayer<String>))
          .polygons,
      isEmpty,
    );
    await t.tap(find.text('إضافة حقل'));
    await t.pumpAndSettle();
    expect(pushed, ['/fields/new']);
  });

  testWidgets('viewer sees no add action', (t) async {
    await pumpScreen(t, const FakeReply(200, []), canAdd: false);
    expect(find.text('إضافة حقل'), findsNothing);
  });

  test('routes are registered under the maps feature', () {
    final paths = mapsFeature.routes.map((r) => r.path).toList();
    expect(paths, containsAll(['/maps/farm', '/maps/offline-packs']));
    expect(mapsFeature.routes.every((r) => r.menu != null), isTrue);
  });
}
