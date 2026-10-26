// أنشطة الحقل وخطّه الزمنيّ (توقيت محلّيّ، حالة متدهورة صادقة) وموجز المزرعة.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/features/activities/data/activity_writer.dart';
import 'package:sahool_app/features/activities/data/field_activity.dart';
import 'package:sahool_app/features/activities/presentation/activity_labels.dart';
import 'package:sahool_app/features/activities/presentation/farm_activity_feed_screen.dart';
import 'package:sahool_app/features/activities/presentation/farm_feed_cubit.dart';
import 'package:sahool_app/features/activities/presentation/field_activities_cubit.dart';
import 'package:sahool_app/features/activities/presentation/field_activities_screen.dart';

import '../../core/fake_http.dart';
import 'activities_fakes.dart';

Widget app(Widget home) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar'), Locale('en')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: home,
);

void tall(WidgetTester t) {
  t.view.physicalSize = const Size(900, 2400);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.reset);
}

void main() {
  test('timeline timestamps are converted from UTC to local time', () {
    const raw = '2026-10-26T09:05:00+00:00';
    final e = TimelineEvent.fromJson({
      'timestamp': raw,
      'event_type': 'operation.irrigation.completed',
      'category': 'operation',
      'summary_ar': 'ريّ',
    });
    expect(e.at!.isUtc, isFalse);
    expect(e.at, DateTime.parse(raw).toLocal());
    expect(timelineTimeLabel(e), fmtDateTime(DateTime.parse(raw).toLocal()));
    final local = DateTime.parse(raw).toLocal();
    expect(
      timelineTimeLabel(e),
      endsWith(
        '${local.hour.toString().padLeft(2, '0')}:'
        '${local.minute.toString().padLeft(2, '0')}',
      ),
    );
    final bad = TimelineEvent.fromJson({'timestamp': 'غير صالح'});
    expect(timelineTimeLabel(bad), 'غير صالح');
  });

  testWidgets('field screen: log list + pending, timeline in local time', (
    t,
  ) async {
    tall(t);
    final server = FakeActivitiesServer();
    server.activities['f1'] = [
      activityJson('a1', title: 'مبيد فطريّ', notes: 'بعد المطر'),
    ];
    server.timeline = {
      'events': [
        {
          'timestamp': '2026-10-25T06:30:00+00:00',
          'event_type': 'operation.irrigation.completed',
          'category': 'operation',
          'summary_ar': 'اكتمل الريّ',
        },
        {
          'timestamp': '2026-10-24T10:00:00+00:00',
          'event_type': 'scouting.pin.created',
          'category': 'observation',
          'summary_ar': 'مشاهدة آفة',
        },
      ],
      'category_counts': {'operation': 1, 'observation': 1},
      'degraded': false,
    };
    final pending = PendingActivities()
      ..add(
        FieldActivity.pending('local:1', 'f1', {
          'activity_type': 'irrigation',
          'performed_on': '2026-10-26',
        }, DateTime(2026, 10, 26)),
      );
    final cubit = FieldActivitiesCubit('f1', api: server.api, pending: pending);
    await t.runAsync(cubit.load);
    await t.pumpWidget(
      app(
        FieldActivitiesScreen(
          fieldId: 'f1',
          fieldName: 'حقل الوادي',
          cubit: cubit,
          role: 'worker',
          pending: pending,
        ),
      ),
    );
    await t.pump();
    expect(find.text('رشّ — مبيد فطريّ'), findsOneWidget);
    expect(find.text('بعد المطر'), findsOneWidget);
    expect(find.text('بانتظار المزامنة'), findsOneWidget);
    expect(find.text('تسجيل نشاط'), findsOneWidget);

    await t.tap(find.text('الخطّ الزمنيّ'));
    await t.pumpAndSettle();
    final local = fmtDateTime(DateTime.parse('2026-10-25T06:30:00Z').toLocal());
    expect(find.text('عمليّات · $local'), findsOneWidget);
    await t.tap(find.text('مشاهدات (1)'));
    await t.pump();
    expect(find.text('اكتمل الريّ'), findsNothing);
    expect(find.text('مشاهدة آفة'), findsOneWidget);
  });

  testWidgets('degraded timeline says unavailable, not "no events"', (t) async {
    tall(t);
    final server = FakeActivitiesServer();
    server.timeline = {
      'events': [],
      'total_events': 0,
      'degraded': true,
      'note_ar': 'القاعدة غير مفعّلة (DATABASE_URL) — لا تاريخ حيّ',
    };
    final cubit = FieldActivitiesCubit(
      'f1',
      api: server.api,
      pending: PendingActivities(),
    );
    await t.runAsync(cubit.load);
    await t.pumpWidget(
      app(FieldActivitiesScreen(fieldId: 'f1', cubit: cubit, role: 'viewer')),
    );
    await t.pump();
    expect(find.text('تسجيل نشاط'), findsNothing, reason: 'viewer');
    await t.tap(find.text('الخطّ الزمنيّ'));
    await t.pumpAndSettle();
    expect(find.text('الخطّ الزمنيّ غير متاح الآن'), findsOneWidget);
    expect(find.text('لا أحداث بعد'), findsNothing);
  });

  testWidgets(
    'farm feed merges fields newest first and flags partial failure',
    (t) async {
      tall(t);
      final server = FakeActivitiesServer();
      server.fields = [
        {'field_id': 'f1', 'name': 'حقل الوادي'},
        {'field_id': 'f2', 'name': 'حقل البنّ'},
        {'field_id': 'f3', 'name': 'حقل الجبل'},
      ];
      server.activities['f1'] = [
        activityJson('a1', type: 'irrigation', performed: '2026-10-20'),
      ];
      server.activities['f2'] = [
        activityJson(
          'a2',
          field: 'f2',
          type: 'harvest',
          performed: '2026-10-24',
        ),
      ];
      server.failFieldList['f3'] = const FakeReply(503, {'detail': 'db'});
      final cubit = FarmFeedCubit(
        api: server.api,
        fieldsApi: server.fieldsApi,
        pending: PendingActivities(),
      );
      await t.runAsync(cubit.load);
      expect(cubit.state.items.map((a) => a.id), ['a2', 'a1']);
      expect(cubit.state.failedFields, 1);

      await t.pumpWidget(
        app(
          FarmActivityFeedScreen(
            cubit: cubit,
            role: 'worker',
            pending: PendingActivities(),
          ),
        ),
      );
      await t.pump();
      expect(
        find.textContaining('تعذّر تحميل أنشطة 1 من 3 حقل'),
        findsOneWidget,
      );
      expect(find.text('حقل البنّ'), findsOneWidget);
      await t.tap(find.text(activityTypeAr('irrigation')).first);
      await t.pump();
      expect(find.text('حقل البنّ'), findsNothing);
      expect(find.text('حقل الوادي'), findsOneWidget);
    },
  );

  testWidgets('farm feed with no fields is honest', (t) async {
    final server = FakeActivitiesServer()..fields = [];
    final cubit = FarmFeedCubit(
      api: server.api,
      fieldsApi: server.fieldsApi,
      pending: PendingActivities(),
    );
    await t.runAsync(cubit.load);
    await t.pumpWidget(
      app(FarmActivityFeedScreen(cubit: cubit, role: 'owner')),
    );
    await t.pump();
    expect(find.text('لا حقول بعد'), findsOneWidget);
    expect(find.byType(FloatingActionButton), findsNothing);
  });
}
