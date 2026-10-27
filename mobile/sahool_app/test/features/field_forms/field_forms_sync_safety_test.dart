// أمان تصريف طابور النماذج الميدانيّة عبر حدود الجلسة والأعطال المؤقّتة
// (تدقيق UI-S1/UI-S2/UI-S3):
//   • انتهاء الجلسة أثناء التصريف يوقف الحلقة قبل العنصر التالي — لا يُرسَل عنصرٌ
//     التقطته جلسةٌ سابقة تحت جلسةٍ لاحقة.
//   • صفّ طابور لا يُفكّ لا يُسقط القائمة كلّها ولا يختفي: يُعَدّ ويُعرَض.
//   • 408/425/429 مؤقّتة لا تصير «لم يُقبل»، والتصريف يُعاد بمؤقّت (Retry-After أو
//     backoff) ما دام متّصلاً — لا ينتظر تغيّر الشبكة.
import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:sahool_app/features/field_forms/data/field_forms_api.dart';
import 'package:sahool_app/features/field_forms/data/field_forms_coordinator.dart';
import 'package:sahool_app/features/field_forms/data/submission_queue.dart';
import 'package:sahool_app/features/field_forms/data/submission_sender.dart';

import '../../core/fake_http.dart';
import 'ff_fixtures.dart';

Dio _dio(FakeAdapter adapter) =>
    Dio(BaseOptions(baseUrl: 'https://api.example.test'))
      ..httpClientAdapter = adapter;

class _Timer implements Timer {
  _Timer(this.delay, this.callback);
  final Duration delay;
  final void Function() callback;
  bool _active = true;
  @override
  void cancel() => _active = false;
  @override
  bool get isActive => _active;
  @override
  int get tick => 0;
  void fire() {
    if (!_active) return;
    _active = false;
    callback();
  }
}

