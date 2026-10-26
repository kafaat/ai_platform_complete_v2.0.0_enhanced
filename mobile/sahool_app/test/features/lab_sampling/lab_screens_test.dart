// شاشات عيّنات المختبر ضدّ ApiClient حقيقيّ بمحوّل مزيّف.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/lab_sampling/data/lab_sampling_api.dart';
import 'package:sahool_app/features/lab_sampling/presentation/gps_reader.dart';
import 'package:sahool_app/features/lab_sampling/presentation/lab_results_screen.dart';
import 'package:sahool_app/features/lab_sampling/presentation/lab_samples_screen.dart';
import 'package:sahool_app/features/lab_sampling/presentation/protocol_screen.dart';
import 'package:sahool_app/features/lab_sampling/presentation/sample_create_cubit.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../../core/fake_http.dart';
import 'fake_outbox.dart';

Widget host(Widget child) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar'), Locale('en')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: child,
);

void bigScreen(WidgetTester t) {
  t.view.physicalSize = const Size(1080, 3600);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.reset);
}

LabSamplingApi apiFor(FakeAdapter a) => LabSamplingApi(
  testClient(
    a,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  ),
);

final _protocol = {
  'supported': true,
  'depth': {
    'purpose': 'general',
    'depth_ar': '15-30 سم',
    'applies_to_ar': 'احتياجات الأسمدة العامّة',
    'all_purposes_ar': [
      {'purpose': 'general', 'depth_ar': '15-30 سم', 'for_ar': 'عامّ'},
      {'purpose': 'nitrate', 'depth_ar': '30 سم', 'for_ar': 'نترات التربة'},
    ],
  },
  'steps_ar': ['١. خطّط', '٢. جهّز أدوات نظيفة'],
  'avoid_ar': ['لا تأخذ عيّنة والتربة مشبعة بالماء.'],
  'timing_ar': 'قبل التسميد',
  'disclaimer_ar': 'بروتوكول عامّ',
};

FakeAdapter labAdapter({List<Map<String, dynamic>>? samples}) {
  var rows =
      samples ??
      [
        {
          'sample_id': 's-1',
          'field_id': 'f1',
          'kind': 'soil',
          'status': 'sampled',
          'latitude': 15.35421,
          'longitude': 44.20671,
          'sampled_on': '2026-10-20',
          'depth_cm_from': 0,
          'depth_cm_to': '30.00',
          'gps_accuracy_m': 4,
        },
      ];
  return FakeAdapter((o) async {
    switch ((o.method, o.path)) {
      case ('GET', '/api/v1/lab/samples'):
        return FakeReply(200, rows);
      case ('GET', '/api/v1/fields/f1/lab-context'):
        return const FakeReply(200, {
          'soil_lab_ready_for_fertilizer': false,
          'water_lab_available': false,
          'blockers_ar': [],
          'warnings_ar': ['لا توجد نتيجة تربة مخبرية', 'لا يوجد تحليل ماء ري'],
          'recommendation_gate': 'needs_review',
        });
      case ('POST', '/api/v1/lab/samples/s-1/transition'):
        rows = [
          {...rows.first, 'status': (o.data as Map)['target_status']},
        ];
        return FakeReply(200, rows.first);
      case ('GET', '/api/v1/soil-sampling/protocol'):
        return FakeReply(200, _protocol);
      case ('GET', '/api/v1/fields/f1/soil-lab-tests'):
        return const FakeReply(200, [
          {
            'test_id': 'soil_1',
            'field_id': 'f1',
            'status': 'published',
            'lab_name': 'مختبر صنعاء',
            'sampled_on': '2026-05-03',
            'result': {'ph': 7.9, 'texture': 'طينيّة'},
          },
        ]);
    }
    return const FakeReply(404, {'detail': 'nf'});
  });
}

