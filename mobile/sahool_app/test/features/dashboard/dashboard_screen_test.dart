// شاشة «اليوم» على الحمولة الحقيقيّة: أرقام مقيسة، «غير مقيس» للغائب (لا null
// أبداً)، لا فيض على 360dp بمقياس نصّ 1.3، ولقطة دون اتّصال بعمرها.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/alerts/data/alerts_api.dart';
import 'package:sahool_app/features/alerts/data/alerts_unread.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_snapshot_store.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/screens/dashboard_screen.dart';

import '../../core/fake_http.dart';
import 'today_fixtures.dart';

Future<void> pumpToday(
  WidgetTester tester,
  TodayHarness h, {
  double width = 1080,
  double height = 4000,
  double textScale = 1,
  String role = 'owner',
  bool Function(String path)? routeExists,
  AlertsUnreadCounter? alertsCounter,
  OfflineOutbox? syncOutbox,
  List<String>? opened,
}) async {
  tester.view.physicalSize = Size(width, height);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light,
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      onGenerateRoute: (settings) {
        opened?.add(settings.name!);
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => const Scaffold(body: Text('target')),
        );
      },
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(
          context,
        ).copyWith(textScaler: TextScaler.linear(textScale)),
        child: child!,
      ),
      home: Scaffold(
        body: DashboardScreen(
          createCubit: h.cubit,
          clock: () => kNow,
          role: role,
          userName: 'أحمد',
          routeExists: routeExists ?? (_) => false,
          alertsCounter: alertsCounter,
          syncOutbox: syncOutbox,
        ),
      ),
    ),
  );
  await settle(tester);
}

/// الطلبات المتتابعة (اللوحة ← المزرعة ← الطقس) تحتاج عدّة دورات.
Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 20; i++) {
    await tester.pump(const Duration(milliseconds: 20));
  }
  await tester.pumpAndSettle();
}

List<String> allTexts(WidgetTester tester) => tester
    .widgetList<Text>(find.byType(Text))
    .map((t) => t.data ?? t.textSpan?.toPlainText() ?? '')
    .toList();

void expectNoNullOrFakes(WidgetTester tester) {
  for (final t in allTexts(tester)) {
    expect(t.contains('null'), isFalse, reason: 'null rendered: $t');
    expect(t.contains('صحة جيدة'), isFalse, reason: 'hard-coded health: $t');
    expect(t.contains('صنعاء'), isFalse, reason: 'hard-coded place: $t');
    expect(t.contains('هكتار'), isFalse, reason: 'legacy unit: $t');
  }
}

class _PendingOutbox implements OfflineOutbox {
  _PendingOutbox(this.count);
  final int count;
  @override
  Future<OutboxReceipt> enqueue(OutboxOp op) => throw UnimplementedError();
  @override
  Stream<int> get pendingCount => Stream<int>.value(count);
}