void main() {
  late Directory dir;
  late SubmissionQueue queue;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('ff_sync_safety');
    Hive.init(dir.path);
    queue = SubmissionQueue(await Hive.openBox<dynamic>('q'));
  });

  tearDown(() async {
    await Hive.close();
    await dir.delete(recursive: true);
  });

  Future<QueuedSubmission> enqueue(String actor, String assignment) async {
    final item = await queue.enqueue(
      tenantId: 't',
      fieldId: 'f',
      assignmentId: assignment,
      assignmentRevision: 1,
      formVersionId: 'v',
      schemaHash: 'h',
      answers: {'a': assignment},
      server: 'https://api.example.test',
      actorId: actor,
    );
    // ترتيب FIFO بالوقت المحلّيّ.
    await Future<void>.delayed(const Duration(milliseconds: 2));
    return item;
  }

  Future<void> until(bool Function() cond) async {
    for (var i = 0; i < 200 && !cond(); i++) {
      await Future<void>.delayed(const Duration(milliseconds: 5));
    }
    expect(cond(), isTrue);
  }

  group('UI-S1 — حدّ الجلسة', () {
    test('انتهاء الجلسة أثناء إرسالٍ جارٍ يوقف الحلقة قبل العنصر التالي '
        'فلا يُرسَل عنصر الجلسة السابقة تحت الجلسة الجديدة', () async {
      final first = await enqueue('alice', 'a1');
      final second = await enqueue('alice', 'a2');
      final gate = Completer<void>();
      final adapter = FakeAdapter((_) async {
        await gate.future;
        return const FakeReply(201, kAccepted);
      });
      var actor = 'alice';
      final c = FieldFormsCoordinator(
        queue: queue,
        api: FieldFormsApi(_dio(adapter)),
        currentTenantId: () => 't',
        currentActorId: () => actor,
      );
      final run = c.drain();
      await until(() => adapter.requests.length == 1);
      // خروج alice ثمّ دخول bob في المستأجِر نفسه بينما الطلب الأوّل جارٍ.
      await c.onSessionEnd();
      actor = 'bob';
      gate.complete();
      await run;
      expect(
        adapter.requests,
        hasLength(1),
        reason: 'العنصر الثاني التقطته جلسة alice — لا يُرسَل بعد انتهائها',
      );
      // D3: الطلب الجاري أُلغي بنهاية الجلسة — الإلغاء لا يثبت أنّ الخادم لم
      // ينفّذه، فلا يُحذف: يبقى «نتيجته غير مؤكَّدة» ويُطابَق حين تعود alice.
      expect(queue.pending(tenantId: 't').map((i) => i.instanceId), [
        first.instanceId,
        second.instanceId,
      ]);
      final rows = queue.pending(tenantId: 't').map((i) => i.toJson()).toList();
      expect(rows.first['outcome_unknown'], isTrue);
      expect(rows.last['outcome_unknown'], isFalse);
    });

    test(
      'تصريفٌ طلبته الجلسة الجديدة أثناء إنهاء الحلقة القديمة لا يضيع',
      () async {
        await enqueue('alice', 'a1');
        final second = await enqueue('alice', 'a2');
        final gate = Completer<void>();
        final adapter = FakeAdapter((_) async {
          await gate.future;
          return const FakeReply(201, kAccepted);
        });
        final api = FieldFormsApi(_dio(adapter));
        final c = FieldFormsCoordinator(
          queue: queue,
          api: api,
          currentTenantId: () => 't',
          currentActorId: () => 'alice',
        );
        final run = c.drain();
        await until(() => adapter.requests.length == 1);
        await c.onSessionEnd();
        // alice تعود فوراً: الجلسة الجديدة تطلب تصريفاً والحلقة القديمة لم تنتهِ.
        c.api = api;
        expect(await c.drain(), 0);
        gate.complete();
        await run;
        await until(() => adapter.requests.length == 2);
        await until(() => queue.pending(tenantId: 't').isEmpty);
        await until(() => !SubmissionSender.isInFlight(second.instanceId));
      },
    );
  });

  group('UI-S2 — صفّ لا يُفكّ', () {
    test(
      'صفّ تالف لا يُسقط القائمة ولا يختفي: يُعَدّ ويبقى على القرص',
      () async {
        final ok = await enqueue('alice', 'a1');
        final box = Hive.box<dynamic>('q');
        await box.put('broken-map', {'instance_id': 'x'}); // حقول ناقصة
        await box.put('broken-scalar', 'not a map');
        expect(queue.pending(tenantId: 't').map((i) => i.instanceId), [
          ok.instanceId,
        ]);
        expect(queue.failed(tenantId: 't'), isEmpty);
        expect(queue.unreadableCount(), 2);
        expect(box.containsKey('broken-map'), isTrue);
        expect(box.containsKey('broken-scalar'), isTrue);
      },
    );
  });

  group('UI-S3 — أعطال مؤقّتة', () {
    for (final status in [408, 425, 429]) {
      test(
        '$status بعد بلوغ حدّ المحاولات يبقى مؤقّتاً لا «لم يُقبل»',
        () async {
          var item = await enqueue('alice', 'a1');
          for (var i = 0; i < SubmissionSender.maxRejectedAttempts; i++) {
            item = await queue.markRetry(item);
          }
          final adapter = FakeAdapter(
            (_) async => FakeReply(status, const {'detail': 'slow down'}),
          );
          final outcome = await SubmissionSender.send(
            item: item,
            queue: queue,
            api: FieldFormsApi(_dio(adapter)),
            deviceId: 'dev-1',
          );
          expect(outcome.kind, SendOutcomeKind.retryLater);
          expect(queue.failed(tenantId: 't'), isEmpty);
          expect(
            queue.pending(tenantId: 't').single.instanceId,
            item.instanceId,
          );
        },
      );
    }

    test(
      '422 متكرّر ما زال يصير «لم يُقبل» (لا تراجع عن الرفض النهائيّ)',
      () async {
        var item = await enqueue('alice', 'a1');
        for (var i = 0; i < SubmissionSender.maxRejectedAttempts; i++) {
          item = await queue.markRetry(item);
        }
        final adapter = FakeAdapter((_) async => const FakeReply(422));
        final outcome = await SubmissionSender.send(
          item: item,
          queue: queue,
          api: FieldFormsApi(_dio(adapter)),
          deviceId: 'dev-1',
        );
        expect(outcome.kind, SendOutcomeKind.failed);
      },
    );

    test('503 مع Retry-After ⇒ مؤقّت إعادة بلا انتظار تغيّر الشبكة، '
        'ويُرسَل حين يتعافى الخادم', () async {
      final item = await enqueue('alice', 'a1');
      var calls = 0;
      final adapter = FakeAdapter((_) async {
        calls++;
        if (calls == 1) {
          return const FakeReply(503, null, {
            'retry-after': ['120'],
          });
        }
        return const FakeReply(201, kAccepted);
      });
      final timers = <_Timer>[];
      var now = DateTime.utc(2026, 10, 27, 9);
      final c = FieldFormsCoordinator(
        queue: queue,
        api: FieldFormsApi(_dio(adapter)),
        currentTenantId: () => 't',
        currentActorId: () => 'alice',
        clock: () => now,
        timer: (d, cb) {
          final t = _Timer(d, cb);
          timers.add(t);
          return t;
        },
      );
      expect(await c.drain(), 0);
      expect(queue.pending(tenantId: 't').single.instanceId, item.instanceId);
      final scheduled = timers.where((t) => t.isActive).toList();
      expect(scheduled, hasLength(1));
      expect(
        scheduled.single.delay,
        greaterThanOrEqualTo(const Duration(seconds: 120)),
      );
      // المؤقّت يُطلَق حين يحين الموعد المحفوظ.
      now = now.add(scheduled.single.delay);
      scheduled.single.fire();
      await until(() => queue.pending(tenantId: 't').isEmpty);
      expect(calls, 2);
      expect(timers.where((t) => t.isActive), isEmpty);
    });

    test('انتهاء الجلسة يلغي مؤقّت الإعادة', () async {
      await enqueue('alice', 'a1');
      final adapter = FakeAdapter((_) async => const FakeReply(503));
      final timers = <_Timer>[];
      final c = FieldFormsCoordinator(
        queue: queue,
        api: FieldFormsApi(_dio(adapter)),
        currentTenantId: () => 't',
        currentActorId: () => 'alice',
        timer: (d, cb) {
          final t = _Timer(d, cb);
          timers.add(t);
          return t;
        },
      );
      await c.drain();
      expect(timers.single.isActive, isTrue);
      await c.onSessionEnd();
      expect(timers.single.isActive, isFalse);
    });
  });
}
