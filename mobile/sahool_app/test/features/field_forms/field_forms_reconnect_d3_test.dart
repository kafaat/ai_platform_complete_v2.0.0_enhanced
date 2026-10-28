// D3 — عودة الشبكة في طابور النماذج الميدانيّة: تتخطّى backoff فشلٍ كان انقطاعاً
// فقط (فلا ينتظر الإرسال نصف ساعة بعد عودة الاتّصال)، ولا تتخطّى Retry-After
// ولا backoff سببه ردّ الخادم. (ملفّ مستقلّ: drain(afterReconnect:) واجهة جديدة.)
import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:sahool_app/features/field_forms/data/field_forms_api.dart';
import 'package:sahool_app/features/field_forms/data/field_forms_coordinator.dart';
import 'package:sahool_app/features/field_forms/data/submission_queue.dart';

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

void main() {
  late Directory dir;
  late SubmissionQueue queue;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('ff_reconnect_d3');
    Hive.init(dir.path);
    queue = SubmissionQueue(await Hive.openBox<dynamic>('q'));
  });

  tearDown(() async {
    await Hive.close();
    await dir.delete(recursive: true);
  });

  Future<QueuedSubmission> enqueue(String assignment) async {
    final item = await queue.enqueue(
      tenantId: 't',
      fieldId: 'f',
      assignmentId: assignment,
      assignmentRevision: 1,
      formVersionId: 'v',
      schemaHash: 'h',
      answers: {'a': assignment},
      server: 'https://api.example.test',
      actorId: 'alice',
    );
    await Future<void>.delayed(const Duration(milliseconds: 2));
    return item;
  }

  Object? idOf(RecordedRequest r) => (r.data! as Map)['instance_id'];

  test('عودة الشبكة تتخطّى backoff انقطاعٍ فقط، لا Retry-After ولا backoff '
      'سببه ردّ الخادم', () async {
    final cut = await enqueue('a1');
    final limited = await enqueue('a2');
    var online = false;
    final adapter = FakeAdapter((o) async {
      if (!online) {
        return const FakeReply.fail(DioExceptionType.connectionTimeout);
      }
      if ((o.data as Map)['instance_id'] == limited.instanceId) {
        return const FakeReply(
          429,
          {'detail': 'slow'},
          {
            'retry-after': ['600'],
          },
        );
      }
      return const FakeReply(201, kAccepted);
    });
    final c = FieldFormsCoordinator(
      queue: queue,
      api: FieldFormsApi(_dio(adapter)),
      currentTenantId: () => 't',
      currentActorId: () => 'alice',
      timer: _Timer.new,
    );
    await c.drain(); // كلاهما: انقطاع
    expect(adapter.requests, hasLength(2));
    // تصريف مجدول قبل الموعد (الشبكة ما زالت مقطوعة): لا شيء.
    await c.drain();
    expect(adapter.requests, hasLength(2));

    online = true;
    await c.drain(afterReconnect: true); // cut يُرسَل؛ limited يلقى 429
    expect(queue.pending(tenantId: 't').map((i) => i.instanceId), [
      limited.instanceId,
    ]);
    final before = adapter.requests.length;
    await c.drain(afterReconnect: true);
    expect(
      adapter.requests.length,
      before,
      reason: 'Retry-After لا تتخطّاه عودة الشبكة',
    );
    expect(
      adapter.requests.where((r) => idOf(r) == cut.instanceId),
      hasLength(2),
    );
  });
}
