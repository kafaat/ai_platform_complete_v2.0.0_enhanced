/// Exercise the real dashboard (DashboardScreen + DashboardCubit + DashboardApi
/// on the real ApiClient) against a fake server routed by path. The producer's
/// payload has no carbon; carbon must render as "غير مقيس", never a number —
/// even if a carbon-looking key ever shows up in the payload.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_api.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_snapshot_store.dart';
import 'package:sahool_app/features/dashboard/presentation/dashboard_cubit.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/tasks/data/tasks_api.dart';
import 'package:sahool_app/screens/dashboard_screen.dart';
import 'package:sahool_app/widgets/carbon_not_measured_card.dart';

import 'core/fake_http.dart';

/// The producer's real shape (analytics_shapers.py `_shape_indicators_dashboard`).
Map<String, dynamic> producerPayload() => {
  'kpis': <dynamic>[],
  'alerts': <dynamic>[],
  'fields_summary': [
    {'field_id': 'f1', 'field_name': 'حقل', 'area_ha': 1.5},
  ],
  'note_ar': 'عدّادات حيّة',
};

FakeAdapter backend(Map<String, dynamic> dashboard) => FakeAdapter(
  (o) async => switch (o.path) {
    '/api/v1/indicators/dashboard' => FakeReply(200, dashboard),
    '/api/v1/tasks' => const FakeReply(200, {'tasks': <dynamic>[]}),
    '/api/v1/farms' => const FakeReply(200, <dynamic>[]),
    _ => const FakeReply(404, {'detail': 'not found'}),
  },
);

Future<FakeAdapter> pumpDashboard(
  WidgetTester tester,
  Map<String, dynamic> dashboard,
) async {
  tester.view.physicalSize = const Size(1200, 6000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final adapter = backend(dashboard);
  final client = testClient(
    adapter,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  );
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light,
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: Scaffold(
        body: DashboardScreen(
          createCubit: () => DashboardCubit(
            api: DashboardApi(client, ResponseCache(), 'tenant:user'),
            tasksApi: TasksApi(client),
            farmsApi: FarmsApi(client),
            snapshots: MemoryDashboardSnapshotStore(),
          ),
          clock: () => DateTime(2026, 10, 26, 9),
          role: 'owner',
          userName: 'أحمد',
          routeExists: (_) => false,
        ),
      ),
    ),
  );
  for (var i = 0; i < 20; i++) {
    await tester.pump(const Duration(milliseconds: 20));
  }
  await tester.pumpAndSettle();
  return adapter;
}

void expectCarbonNotMeasured(WidgetTester tester) {
  expect(find.text('الكربون غير مقيس'), findsOneWidget);
  final card = find.byType(CarbonNotMeasuredCard);
  expect(card, findsOneWidget);
  final texts = tester
      .widgetList<Text>(find.descendant(of: card, matching: find.byType(Text)))
      .map((t) => t.data ?? '')
      .toList();
  expect(texts, contains(kCarbonNotMeasuredValue));
  expect(texts, contains('الكربون المخزّن'));
  for (final text in texts) {
    expect(text.contains('null'), isFalse);
    expect(text.contains('كجم'), isFalse);
    expect(text.contains(r'$'), isFalse);
    expect(RegExp(r'[\d٠-٩]').hasMatch(text), isFalse, reason: text);
  }
}

void main() {
  testWidgets('producer payload without carbon: carbon is not measured', (
    tester,
  ) async {
    final adapter = await pumpDashboard(tester, producerPayload());
    expect(tester.takeException(), isNull);
    // The real dashboard read happened (the screen is not an empty shell).
    expect(adapter.to('/api/v1/indicators/dashboard'), isNotEmpty);
    expect(find.text('صباح الخير، أحمد'), findsOneWidget);
    expectCarbonNotMeasured(tester);
  });

  testWidgets('a carbon-looking key in the payload is never shown', (
    tester,
  ) async {
    await pumpDashboard(tester, {
      ...producerPayload(),
      'carbon': {'sequestered_kg': 98765, 'credit_value_usd': 4321},
    });
    expect(tester.takeException(), isNull);
    expectCarbonNotMeasured(tester);
    final all = tester
        .widgetList<Text>(find.byType(Text))
        .map((t) => t.data ?? t.textSpan?.toPlainText() ?? '');
    for (final t in all) {
      expect(t.contains('98765') || t.contains('98,765'), isFalse);
      expect(t.contains('4321') || t.contains('4,321'), isFalse);
    }
  });

  test('dashboard never reads unproduced carbon payload values', () {
    final source = File('lib/screens/dashboard_screen.dart')
        .readAsLinesSync()
        .map((line) => line.replaceAll(RegExp(r'//.*$'), ''))
        .join('\n');
    for (final key in ["'carbon'", "'sequestered_kg'", "'credit_value_usd'"]) {
      expect(source.contains(key), isFalse, reason: 'unproduced key: $key');
    }
    expect(source.contains('CarbonNotMeasuredCard()'), isTrue);
  });
}
