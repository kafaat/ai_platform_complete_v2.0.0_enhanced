// D3 — طابور النماذج الميدانيّة (SubmissionQueue + FieldFormsCoordinator):
//   • R11: الموعد (backoff + Retry-After بصيغتيه) محفوظ في الصفّ — لا يمحوه تصريف
//     آخر والشبكة موجودة، ولا إعادة تشغيل التطبيق (صندوق Hive يُعاد فتحه).
//   • R10: ردّ وصل بعد تبدّل المالك لا يحذف عنصر صاحبه ولا يُطلق إرسالاً بهويّة
//     جديدة؛ يُطابَق بنفس instance_id حين يعود.
//   • حارس المالك داخل ApiClient: تجديدٌ بعد 401 أعاد رمز مستخدم آخر ⇒ لا يخرج
//     الإرسال بذلك الرمز.
//   • 409 تعارض ⇒ «لم يُقبل» فوراً بلا إعادات عمياء؛ in_progress ⇒ لاحقاً.
//   • مهلة استقبال/5xx ⇒ «نتيجته غير مؤكَّدة»؛ تعذّر الاتّصال قبل الإرسال ليس كذلك.
import 'dart:async';
import 'dart:convert';
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
}

/// صاحب ترويسة Authorization (sub في حمولة JWT).
String? _subOf(Object? authorization) {
  final a = authorization?.toString();
  if (a == null || !a.startsWith('Bearer ')) return null;
  final parts = a.substring(7).split('.');
  if (parts.length != 3) return null;
  final payload = jsonDecode(
    utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))),
  );
  return payload is Map ? payload['sub']?.toString() : null;
}

