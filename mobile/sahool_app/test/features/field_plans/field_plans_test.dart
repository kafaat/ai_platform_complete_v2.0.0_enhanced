// خطط الحقل (الوصفة وخطّة العيّنات): النقاط الحقيقيّة، والفتح البارد دون اتّصال
// الذي يعرض آخر نسخة محفوظة مع عمرها — ضدّ ApiClient حقيقيّ بمحوّل مزيّف وكاش
// مشفَّر حقيقيّ فوق مخزن ذاكرة يبقى بين «تشغيلين».
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/offline/cache_backends.dart';
import 'package:sahool_app/core/offline/cached_loader.dart';
import 'package:sahool_app/core/offline/offline_read_cache.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/field_plans/data/field_plans_api.dart';
import 'package:sahool_app/features/field_plans/data/field_plans_repository.dart';
import 'package:sahool_app/features/field_plans/presentation/field_plan_screens.dart';

import '../../core/fake_http.dart';

const tenantA = CacheScope(tenantId: 'tenant-a', userId: 'u1');
const tenantB = CacheScope(tenantId: 'tenant-b', userId: 'u1');

final fetchedAt = DateTime(2026, 11, 16, 6, 0);
final threeHoursLater = fetchedAt.add(const Duration(hours: 3));

const fieldsBody = [
  {'field_id': 'f1', 'name': 'حقل الوادي', 'crop': 'wheat'},
];

const recipesBody = {
  'field_id': 'f1',
  'total': 1,
  'prescriptions': [
    {
      'prescription_id': 'rx1',
      'field_id': 'f1',
      'name': 'يوريا الربيع',
      'product_type': 'fertility',
      'zones': [
        {'geometry': null, 'rate': 120, 'unit': 'kg/ha'},
        {'geometry': null, 'rate': 80, 'unit': 'kg/ha'},
      ],
      'created_by': 'u1',
      'created_at': '2026-11-01T08:00:00+00:00',
    },
  ],
};

const fieldDetailBody = {
  'field_id': 'f1',
  'name': 'حقل الوادي',
  'geometry': {
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
  },
};

const scanPlanBody = {
  'type': 'FeatureCollection',
  'computed': true,
  'field_id': 'f1',
  'features': [
    {
      'type': 'Feature',
      'geometry': {
        'type': 'Point',
        'coordinates': [44.005, 15.005],
      },
      'properties': {
        'point_id': 'soil_A1',
        'zone_id': 'A',
        'depth_cm': '0-30',
        'tests': ['pH', 'EC'],
        'reason_ar': 'منطقة A — طينيّة',
      },
    },
  ],
};

FakeAdapter onlineAdapter() => FakeAdapter((o) async {
      switch (o.path) {
        case '/api/v1/fields':
          return const FakeReply(200, fieldsBody);
        case '/api/v1/fields/f1/prescriptions':
          return const FakeReply(200, recipesBody);
        case '/api/v1/fields/f1':
          return const FakeReply(200, fieldDetailBody);
        case '/api/raster/v1/fields/f1/soil/sampling-plan':
          return const FakeReply(200, scanPlanBody);
      }
      return const FakeReply(404, {'detail': 'not found'});
    });

FakeAdapter offlineAdapter() =>
    FakeAdapter((_) async => const FakeReply.fail(
          DioExceptionType.connectionError,
        ));

/// «جهاز» واحد: مخزن ومفاتيح يبقيان بين تشغيلين، ونطاق جلسة قابل للتبديل.
class Device {
  final store = MemoryRawCacheStore();
  final vault = MemoryCacheKeyVault();
  CacheScope? scope = tenantA;

  /// تشغيل جديد للتطبيق: كاش وعميل جديدان فوق التخزين نفسه.
  FieldPlansRepository launch(FakeAdapter adapter, {DateTime? clock}) {
    final cache = OfflineReadCache(store: store, vault: vault);
    return FieldPlansRepository(
      api: FieldPlansApi(
        testClient(
          adapter,
          MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
        ),
      ),
      loader: CachedLoader(
        cache: cache,
        scope: () => scope,
        clock: () => clock ?? fetchedAt,
      ),
    );
  }
}

Widget host(Widget child) => MaterialApp(
      theme: AppTheme.light,
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: child,
    );

