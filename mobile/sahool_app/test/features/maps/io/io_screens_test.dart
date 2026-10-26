// شاشات io/: معاينة الاستيراد واختياره، وضع الالتقاط، مشي GPS، التصدير، والدمج
// والتقسيم (بما فيه معاينة مُطفأة في الخادم ⇒ لا حفظ).
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/maps/io/data/maps_io_api.dart';
import 'package:sahool_app/features/maps/io/geo/boundary_writer.dart';
import 'package:sahool_app/features/maps/io/maps_io_routes.dart';
import 'package:sahool_app/features/maps/io/presentation/export_screen.dart';
import 'package:sahool_app/features/maps/io/presentation/field_ops_screens.dart';
import 'package:sahool_app/features/maps/io/presentation/gps_walk_screen.dart';
import 'package:sahool_app/features/maps/io/presentation/import_screen.dart';

import '../../../core/fake_http.dart';
import 'fixtures.dart';
import 'gps_walk_test.dart' show FakeLocation, fix;

Widget app(Widget home) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar'), Locale('en')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: home,
);

/// يفتح [screen] فوق شاشة أساس ويعيد نتيجة pop.
Widget launcher(Widget screen, void Function(Object?) onResult) => app(
  Builder(
    builder: (context) => Scaffold(
      body: Center(
        child: TextButton(
          onPressed: () async {
            final r = await Navigator.of(
              context,
            ).push<Object?>(MaterialPageRoute(builder: (_) => screen));
            onResult(r);
          },
          child: const Text('افتح'),
        ),
      ),
    ),
  ),
);

MapsIoApi apiWith(FakeAdapter a) => MapsIoApi(
  testClient(
    a,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  ),
);

Map<String, dynamic> fieldRow(
  String id,
  String name,
  List<List<double>> ring,
) => {
  'field_id': id,
  'name': name,
  'area_ha': 1.19,
  'farm_id': 'farm_1',
  'geometry': {
    'type': 'Polygon',
    'coordinates': [ring],
  },
};

void tallScreen(WidgetTester t) {
  t.view.physicalSize = const Size(800, 2400);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.reset);
}

