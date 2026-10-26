// نموذج التسجيل السريع: التحقّق، الجسم المُرسَل، والإرسال عبر الكاتب.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/activities/data/activity_writer.dart';
import 'package:sahool_app/features/activities/data/field_activity.dart';
import 'package:sahool_app/features/activities/presentation/activity_log_sheet.dart';

import '../../core/fake_http.dart';
import 'activities_fakes.dart';

final now = DateTime(2026, 10, 26, 9);

void main() {
  group('ActivityDraft.validate', () {
    test('type is required and must be a server type', () {
      expect(const ActivityDraft().validate(now)['type'], 'اختر نوع النشاط');
      expect(
        const ActivityDraft(type: 'other').validate(now)['type'],
        isNotNull,
        reason: 'the server rejects unknown types with 422',
      );
      expect(const ActivityDraft(type: 'spraying').validate(now), isEmpty);
    });

    test('title is limited to 200 characters', () {
      final d = ActivityDraft(type: 'irrigation', title: 'أ' * 201);
      expect(d.validate(now)['title'], contains('200'));
      expect(
        ActivityDraft(type: 'irrigation', title: 'أ' * 200).validate(now),
        isEmpty,
      );
    });

    test('done on a date: required and not in the future', () {
      const d = ActivityDraft(type: 'harvest', when: ActivityWhen.onDate);
      expect(d.validate(now)['date'], 'اختر تاريخ التنفيذ');
      expect(
        d.copyWith(date: DateTime(2026, 10, 27)).validate(now)['date'],
        contains('المستقبل'),
      );
      expect(d.copyWith(date: DateTime(2026, 10, 26)).validate(now), isEmpty);
    });

    test('planned: required and not in the past', () {
      const d = ActivityDraft(type: 'harvest', when: ActivityWhen.planned);
      expect(d.validate(now)['date'], 'اختر تاريخ الجدولة');
      expect(
        d.copyWith(date: DateTime(2026, 10, 25)).validate(now)['date'],
        contains('الماضي'),
      );
      expect(d.copyWith(date: DateTime(2026, 11, 2)).validate(now), isEmpty);
    });
  });

  test('toJson sends local calendar dates and only filled fields', () {
    expect(const ActivityDraft(type: 'spraying').toJson(now), {
      'activity_type': 'spraying',
      'performed_on': '2026-10-26',
    });
    expect(
      ActivityDraft(
        type: 'fertilization',
        title: '  يوريا ',
        notes: ' 50 كجم ',
        when: ActivityWhen.planned,
        date: DateTime(2026, 11, 2),
      ).toJson(now),
      {
        'activity_type': 'fertilization',
        'title_ar': 'يوريا',
        'scheduled_for': '2026-11-02',
        'details': {'notes': '50 كجم'},
      },
    );
  });

  group('ActivityWriter', () {
    test(
      'online: POST with an Idempotency-Key, returns the stored row',
      () async {
        final server = FakeActivitiesServer();
        final r = await server.writer().submit('f1', {
          'activity_type': 'spraying',
          'performed_on': '2026-10-26',
        });
        expect(r.isSaved, isTrue);
        expect(r.value!.id, 'act_1');
        final post = server.posts.single;
        expect(post.path, '/api/v1/fields/f1/activities');
        expect(post.headers[kIdempotencyHeader], isNotNull);
      },
    );

    test(
      'offline: queued as activity_complete and listed as pending',
      () async {
        final server = FakeActivitiesServer();
        final outbox = FakeOutbox();
        final pending = PendingActivities();
        final body = {
          'activity_type': 'irrigation',
          'performed_on': '2026-10-26',
        };
        final r = await server
            .writer(outbox: outbox, online: false, pending: pending)
            .submit('f1', body);
        expect(r.isQueued, isTrue);
        expect(server.posts, isEmpty);
        final op = outbox.ops.single;
        expect(op.kind, 'activity_complete');
        expect(op.method, 'POST');
        expect(op.path, '/api/v1/fields/f1/activities');
        expect(op.body, body);
        expect(op.fieldId, 'f1');
        expect(pending.forField('f1').single.pendingSync, isTrue);
        expect(pending.forField('f1').single.type, 'irrigation');

        // ظهوره من الخادم يُسقط النسخة المحلّيّة.
        pending.reconcile('f1', [
          FieldActivity.fromJson({
            'activity_id': 'act_9',
            'field_id': 'f1',
            'activity_type': 'irrigation',
            'performed_on': '2026-10-26',
            'status': 'done',
            'details': {},
          }),
        ]);
        expect(pending.value, isEmpty);
      },
    );

    test('a planned activity is queued as activity_create', () async {
      final outbox = FakeOutbox();
      await FakeActivitiesServer().writer(outbox: outbox, online: false).submit(
        'f1',
        {'activity_type': 'harvest', 'scheduled_for': '2026-11-02'},
      );
      expect(outbox.ops.single.kind, 'activity_create');
    });

    test('offline without a durable outbox: failed, nothing pending', () async {
      final pending = PendingActivities();
      final r = await FakeActivitiesServer()
          .writer(
            outbox: FakeOutbox(accept: false),
            online: false,
            pending: pending,
          )
          .submit('f1', {'activity_type': 'spraying'});
      expect(r.isFailed, isTrue);
      expect(r.messageAr, contains('لم يُحفظ'));
      expect(pending.value, isEmpty);
    });

    test('the key is stable across a retry of the same entry', () async {
      final server = FakeActivitiesServer();
      var fail = true;
      server.postReply = (_) =>
          fail ? const FakeReply(500, {'detail': 'boom'}) : null;
      final writer = server.writer();
      final body = {'activity_type': 'spraying', 'performed_on': '2026-10-26'};
      expect((await writer.submit('f1', body)).isFailed, isTrue);
      fail = false;
      expect((await writer.submit('f1', body)).isSaved, isTrue);
      final keys = server.posts.map((r) => r.headers[kIdempotencyHeader]);
      expect(keys, hasLength(2));
      expect(keys.toSet(), hasLength(1));
      // تسجيل جديد بعد النجاح ⇒ مفتاح جديد (لا يُعاد ردّ التسجيل الأوّل).
      await writer.submit('f1', body);
      expect(server.posts.last.headers[kIdempotencyHeader], isNot(keys.first));
    });
  });

  group('ActivityLogSheet', () {
    Future<FakeActivitiesServer> pumpSheet(
      WidgetTester t, {
      DateTime? picked,
    }) async {
      t.view.physicalSize = const Size(900, 2400);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.reset);
      final server = FakeActivitiesServer();
      await t.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          locale: const Locale('ar'),
          supportedLocales: const [Locale('ar'), Locale('en')],
          localizationsDelegates: GlobalMaterialLocalizations.delegates,
          home: Scaffold(
            body: ActivityLogSheet(
              fieldId: 'f1',
              fieldName: 'حقل الوادي',
              writer: server.writer(),
              clock: () => now,
              popOnDone: false,
              pickDate:
                  (
                    _, {
                    required initial,
                    required first,
                    required last,
                  }) async => picked,
            ),
          ),
        ),
      );
      return server;
    }

    testWidgets('submitting without a type shows an inline error, no POST', (
      t,
    ) async {
      final server = await pumpSheet(t);
      await t.tap(find.text('حفظ النشاط'));
      await t.pump();
      expect(find.text('اختر نوع النشاط'), findsOneWidget);
      expect(server.posts, isEmpty);
    });

    testWidgets('server types only — no "other" chip', (t) async {
      await pumpSheet(t);
      expect(find.text('رشّ'), findsOneWidget);
      expect(find.text('تقليم'), findsOneWidget);
      expect(find.text('أخرى'), findsNothing);
    });

    testWidgets('a long title is rejected inline', (t) async {
      final server = await pumpSheet(t);
      await t.tap(find.widgetWithText(ChoiceChip, 'ريّ'));
      await t.enterText(find.byType(TextFormField).first, 'ع' * 201);
      await t.tap(find.text('حفظ النشاط'));
      await t.pump();
      expect(find.text('العنوان أطول من 200 حرف'), findsOneWidget);
      expect(server.posts, isEmpty);
    });

    testWidgets('a future "done on" date is rejected', (t) async {
      final server = await pumpSheet(t, picked: DateTime(2026, 10, 30));
      await t.tap(find.widgetWithText(ChoiceChip, 'حصاد'));
      await t.tap(find.text('نُفِّذ في يوم آخر'));
      await t.pump();
      await t.tap(find.text('اختر تاريخ التنفيذ'));
      await t.pump();
      await t.tap(find.text('حفظ النشاط'));
      await t.pump();
      expect(find.textContaining('لا يكون في المستقبل'), findsOneWidget);
      expect(server.posts, isEmpty);
    });

    testWidgets('a valid quick log posts once (done today)', (t) async {
      final server = await pumpSheet(t);
      await t.tap(find.widgetWithText(ChoiceChip, 'رشّ'));
      await t.pump();
      await t.tap(find.text('حفظ النشاط'));
      for (var i = 0; i < 5; i++) {
        await t.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 10)),
        );
        await t.pump(const Duration(milliseconds: 50));
      }
      expect(server.posts.single.data, {
        'activity_type': 'spraying',
        'performed_on': '2026-10-26',
      });
    });
  });
}