void main() {
  late Directory dir;
  late SubmissionQueue queue;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('ff_sync_d3');
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
    await Future<void>.delayed(const Duration(milliseconds: 2));
    return item;
  }

  Future<void> until(bool Function() cond) async {
    for (var i = 0; i < 200 && !cond(); i++) {
      await Future<void>.delayed(const Duration(milliseconds: 5));
    }
    expect(cond(), isTrue);
  }

  Timer recordTimer(Duration d, void Function() cb) => _Timer(d, cb);

  Object? idOf(RecordedRequest r) => (r.data! as Map)['instance_id'];

  test('R11 — 429 مع Retry-After: لا إعادة فوريّة ولو بقيت الشبكة، ولا بعد '
      'إعادة تشغيل التطبيق (صندوق Hive يُعاد فتحه)', () async {
    final item = await enqueue('alice', 'a1');
    final adapter = FakeAdapter(
      (_) async => const FakeReply(
        429,
        {'detail': 'slow down'},
        {
          'retry-after': ['120'],
        },
      ),
    );
    FieldFormsCoordinator coordinatorOn(SubmissionQueue q) =>
        FieldFormsCoordinator(
          queue: q,
          api: FieldFormsApi(_dio(adapter)),
          currentTenantId: () => 't',
          currentActorId: () => 'alice',
          timer: recordTimer,
        );
    final first = coordinatorOn(queue);
    await first.drain();
    expect(adapter.requests, hasLength(1));
    // ما يفعله مستمع الشبكة: تصريف آخر والشبكة موجودة.
    await first.drain();
    expect(
      adapter.requests,
      hasLength(1),
      reason: 'وجود الشبكة لا يلغي موعد Retry-After',
    );

    // إعادة تشغيل: يُغلق Hive ويُفتح الصندوق نفسه بمنسّق جديد (الإقلاع يصرّف).
    await Hive.close();
    Hive.init(dir.path);
    final reopened = SubmissionQueue(await Hive.openBox<dynamic>('q'));
    final second = coordinatorOn(reopened);
    await second.drain();
    expect(
      adapter.requests,
      hasLength(1),
      reason: 'الموعد محفوظ في الصفّ؛ الإقلاع لا يمحوه',
    );
    final row = reopened.pending(tenantId: 't').single.toJson();
    expect(row['instance_id'], item.instanceId);
    expect(row['attempts'], 1);
    final notBefore = DateTime.parse(row['not_before']! as String);
    expect(
      notBefore.isAfter(DateTime.now().add(const Duration(seconds: 100))),
      isTrue,
    );
  });

  test('Retry-After بصيغة تاريخ HTTP يُحترَم ويُحفَظ', () async {
    await enqueue('alice', 'a1');
    final at = DateTime.now().toUtc().add(const Duration(minutes: 7));
    final adapter = FakeAdapter(
      (_) async => FakeReply(
        503,
        const {'detail': 'maintenance'},
        {
          'retry-after': [HttpDate.format(at)],
        },
      ),
    );
    final c = FieldFormsCoordinator(
      queue: queue,
      api: FieldFormsApi(_dio(adapter)),
      currentTenantId: () => 't',
      currentActorId: () => 'alice',
      timer: recordTimer,
    );
    await c.drain();
    await c.drain();
    expect(adapter.requests, hasLength(1));
    final row = queue.pending(tenantId: 't').single.toJson();
    final notBefore = DateTime.parse(row['not_before']! as String);
    // دقّة تاريخ HTTP ثانية واحدة.
    expect(notBefore.difference(at).inSeconds.abs(), lessThanOrEqualTo(1));
    expect(row['outcome_unknown'], isFalse, reason: '503 ⇒ لم يُنفَّذ');
  });

  test(
    'R10 — ردّ 201 وصل بعد تبدّل المالك: لا إرسال لاحق تحت bob، ولا حذف '
    'لعنصر alice؛ يبقى «غير مؤكَّد» ويُطابَق بنفس instance_id حين تعود',
    () async {
      final first = await enqueue('alice', 'a1');
      final second = await enqueue('alice', 'a2');
      final gate = Completer<void>();
      var n = 0;
      final adapter = FakeAdapter((_) async {
        n++;
        if (n == 1) await gate.future;
        return const FakeReply(201, kAccepted);
      });
      var actor = 'alice';
      final c = FieldFormsCoordinator(
        queue: queue,
        api: FieldFormsApi(_dio(adapter)),
        currentTenantId: () => 't',
        currentActorId: () => actor,
        timer: recordTimer,
      );
      final run = c.drain();
      await until(() => adapter.requests.length == 1);
      actor = 'bob'; // تبدّل دون onSessionEnd: الإشعار لم يصل بعد
      gate.complete();
      await run;
      expect(adapter.requests, hasLength(1));
      expect(
        queue.pending(tenantId: 't').map((i) => i.instanceId),
        [first.instanceId, second.instanceId],
        reason: 'ردّ وصل لجلسة bob لا يحذف عنصر alice',
      );
      expect(
        queue.pending(tenantId: 't').first.toJson()['outcome_unknown'],
        isTrue,
      );
      await c.drain(); // جلسة bob: لا شيء لها
      expect(adapter.requests, hasLength(1));

      actor = 'alice';
      await c.drain();
      expect(adapter.requests.map(idOf), [
        first.instanceId,
        first.instanceId,
        second.instanceId,
      ]);
      expect(queue.pending(tenantId: 't'), isEmpty);
    },
  );

  test('حارس المالك داخل ApiClient: 401 ثمّ تجديدٌ يعيد رمز bob ⇒ لا يخرج '
      'إرسال alice برمز bob', () async {
    await enqueue('alice', 'a1');
    final tokens = MemoryTokenStore(
      accessToken: fakeJwt(const Duration(hours: 1), sub: 'alice'),
      refreshToken: 'refresh-alice',
    );
    final gate = Completer<void>();
    final adapter = FakeAdapter((o) async {
      if (o.path == '/auth/refresh') {
        final sent = (o.data as Map)['refresh_token'];
        final who = sent == 'refresh-bob' ? 'bob' : 'alice';
        return FakeReply(200, {
          'access_token': fakeJwt(const Duration(hours: 1), sub: who),
        });
      }
      if (_subOf(o.headers['Authorization']) == 'alice') {
        await gate.future;
        return const FakeReply(401, {'detail': 'expired'});
      }
      return const FakeReply(201, kAccepted);
    });
    var actor = 'alice';
    final c = FieldFormsCoordinator(
      queue: queue,
      api: FieldFormsApi(testClient(adapter, tokens).dio),
      currentTenantId: () => 't',
      currentActorId: () => actor,
      timer: recordTimer,
    );
    final run = c.drain();
    await until(() => adapter.requests.length == 1);
    actor = 'bob';
    tokens.accessToken = fakeJwt(const Duration(hours: 1), sub: 'bob');
    tokens.refreshToken = 'refresh-bob';
    gate.complete();
    await run;
    final submits = adapter.to('/api/field-forms/submissions');
    expect(
      submits.map((r) => _subOf(r.headers['Authorization'])),
      ['alice'],
      reason: 'لا نسخة من إرسال alice برمز bob',
    );
    expect(queue.pending(tenantId: 't'), hasLength(1));
  });

  test('409 تعارض ⇒ «لم يُقبل» من أوّل مرّة بلا عشر إعادات عمياء؛ '
      '409 in_progress ⇒ لاحقاً ونتيجته غير مؤكَّدة', () async {
    final conflict = await enqueue('alice', 'a1');
    final busy = await enqueue('alice', 'a2');
    final adapter = FakeAdapter((o) async {
      if ((o.data as Map)['instance_id'] == conflict.instanceId) {
        return const FakeReply(409, {'detail': 'ambiguous_active_assignment'});
      }
      return const FakeReply(409, {
        'detail': {'reason': 'in_progress'},
      });
    });
    final c = FieldFormsCoordinator(
      queue: queue,
      api: FieldFormsApi(_dio(adapter)),
      currentTenantId: () => 't',
      currentActorId: () => 'alice',
      timer: recordTimer,
    );
    await c.drain();
    final failed = queue.failed(tenantId: 't');
    expect(failed.map((i) => i.instanceId), [conflict.instanceId]);
    expect(failed.single.failedReason, contains('409'));
    final pending = queue.pending(tenantId: 't').single;
    expect(pending.instanceId, busy.instanceId);
    expect(pending.toJson()['outcome_unknown'], isTrue);
    await c.drain();
    expect(
      adapter.requests.where((r) => idOf(r) == conflict.instanceId),
      hasLength(1),
      reason: 'لا إعادة عمياء للمتعارض',
    );
  });

  test('مهلة استقبال/5xx ⇒ «نتيجته غير مؤكَّدة» محفوظة؛ تعذّر الاتّصال قبل '
      'الإرسال ليس كذلك', () async {
    final slow = await enqueue('alice', 'a1');
    final down = await enqueue('alice', 'a2');
    final adapter = FakeAdapter((o) async {
      if ((o.data as Map)['instance_id'] == slow.instanceId) {
        return const FakeReply.fail(DioExceptionType.receiveTimeout);
      }
      return const FakeReply(500, {'detail': 'boom'});
    });
    final c = FieldFormsCoordinator(
      queue: queue,
      api: FieldFormsApi(_dio(adapter)),
      currentTenantId: () => 't',
      currentActorId: () => 'alice',
      timer: recordTimer,
    );
    await c.drain();
    Map<String, Object?> row(String id) => queue
        .pending(tenantId: 't')
        .firstWhere((i) => i.instanceId == id)
        .toJson();
    expect(row(slow.instanceId)['outcome_unknown'], isTrue);
    expect(row(down.instanceId)['outcome_unknown'], isTrue);
    expect(row(slow.instanceId)['next_attempt_at'], isNotNull);

    final unreachable = await enqueue('alice', 'a3');
    final offline = FakeAdapter(
      (_) async => const FakeReply.fail(DioExceptionType.connectionTimeout),
    );
    await SubmissionSender.send(
      item: unreachable,
      queue: queue,
      api: FieldFormsApi(_dio(offline)),
      deviceId: 'dev-1',
    );
    expect(row(unreachable.instanceId)['outcome_unknown'], isFalse);
    expect(row(unreachable.instanceId)['last_unreachable'], isTrue);
  });
}