void main() {
  testWidgets('header embeds the alerts bell and the pending-sync badge; '
      'an alert opens its detail route', (tester) async {
    final adapter = fakeBackend(
      overrides: {
        '/api/v1/alerts': () => const FakeReply(200, [
          {'alert_id': 'a1', 'status': 'active', 'title_ar': 'صقيع'},
          {'alert_id': 'a2', 'status': 'active', 'title_ar': 'رياح'},
        ]),
      },
    );
    final h = TodayHarness(adapter);
    final client = testClient(
      adapter,
      MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
    );
    final opened = <String>[];
    await pumpToday(
      tester,
      h,
      routeExists: (_) => true,
      alertsCounter: AlertsUnreadCounter(
        api: AlertsApi(client),
        events: const Stream.empty(),
      ),
      syncOutbox: _PendingOutbox(2),
      opened: opened,
    );
    expect(tester.takeException(), isNull);
    expect(find.byTooltip('التنبيهات'), findsOneWidget);
    expect(find.byKey(const ValueKey('pending-sync-badge')), findsOneWidget);
    expect(find.byTooltip('المزامنة: 2 بانتظار الإرسال'), findsOneWidget);
    final bell = find.byTooltip('التنبيهات');
    expect(find.descendant(of: bell, matching: find.text('2')), findsOneWidget);
    await tester.tap(find.text('فتح').first);
    await tester.pumpAndSettle();
    expect(opened.single, startsWith('/alerts/detail?alert_id='));
  });

  testWidgets('no bell or sync badge when those routes are not registered', (
    tester,
  ) async {
    await pumpToday(tester, TodayHarness(fakeBackend()));
    expect(find.byTooltip('التنبيهات'), findsNothing);
    expect(find.byKey(const ValueKey('pending-sync-badge')), findsNothing);
  });

  testWidgets('real producer payload renders measured numbers', (tester) async {
    final h = TodayHarness(fakeBackend());
    await pumpToday(tester, h);
    expect(tester.takeException(), isNull);

    expect(find.text('صباح الخير، أحمد'), findsOneWidget);
    // KPIs من kpis[] لا من fields_count/total_area_ha.
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('kpi-area_total')),
        matching: find.text('12.8'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('kpi-fields_total')),
        matching: find.text('3'),
      ),
      findsOneWidget,
    );
    // التنبيهات: title_ar، الأشدّ أوّلاً، مع اسم الحقل.
    expect(find.text('خطر صقيع الليلة'), findsOneWidget);
    expect(find.text('رطوبة التربة منخفضة'), findsOneWidget);
    expect(find.text('حرج'), findsOneWidget);
    // المهامّ: المتأخّرة واليوم فقط.
    expect(find.text('كشف ميدانيّ'), findsOneWidget);
    expect(find.text('ريّ'), findsOneWidget);
    expect(find.text('حصاد'), findsNothing);
    expect(find.text('متأخّرة'), findsOneWidget);
    // الطقس من field-weather-summary لمركز المزرعة.
    expect(find.text('الطقس الآن — مزرعة الوادي'), findsOneWidget);
    expect(find.text('24 °م'), findsOneWidget);
    expect(find.text('الرشّ: مناسب'), findsOneWidget);
    // الحقول بالأولويّة: الحرج أوّلاً، والمساحة 0 «غير مقيس».
    final f2 = tester.getTopLeft(find.byKey(const ValueKey('field-f2'))).dy;
    final f1 = tester.getTopLeft(find.byKey(const ValueKey('field-f1'))).dy;
    expect(f2, lessThan(f1));
    expect(find.text('محصول غير محدّد · غير مقيس'), findsOneWidget);
    expect(find.text('آخر تحديث: الآن'), findsOneWidget);
    expect(find.text('مزرعة الوادي'), findsOneWidget); // اختيار المزرعة
    expectNoNullOrFakes(tester);
  });

  testWidgets('missing keys render "غير مقيس", never null', (tester) async {
    final h = TodayHarness(
      fakeBackend(
        overrides: {
          '/api/v1/indicators/dashboard': () => const FakeReply(200, {
            'fields_summary': [
              {'field_id': 'f9'},
            ],
          }),
          '/api/v1/farms': () => const FakeReply(200, <dynamic>[]),
          '/api/v1/tasks': () => const FakeReply(200, {'tasks': <dynamic>[]}),
        },
      ),
    );
    await pumpToday(tester, h);
    expect(tester.takeException(), isNull);
    for (final id in [
      'fields_total',
      'area_total',
      'active_seasons',
      'open_alerts',
    ]) {
      expect(
        find.descendant(
          of: find.byKey(ValueKey('kpi-$id')),
          matching: find.text('غير مقيس'),
        ),
        findsOneWidget,
        reason: id,
      );
    }
    expect(find.text('لا تنبيهات نشطة الآن.'), findsOneWidget);
    expect(find.text('لا مهامّ مستحقّة اليوم.'), findsOneWidget);
    expect(find.textContaining('الطقس غير متاح'), findsOneWidget);
    expect(find.text('حقل بلا اسم'), findsOneWidget);
    expectNoNullOrFakes(tester);
  });

  testWidgets('no overflow at 360dp with textScale 1.3', (tester) async {
    final h = TodayHarness(fakeBackend());
    await pumpToday(tester, h, width: 360, height: 760, textScale: 1.3);
    expect(tester.takeException(), isNull);
    final list = find.byKey(const ValueKey('today-list'));
    for (var i = 0; i < 40; i++) {
      await tester.drag(list, const Offset(0, -300));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'overflow at step $i');
    }
    expect(find.byKey(const ValueKey('today-not-measured')), findsOneWidget);
  });

  testWidgets('viewer has no acknowledge action', (tester) async {
    final h = TodayHarness(fakeBackend());
    await pumpToday(tester, h, role: 'viewer');
    expect(find.text('خطر صقيع الليلة'), findsOneWidget);
    expect(find.byKey(const ValueKey('ack-alr_frost')), findsNothing);
  });

  testWidgets('a worker acknowledges an alert once', (tester) async {
    // الخادم المزيّف يُسقط التنبيه المُقَرّ من اللوحة كما يفعل الحقيقيّ
    // (status='acknowledged' لا يُعاد في alerts النشطة).
    var acked = false;
    final h2 = TodayHarness(
      fakeBackend(
        overrides: {
          '/api/v1/alerts/alr_frost/acknowledge': () {
            acked = true;
            return const FakeReply(200, {});
          },
          '/api/v1/indicators/dashboard': () {
            final d = realDashboard();
            if (acked) {
              (d['alerts'] as List).removeWhere(
                (a) => (a as Map)['alert_id'] == 'alr_frost',
              );
            }
            return FakeReply(200, d);
          },
        },
      ),
    );
    await pumpToday(tester, h2, role: 'worker');
    await tester.tap(find.byKey(const ValueKey('ack-alr_frost')));
    await settle(tester);
    expect(h2.adapter.to('/api/v1/alerts/alr_frost/acknowledge'), hasLength(1));
    expect(find.text('سُجِّل الاطّلاع على التنبيه'), findsOneWidget);
    expect(find.text('خطر صقيع الليلة'), findsNothing);
  });

  testWidgets('offline: cached snapshot with its last-updated time', (
    tester,
  ) async {
    final store = MemoryDashboardSnapshotStore();
    final savedAt = kNow.subtract(const Duration(hours: 3));
    await store.write('dashboard:tenant:user', {
      'dashboard': realDashboard(),
      'tasks': realTasks()['tasks'],
      'farms': realFarms(),
    }, savedAt);
    final h = TodayHarness(
      fakeBackend(
        overrides: {
          for (final p in [
            '/api/v1/indicators/dashboard',
            '/api/v1/tasks',
            '/api/v1/farms',
            '/api/v1/farms/farm1/fields',
            '/api/v1/farms/farm1/priority-queue',
            '/api/v1/weather/field-weather-summary',
          ])
            p: offline,
        },
      ),
      snapshots: store,
    );
    await pumpToday(tester, h);
    expect(tester.takeException(), isNull);
    expect(find.byKey(const ValueKey('today-stale-banner')), findsOneWidget);
    expect(find.text('تعرض آخر نسخة محفوظة على الجهاز'), findsOneWidget);
    expect(find.text('آخر تحديث: منذ 3 ساعة'), findsOneWidget);
    expect(find.text('خطر صقيع الليلة'), findsOneWidget);
    expect(find.text('كشف ميدانيّ'), findsOneWidget);
    // لا إقرار على لقطة قديمة.
    expect(find.byKey(const ValueKey('ack-alr_frost')), findsNothing);
    expectNoNullOrFakes(tester);
  });

  testWidgets('first load failure shows the typed error, not raw text', (
    tester,
  ) async {
    final h = TodayHarness(
      fakeBackend(
        overrides: {
          '/api/v1/indicators/dashboard': () =>
              const FakeReply(503, {'detail': 'db down'}),
        },
      ),
    );
    await pumpToday(tester, h);
    expect(find.text('تعذّر تحميل اليوم'), findsOneWidget);
    expect(find.text('إعادة المحاولة'), findsOneWidget);
    expect(find.textContaining('DioException'), findsNothing);
  });
}