void main() {
  testWidgets('import: paste → map preview → choose → one POST per polygon', (
    t,
  ) async {
    tallScreen(t);
    final adapter = FakeAdapter(
      (_) async => const FakeReply(201, {'field_id': 'fld'}),
    );
    await t.pumpWidget(
      app(ImportScreen(api: apiWith(adapter), showBasemap: false)),
    );
    await t.enterText(
      find.byKey(const Key('import-text')),
      featureCollection(),
    );
    await t.tap(find.text('معاينة على الخريطة'));
    await t.pumpAndSettle();

    expect(find.byType(FlutterMap), findsOneWidget);
    expect(find.textContaining('وُجد 3 مضلّع'), findsOneWidget);
    expect(
      find.textContaining('Point'),
      findsOneWidget,
    ); // skipped part announced
    expect(find.textContaining('ثقباً'), findsOneWidget); // hole drop announced

    await t.tap(find.byType(Checkbox).at(2)); // deselect the 3rd polygon
    await t.pump();
    await t.tap(find.text('استيراد 2 حقل'));
    await t.pumpAndSettle();
    expect(adapter.to('/api/v1/fields/import'), hasLength(2));
    expect(find.text('تمّ الاستيراد'), findsOneWidget);
  });

  testWidgets('import: a parse error is shown inline, nothing is sent', (
    t,
  ) async {
    final adapter = FakeAdapter((_) async => const FakeReply(201, {}));
    await t.pumpWidget(
      app(ImportScreen(api: apiWith(adapter), showBasemap: false)),
    );
    await t.enterText(
      find.byKey(const Key('import-text')),
      '{"type":"Polygon"',
    );
    await t.tap(find.text('معاينة على الخريطة'));
    await t.pumpAndSettle();
    expect(find.textContaining('GeoJSON غير صالح'), findsOneWidget);
    expect(adapter.requests, isEmpty);
  });

  testWidgets('import pick mode returns one GeoJSON polygon, no server write', (
    t,
  ) async {
    tallScreen(t);
    final adapter = FakeAdapter((_) async => const FakeReply(201, {}));
    Object? result;
    await t.pumpWidget(
      launcher(
        ImportScreen(api: apiWith(adapter), pickMode: true, showBasemap: false),
        (r) => result = r,
      ),
    );
    await t.tap(find.text('افتح'));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const Key('import-text')), kmlDoc());
    await t.tap(find.text('معاينة على الخريطة'));
    await t.pumpAndSettle();
    await t.tap(find.text('استخدم هذا المضلّع').first);
    await t.pumpAndSettle();
    expect(result, isA<Map<String, dynamic>>());
    final m = result! as Map<String, dynamic>;
    expect(m['type'], 'Polygon');
    expect((m['coordinates'] as List).single, hasLength(5)); // closed, no hole
    expect(adapter.requests, isEmpty);
  });

  testWidgets(
    'gps walk: live metrics, rejected fixes counted, viewer cannot save',
    (t) async {
      tallScreen(t);
      final loc = FakeLocation();
      final adapter = FakeAdapter((_) async => const FakeReply(201, {}));
      await t.pumpWidget(
        app(
          GpsWalkScreen(
            api: apiWith(adapter),
            source: loc,
            canSave: false,
            showBasemap: false,
          ),
        ),
      );
      expect(
        find.text('غير مقيس'),
        findsWidgets,
      ); // no fake numbers before data
      await t.tap(find.text('ابدأ المشي'));
      await t.pump();
      loc
        ..emit(fix(15.3500, 44.2000))
        ..emit(fix(15.3500, 44.2010, sec: 60))
        ..emit(fix(15.3510, 44.2010, acc: 40, sec: 70))
        ..emit(fix(15.3510, 44.2010, sec: 120));
      await t.pump();
      expect(find.text('رُفضت: الدقّة أضعف من الحدّ'), findsNothing);
      expect(find.text('قراءة مقبولة'), findsOneWidget);
      await t.tap(find.text('إنهاء وإغلاق الحدّ'));
      await t.pump();
      expect(find.textContaining('للمالك والمدير فقط'), findsOneWidget);
      expect(find.text('حفظ كحقل'), findsNothing);
      expect(adapter.requests, isEmpty);
    },
  );

  testWidgets('gps walk: manager saves with format=gps', (t) async {
    tallScreen(t);
    final loc = FakeLocation();
    final adapter = FakeAdapter(
      (_) async => const FakeReply(201, {'field_id': 'fld_gps'}),
    );
    await t.pumpWidget(
      app(
        GpsWalkScreen(
          api: apiWith(adapter),
          source: loc,
          canSave: true,
          showBasemap: false,
        ),
      ),
    );
    await t.tap(find.text('ابدأ المشي'));
    await t.pump();
    loc
      ..emit(fix(15.3500, 44.2000))
      ..emit(fix(15.3500, 44.2010, sec: 60))
      ..emit(fix(15.3510, 44.2010, sec: 120))
      ..emit(fix(15.3510, 44.2000, sec: 180));
    await t.pump();
    await t.tap(find.text('إنهاء وإغلاق الحدّ'));
    await t.pump();
    await t.tap(find.text('حفظ كحقل'));
    await t.pump();
    expect(find.text('اسم الحقل مطلوب'), findsOneWidget);
    await t.enterText(find.byType(TextFormField), 'حقل المشي');
    await t.tap(find.text('حفظ كحقل'));
    await t.pumpAndSettle();
    final body = adapter.requests.single.data as Map;
    expect(body['format'], 'gps');
    expect(body['points'], hasLength(4));
    expect(adapter.requests.single.headers['Idempotency-Key'], isNotNull);
    expect(find.text('أُنشئ الحقل من مسار المشي'), findsOneWidget);
  });

  testWidgets(
    'export: shares a KML of the chosen field; no-geometry field listed',
    (t) async {
      tallScreen(t);
      final adapter = FakeAdapter(
        (_) async => FakeReply(200, [
          fieldRow('f1', 'حقل البنّ', square),
          {'field_id': 'f2', 'name': 'بلا حدود', 'geometry': null},
        ]),
      );
      ExportFile? shared;
      await t.pumpWidget(
        app(
          ExportScreen(api: apiWith(adapter), share: (f) async => shared = f),
        ),
      );
      await t.pumpAndSettle();
      expect(find.textContaining('بلا حدود محفوظة'), findsOneWidget);
      await t.tap(find.text('KML'));
      await t.pumpAndSettle();
      expect(shared!.fileName, 'حقل_البنّ.kml');
      expect(shared!.content, contains('<name>حقل البنّ</name>'));
    },
  );

  testWidgets('export: 503 shows the honest outage message', (t) async {
    final adapter = FakeAdapter(
      (_) async => const FakeReply(503, {'detail': 'db'}),
    );
    await t.pumpWidget(
      app(ExportScreen(api: apiWith(adapter), share: (_) async {})),
    );
    await t.pumpAndSettle();
    expect(find.textContaining('الخدمة غير متاحة'), findsOneWidget);
  });

  testWidgets('merge: preview disabled on the server ⇒ explained, no save', (
    t,
  ) async {
    tallScreen(t);
    final adapter = FakeAdapter(
      (o) async => o.path == '/api/v1/fields'
          ? FakeReply(200, [
              fieldRow('a', 'أ', square),
              fieldRow('b', 'ب', square2),
            ])
          : const FakeReply(404, {'detail': 'نواة GIS غير مُفعَّلة'}),
    );
    await t.pumpWidget(
      app(MergeFieldsScreen(api: apiWith(adapter), showBasemap: false)),
    );
    await t.pumpAndSettle();
    await t.tap(find.text('أ').last);
    await t.tap(find.text('ب').last);
    await t.pump();
    await t.tap(find.text('معاينة الدمج'));
    await t.pumpAndSettle();
    expect(find.textContaining('FEATURE_GIS_KERNEL'), findsOneWidget);
    expect(find.text('دمج وحفظ'), findsNothing);
    expect(adapter.to('/api/v1/fields/merge'), isEmpty);
  });

  testWidgets(
    'merge: server preview → confirm → atomic merge with that geometry',
    (t) async {
      tallScreen(t);
      final union = {
        'type': 'Polygon',
        'coordinates': [square],
      };
      final adapter = FakeAdapter(
        (o) async => switch (o.path) {
          '/api/v1/fields' => FakeReply(200, [
            fieldRow('a', 'أ', square),
            fieldRow('b', 'ب', square2),
          ]),
          '/api/v1/gis/union' => FakeReply(200, {
            'operation': 'union',
            'dry_run': true,
            'result': union,
          }),
          _ => const FakeReply(201, {'field_id': 'm'}),
        },
      );
      await t.pumpWidget(
        app(MergeFieldsScreen(api: apiWith(adapter), showBasemap: false)),
      );
      await t.pumpAndSettle();
      await t.tap(find.text('أ').last);
      await t.tap(find.text('ب').last);
      await t.pump();
      await t.tap(find.text('معاينة الدمج'));
      await t.pumpAndSettle();
      await t.enterText(find.byType(TextFormField), 'المدموج');
      await t.tap(find.text('دمج وحفظ'));
      await t.pumpAndSettle();
      expect(find.text('دمج الحقلين؟'), findsOneWidget); // destructive confirm
      await t.tap(find.text('دمج'));
      await t.pumpAndSettle();
      final req = adapter.to('/api/v1/fields/merge').single;
      expect((req.data as Map)['geometry'], union);
      expect((req.data as Map)['source_field_ids'], ['a', 'b']);
      expect((req.data as Map)['farm_id'], 'farm_1');
      expect(req.headers['Idempotency-Key'], isNotNull);
    },
  );

  testWidgets('split: blade drawn on the map → server parts → named children', (
    t,
  ) async {
    tallScreen(t);
    final partA = {
      'type': 'Polygon',
      'coordinates': [
        [
          [44.2, 15.35],
          [44.2005, 15.35],
          [44.2005, 15.351],
          [44.2, 15.351],
          [44.2, 15.35],
        ],
      ],
    };
    final partB = {
      'type': 'Polygon',
      'coordinates': [
        [
          [44.2005, 15.35],
          [44.201, 15.35],
          [44.201, 15.351],
          [44.2005, 15.351],
          [44.2005, 15.35],
        ],
      ],
    };
    final adapter = FakeAdapter(
      (o) async => switch (o.path) {
        '/api/v1/fields' => FakeReply(200, [fieldRow('a', 'أ', square)]),
        '/api/v1/gis/split' => FakeReply(200, {
          'part_count': 2,
          'result': {
            'type': 'GeometryCollection',
            'geometries': [partA, partB],
          },
        }),
        _ => const FakeReply(201, [
          {'field_id': 'c1'},
          {'field_id': 'c2'},
        ]),
      },
    );
    await t.pumpWidget(
      app(
        SplitFieldScreen(
          api: apiWith(adapter),
          fieldId: 'a',
          showBasemap: false,
        ),
      ),
    );
    await t.pumpAndSettle();
    final map = t.getRect(find.byType(FlutterMap));
    await t.tapAt(map.topCenter + const Offset(0, 10));
    await t.pump(const Duration(milliseconds: 400));
    await t.tapAt(map.bottomCenter - const Offset(0, 10));
    await t.pump(const Duration(milliseconds: 400));
    expect(find.textContaining('(2 نقطة)'), findsOneWidget);
    await t.tap(find.text('معاينة التقسيم'));
    await t.pumpAndSettle();
    final blade =
        (adapter.to('/api/v1/gis/split').single.data as Map)['blade'] as Map;
    expect(blade['type'], 'LineString');
    expect(blade['coordinates'], hasLength(2));
    expect(find.text('اسم الجزء 2'), findsOneWidget);
    await t.tap(find.text('تقسيم وحفظ'));
    await t.pumpAndSettle();
    await t.tap(find.text('تقسيم'));
    await t.pumpAndSettle();
    final req = adapter.to('/api/v1/fields/split').single.data as Map;
    expect(req['source_field_id'], 'a');
    expect((req['children'] as List).map((c) => c['name']), ['أ — 1', 'أ — 2']);
    expect((req['children'] as List).first['geometry'], partA);
  });

  test('routes: unique /maps/ paths; writes need owner/manager', () {
    final paths = mapsIoRoutes.map((r) => r.path).toList();
    expect(paths.toSet(), hasLength(paths.length));
    expect(paths.every((p) => p.startsWith('/maps/')), isTrue);
    AppRoute r(String p) => mapsIoRoutes.firstWhere((x) => x.path == p);
    for (final p in [
      MapsIoRoutes.import,
      MapsIoRoutes.merge,
      MapsIoRoutes.split,
    ]) {
      expect(r(p).allowedRoles, RouteRoles.management, reason: p);
    }
    expect(r(MapsIoRoutes.export).allowedRoles, isNull);
  });

  test('io routes are registered in the app router under the maps feature', () {
    for (final route in mapsIoRoutes) {
      expect(
        AppRouter.instance.match(route.path),
        same(route),
        reason: route.path,
      );
      expect(AppRouter.instance.ownerOf(route.path), 'maps');
    }
  });
}