void main() {
  group('endpoints', () {
    test('recipes read GET /api/v1/fields/{id}/prescriptions', () async {
      final a = onlineAdapter();
      final r = await Device().launch(a).recipes('f1');
      expect(a.requests.single.method, 'GET');
      expect(a.requests.single.path, '/api/v1/fields/f1/prescriptions');
      expect(r.data.recipes.single.name, 'يوريا الربيع');
      expect(r.data.recipes.single.zones.first.rate, 120);
      expect(r.fromCache, isFalse);
    });

    test('scan plan reads the field boundary, then the raster sampling plan '
        'clipped to it', () async {
      final a = onlineAdapter();
      final r = await Device().launch(a).scanPlan('f1');
      expect(a.requests.map((q) => q.path), [
        '/api/v1/fields/f1',
        '/api/raster/v1/fields/f1/soil/sampling-plan',
      ]);
      final q = a.requests.last;
      expect(q.method, 'GET');
      final uri = Uri.parse('https://x.invalid${q.path}');
      expect(uri.path, '/api/raster/v1/fields/f1/soil/sampling-plan');
      expect(r.data.points.single.pointId, 'soil_A1');
    });

    test('scan plan query carries bbox and poly from the polygon', () async {
      Map<String, dynamic>? query;
      final online = onlineAdapter();
      final a = FakeAdapter((o) {
        if (o.path.endsWith('/sampling-plan')) query = o.queryParameters;
        return online.handler(o);
      });
      await Device().launch(a).scanPlan('f1');
      expect(query?['bbox'], '44.0,15.0,44.01,15.01');
      expect(query?['poly'], startsWith('44.0,15.0;44.01,15.0;'));
      expect(query?['zones'], '3');
      expect(query?['samples_per_zone'], '1');
    });

    test('no boundary: the plan is requested unclipped (server says why)',
        () async {
      Map<String, dynamic>? query;
      final a = FakeAdapter((o) async {
        if (o.path == '/api/v1/fields/f1') {
          return const FakeReply(200, {'field_id': 'f1', 'geometry': null});
        }
        query = o.queryParameters;
        return const FakeReply(200, {
          'type': 'FeatureCollection',
          'features': [],
          'computed': false,
          'source': 'no_bbox',
        });
      });
      final r = await Device().launch(a).scanPlan('f1');
      expect(query?.containsKey('bbox'), isFalse);
      expect(r.data.computed, isFalse);
      expect(r.data.points, isEmpty);
      expect(r.data.source, 'no_bbox');
    });
  });

  group('offline cold start', () {
    test('returns the last saved recipe with its fetch time', () async {
      final device = Device();
      await device.launch(onlineAdapter()).recipes('f1');

      final offline = device.launch(offlineAdapter(), clock: threeHoursLater);
      final r = await offline.recipes('f1');
      expect(r.fromCache, isTrue);
      expect(r.fetchedAt, fetchedAt, reason: 'the fetch time, not now');
      expect(r.age(threeHoursLater), const Duration(hours: 3));
      expect(r.refreshError?.kind, ApiErrorKind.network);
      expect(r.data.recipes.single.name, 'يوريا الربيع');
    });

    test('nothing saved: fails honestly, never an empty list', () async {
      final offline = Device().launch(offlineAdapter());
      await expectLater(
        offline.recipes('f1'),
        throwsA(isA<ApiException>()
            .having((e) => e.kind, 'kind', ApiErrorKind.network)),
      );
    });

    test('403 is shown as 403, not as the saved copy', () async {
      final device = Device();
      await device.launch(onlineAdapter()).recipes('f1');
      final forbidden = device.launch(
        FakeAdapter((_) async => const FakeReply(403, {'detail': 'no'})),
      );
      await expectLater(
        forbidden.recipes('f1'),
        throwsA(isA<ApiException>()
            .having((e) => e.kind, 'kind', ApiErrorKind.forbidden)),
      );
    });

    test("another tenant on the same device does not get the first tenant's "
        'saved recipe', () async {
      final device = Device();
      await device.launch(onlineAdapter()).recipes('f1');
      device.scope = tenantB;
      await expectLater(
        device.launch(offlineAdapter()).recipes('f1'),
        throwsA(isA<ApiException>()),
      );
      device.scope = tenantA;
      await expectLater(
        device.launch(offlineAdapter()).recipes('f1'),
        throwsA(isA<ApiException>()),
        reason: 'the tenant switch wiped the earlier copy',
      );
    });

    test('no session tenant: nothing is written', () async {
      final device = Device()..scope = null;
      await device.launch(onlineAdapter()).recipes('f1');
      expect(device.store.entries, isEmpty);
      expect(device.vault.keys, isEmpty);
    });
  });

  group('screens', () {
    testWidgets('recipe screen, offline cold start: last state with its age',
        (t) async {
      final device = Device();
      await t.runAsync(() => device.launch(onlineAdapter()).recipes('f1'));

      final repo = device.launch(offlineAdapter(), clock: threeHoursLater);
      await t.pumpWidget(host(RecipeScreen(
        fieldId: 'f1',
        repository: repo,
        now: threeHoursLater,
      )));
      await t.runAsync(() => Future<void>.delayed(
            const Duration(milliseconds: 50),
          ));
      await t.pumpAndSettle();

      expect(find.text('يوريا الربيع'), findsOneWidget);
      expect(find.textContaining('120'), findsOneWidget);
      final banner = find.byType(DataAgeBanner);
      expect(banner, findsOneWidget);
      final age = DataAgeBanner.ageText(fetchedAt, now: threeHoursLater);
      expect(age, contains(fmtAge(fetchedAt, now: threeHoursLater)));
      expect(age, contains('منذ 3 ساعة'));
      expect(find.textContaining(age), findsOneWidget);
      expect(find.textContaining('غير متّصل'), findsOneWidget);
      expect(find.byType(ErrorState), findsNothing);
      expect(find.byType(EmptyState), findsNothing);
    });

    testWidgets('scan plan screen, offline cold start: points with their age',
        (t) async {
      final device = Device();
      await t.runAsync(() => device.launch(onlineAdapter()).scanPlan('f1'));

      final repo = device.launch(offlineAdapter(), clock: threeHoursLater);
      await t.pumpWidget(host(ScanPlanScreen(
        fieldId: 'f1',
        repository: repo,
        now: threeHoursLater,
      )));
      await t.runAsync(() => Future<void>.delayed(
            const Duration(milliseconds: 50),
          ));
      await t.pumpAndSettle();

      expect(find.text('soil_A1'), findsOneWidget);
      expect(find.textContaining('منطقة A — طينيّة'), findsOneWidget);
      expect(find.textContaining('منذ 3 ساعة'), findsOneWidget);
      expect(find.textContaining('غير متّصل'), findsOneWidget);
    });

    testWidgets('fresh data shows its age without the offline warning',
        (t) async {
      final repo = Device().launch(onlineAdapter());
      await t.pumpWidget(host(RecipeScreen(
        fieldId: 'f1',
        repository: repo,
        now: fetchedAt.add(const Duration(minutes: 5)),
      )));
      await t.runAsync(() => Future<void>.delayed(
            const Duration(milliseconds: 50),
          ));
      await t.pumpAndSettle();
      expect(find.textContaining('عمر البيانات: منذ 5 دقيقة'), findsOneWidget);
      expect(find.textContaining('غير متّصل'), findsNothing);
    });

    testWidgets('offline with nothing saved shows the network error',
        (t) async {
      final repo = Device().launch(offlineAdapter());
      await t.pumpWidget(host(RecipeScreen(fieldId: 'f1', repository: repo)));
      await t.runAsync(() => Future<void>.delayed(
            const Duration(milliseconds: 50),
          ));
      await t.pumpAndSettle();
      expect(find.byType(ErrorState), findsOneWidget);
      expect(find.byType(DataAgeBanner), findsNothing);
      expect(find.text('يوريا الربيع'), findsNothing);
    });

    testWidgets('offline field chooser uses the saved field list', (t) async {
      final device = Device();
      await t.runAsync(() async {
        final online = device.launch(onlineAdapter());
        await online.fields();
        await online.recipes('f1');
      });
      final repo = device.launch(offlineAdapter(), clock: threeHoursLater);
      await t.pumpWidget(host(RecipeScreen(
        repository: repo,
        now: threeHoursLater,
      )));
      await t.runAsync(() => Future<void>.delayed(
            const Duration(milliseconds: 50),
          ));
      await t.pumpAndSettle();
      expect(find.text('حقل الوادي'), findsOneWidget);
      await t.tap(find.text('حقل الوادي'));
      await t.runAsync(() => Future<void>.delayed(
            const Duration(milliseconds: 50),
          ));
      await t.pumpAndSettle();
      expect(find.text('يوريا الربيع'), findsOneWidget);
      expect(find.textContaining('منذ 3 ساعة'), findsOneWidget);
    });
  });
}