void main() {
  testWidgets('samples list: status, Arabic date, depth, context warnings', (
    t,
  ) async {
    bigScreen(t);
    await t.pumpWidget(
      host(
        LabSamplesScreen(
          fieldId: 'f1',
          fieldName: 'حقل البنّ',
          api: apiFor(labAdapter()),
          role: 'owner',
          outbox: FakeOutbox(),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('عيّنات حقل البنّ'), findsOneWidget);
    expect(find.text('جُمعت'), findsOneWidget);
    expect(find.text('20 أكتوبر 2026'), findsOneWidget);
    expect(find.text('0–30 سم'), findsOneWidget);
    expect(find.text('± 4 م'), findsOneWidget);
    expect(find.text('لا توجد نتيجة تربة مخبرية'), findsOneWidget);
    expect(find.text('التربة غير جاهزة لقرار التسميد'), findsOneWidget);
  });

  testWidgets(
    'sending to the lab posts the transition and updates the status',
    (t) async {
      bigScreen(t);
      final a = labAdapter();
      await t.pumpWidget(
        host(
          LabSamplesScreen(
            fieldId: 'f1',
            api: apiFor(a),
            role: 'manager',
            outbox: FakeOutbox(),
          ),
        ),
      );
      await t.pumpAndSettle();
      await t.tap(find.text('أُرسلت للمختبر'));
      await t.pumpAndSettle();
      final post = a.to('/api/v1/lab/samples/s-1/transition').single;
      expect(post.data, {'target_status': 'in_lab'});
      expect(post.headers['Idempotency-Key'], isNotEmpty);
      expect(find.text('في المختبر'), findsOneWidget);
      expect(find.text('بانتظار نتيجة المختبر'), findsOneWidget);
      expect(find.text('أُرسلت للمختبر'), findsNothing);
    },
  );

  testWidgets('cancelling asks for confirmation; dismiss sends nothing', (
    t,
  ) async {
    bigScreen(t);
    final a = labAdapter();
    await t.pumpWidget(
      host(
        LabSamplesScreen(
          fieldId: 'f1',
          api: apiFor(a),
          role: 'owner',
          outbox: FakeOutbox(),
        ),
      ),
    );
    await t.pumpAndSettle();
    await t.tap(find.text('إلغاء العيّنة'));
    await t.pumpAndSettle();
    expect(
      find.text('إلغاء العيّنة نهائيّ ولا يمكن التراجع عنه.'),
      findsOneWidget,
    );
    await t.tap(find.text('إلغاء')); // زرّ الإلغاء في الحوار
    await t.pumpAndSettle();
    expect(a.to('/api/v1/lab/samples/s-1/transition'), isEmpty);
  });

  testWidgets(
    'viewer and worker see no write actions (server needs field:edit)',
    (t) async {
      bigScreen(t);
      for (final role in ['viewer', 'worker']) {
        await t.pumpWidget(
          host(
            LabSamplesScreen(
              key: ValueKey(role),
              fieldId: 'f1',
              api: apiFor(labAdapter()),
              role: role,
              outbox: FakeOutbox(),
            ),
          ),
        );
        await t.pumpAndSettle();
        expect(find.text('أُرسلت للمختبر'), findsNothing, reason: role);
        expect(find.text('عيّنة جديدة'), findsNothing, reason: role);
      }
    },
  );

  testWidgets('offline capture: GPS + protocol depth chip → queued receipt', (
    t,
  ) async {
    bigScreen(t);
    final a = labAdapter(samples: []);
    final outbox = FakeOutbox();
    await t.pumpWidget(
      host(
        LabSamplesScreen(
          fieldId: 'f1',
          fieldName: 'حقل البنّ',
          api: apiFor(a),
          role: 'owner',
          outbox: outbox,
          isOnline: () => false,
          gpsReader: () async =>
              const GpsFix(15.354212, 44.206711, accuracyM: 35),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('لا عيّنات بعد'), findsOneWidget);
    await t.tap(find.text('عيّنة جديدة').first);
    await t.pumpAndSettle();

    await t.tap(find.text('التقاط موقع العيّنة (GPS)'));
    await t.pumpAndSettle();
    expect(find.text('15.354212'), findsOneWidget);
    expect(find.textContaining('دقّة الموقع: ± 35 م — منخفضة'), findsOneWidget);

    await t.tap(find.text('العمق الموصى به 15–30 سم'));
    await t.pumpAndSettle();
    await t.tap(find.text('حفظ العيّنة'));
    await t.pumpAndSettle();

    expect(
      find.text('حُفظت العيّنة على الجهاز وستُرسَل عند عودة الاتّصال'),
      findsOneWidget,
    );
    expect(a.requests.where((r) => r.method == 'POST'), isEmpty);
    final op = outbox.ops.single;
    expect(op.body['latitude'], 15.354212);
    expect(op.body['gps_accuracy_m'], 35.0);
    expect(op.body['depth_cm_from'], 15);
    expect(op.body['depth_cm_to'], 30);
    expect(find.text('1 عمليّة بانتظار الإرسال'), findsOneWidget);
  });

  testWidgets('offline with no durable queue keeps the form and says so', (
    t,
  ) async {
    bigScreen(t);
    await t.pumpWidget(
      host(
        LabSamplesScreen(
          fieldId: 'f1',
          api: apiFor(labAdapter(samples: [])),
          role: 'owner',
          outbox: FakeOutbox(
            receipt: const OutboxReceipt.notQueued('offline_queue_unavailable'),
          ),
          isOnline: () => false,
          gpsReader: () async => const GpsFix(15.35, 44.2, accuracyM: 3),
        ),
      ),
    );
    await t.pumpAndSettle();
    await t.tap(find.text('عيّنة جديدة').first);
    await t.pumpAndSettle();
    await t.tap(find.text('التقاط موقع العيّنة (GPS)'));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const ValueKey('sample_depth_from')), '٠');
    await t.enterText(find.byKey(const ValueKey('sample_depth_to')), '٢٠');
    await t.tap(find.text('حفظ العيّنة'));
    await t.pumpAndSettle();
    expect(
      find.text(notQueuedMessage('offline_queue_unavailable')),
      findsOneWidget,
    );
    expect(find.text('حفظ العيّنة'), findsOneWidget); // ما زلنا في النموذج
  });

  testWidgets('GPS permission failure is shown, not a fake point', (t) async {
    bigScreen(t);
    await t.pumpWidget(
      host(
        LabSamplesScreen(
          fieldId: 'f1',
          api: apiFor(labAdapter(samples: [])),
          role: 'owner',
          outbox: FakeOutbox(),
          gpsReader: () async => throw const GpsFailure(
            'إذن الموقع مرفوض — تعذّر التقاط موقع العيّنة.',
          ),
        ),
      ),
    );
    await t.pumpAndSettle();
    await t.tap(find.text('عيّنة جديدة').first);
    await t.pumpAndSettle();
    await t.tap(find.text('التقاط موقع العيّنة (GPS)'));
    await t.pumpAndSettle();
    expect(
      find.text('إذن الموقع مرفوض — تعذّر التقاط موقع العيّنة.'),
      findsOneWidget,
    );
    await t.tap(find.text('حفظ العيّنة'));
    await t.pumpAndSettle();
    expect(
      find.text('التقط موقع العيّنة بالـGPS أو أدخل الإحداثيّات'),
      findsOneWidget,
    );
  });

  testWidgets(
    'results show stored values as-is and say units are not provided',
    (t) async {
      bigScreen(t);
      await t.pumpWidget(
        host(LabResultsScreen(fieldId: 'f1', api: apiFor(labAdapter()))),
      );
      await t.pumpAndSettle();
      expect(find.text('مختبر صنعاء'), findsOneWidget);
      expect(find.text('منشورة'), findsOneWidget);
      expect(find.text('تاريخ العيّنة: 3 مايو 2026'), findsOneWidget);
      expect(find.text('7.9'), findsOneWidget);
      expect(find.text('طينيّة'), findsOneWidget);
      expect(find.text(kUnitsNotProvided), findsOneWidget);
    },
  );

  testWidgets('protocol guidance renders the server steps', (t) async {
    bigScreen(t);
    final a = labAdapter();
    await t.pumpWidget(host(ProtocolScreen(areaHa: 3, api: apiFor(a))));
    await t.pumpAndSettle();
    expect(find.text('١. خطّط'), findsOneWidget);
    expect(find.text('لا تأخذ عيّنة والتربة مشبعة بالماء.'), findsOneWidget);
    expect(find.text('15-30 سم'), findsOneWidget);
    expect(a.requests.first.path, '/api/v1/soil-sampling/protocol');
  });
}
