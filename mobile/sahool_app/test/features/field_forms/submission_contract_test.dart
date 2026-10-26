// عقد الإرسال مع الخادم الحقيقيّ (services/scout-ingest-service/field_forms_api.py):
//   • الخادم يردّ trust_status/field_submission_id — كلّ إرسال مقبول كان يُقرأ
//     «محجوزاً» لأنّ العميل كان يقرأ status/submission_id.
//   • الخادم يجزّئ الجسم كاملاً (ومنه submitted_at) ليقرّر الإعادة؛ كان العميل
//     يولّد submitted_at في كلّ محاولة فتُحجَر الإعادة «مختلفةً» بدل أن تُكرَّر.
//   • لا يُرسَل العنصر نفسه مرّتين في آنٍ واحد (الشاشة + التصريف).
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

void main() {
  group('SubmissionResult.fromJson — شكل الخادم الحقيقيّ', () {
    test('trust_status=accepted ⇒ مقبول (لا «محجوز»)', () {
      final r = SubmissionResult.fromJson(kAccepted);
      expect(r.status, 'accepted');
      expect(r.isAccepted, isTrue);
      expect(r.submissionId, '0d4c7a1e-0000-4000-8000-000000000001');
      expect(r.idempotentReplay, isFalse);
    });

    test('_quarantined_response ⇒ محجوز بسببه وأخطائه', () {
      final r = SubmissionResult.fromJson(const {
        'idempotent': false,
        'envelope_id': 8,
        'field_submission_id': null,
        'trust_status': 'quarantined',
        'quarantine_reason': 'form_version_unknown',
        'version_resolution_status': null,
        'validation_errors': [],
      });
      expect(r.isQuarantined, isTrue);
      expect(r.quarantineReason, 'form_version_unknown');
      expect(r.submissionId, isNull);
    });

    test('إعادة idempotent لصفّ valid ⇒ مقبول', () {
      final r = SubmissionResult.fromJson(const {
        'idempotent': true,
        'envelope_id': 7,
        'field_submission_id': 'fs-1',
        'form_validation_status': 'valid',
        'version_resolution_status': 'current',
        'stale_version': false,
      });
      expect(r.status, 'accepted');
      expect(r.idempotentReplay, isTrue);
    });

    test('إعادة idempotent لمظروف بلا صفّ أو صفّ invalid ⇒ محجوز', () {
      expect(
        SubmissionResult.fromJson(const {
          'idempotent': true,
          'envelope_id': 9,
          'field_submission_id': null,
          'form_validation_status': null,
        }).status,
        'quarantined',
      );
      expect(
        SubmissionResult.fromJson(const {
          'idempotent': true,
          'envelope_id': 9,
          'field_submission_id': 'fs-2',
          'form_validation_status': 'invalid',
        }).status,
        'quarantined',
      );
    });

    test('ردّ بلا trust_status ولا idempotent لا يُخمَّن', () {
      expect(
        () => SubmissionResult.fromJson(const {'status': 'accepted'}),
        throwsFormatException,
      );
    });
  });

  group('الطابور يجمّد جسم الإرسال', () {
    late Directory dir;
    late SubmissionQueue queue;

    setUp(() async {
      dir = await Directory.systemTemp.createTemp('ff_contract');
      Hive.init(dir.path);
      queue = SubmissionQueue(await Hive.openBox<dynamic>('q'));
    });

    tearDown(() async {
      await Hive.close();
      await dir.delete(recursive: true);
    });

    Future<QueuedSubmission> enqueue({String? actor}) => queue.enqueue(
      tenantId: 't',
      fieldId: 'f',
      assignmentId: 'a',
      assignmentRevision: 2,
      formVersionId: 'v',
      schemaHash: 'h',
      answers: const {'crop': 'wheat'},
      server: 'https://api.example.test',
      actorId: actor,
    );

    test('المحاولات المتتالية ترسل الجسم نفسه بايتاً ببايت', () async {
      final item = await enqueue();
      final first = jsonEncode(item.buildEnvelope());
      await Future<void>.delayed(const Duration(milliseconds: 5));
      final retried = await queue.markRetry(item);
      // وبعد إعادة القراءة من القرص (إعادة تشغيل التطبيق):
      final reread = queue.pending().single;
      expect(jsonEncode(retried.buildEnvelope()), first);
      expect(jsonEncode(reread.buildEnvelope()), first);
      // حتّى لو مرّر المستدعي server/submittedAt مختلفين، المجمَّد يغلب.
      expect(
        jsonEncode(
          reread.buildEnvelope(
            server: 'https://other.test',
            submittedAt: DateTime.utc(2030),
          ),
        ),
        first,
      );
    });

    test('عنصر قديم بلا submitted_at يستعمل local_created_at الثابت', () {
      final legacy = QueuedSubmission.fromJson({
        'instance_id': 'ff-old',
        'tenant_id': 't',
        'field_id': 'f',
        'assignment_id': 'a',
        'assignment_revision': 1,
        'form_version_id': 'v',
        'schema_hash': 'h',
        'answers': const {},
        'local_created_at': '2026-01-02T03:04:05.000Z',
        'attempts': 2,
      });
      final a = legacy.buildEnvelope(server: 'https://api.example.test');
      final b = legacy.buildEnvelope(server: 'https://api.example.test');
      expect(a['submitted_at'], '2026-01-02T03:04:05.000Z');
      expect(jsonEncode(a), jsonEncode(b));
    });

    test('عناصر مستخدمٍ آخر لا تُصرَّف تحت جلستك', () async {
      final mine = await enqueue(actor: 'u1');
      await enqueue(actor: 'u2');
      final ids = queue
          .pending(tenantId: 't', actorId: 'u1')
          .map((i) => i.instanceId);
      expect(ids, [mine.instanceId]);
    });

    test('إرسالان متزامنان للعنصر نفسه ⇒ طلب HTTP واحد', () async {
      final item = await enqueue();
      final gate = Completer<void>();
      final adapter = FakeAdapter((_) async {
        await gate.future;
        return const FakeReply(201, kAccepted);
      });
      final api = FieldFormsApi(_dio(adapter));
      final a = SubmissionSender.send(
        item: item,
        queue: queue,
        api: api,
        deviceId: 'dev-1',
      );
      final b = SubmissionSender.send(
        item: item,
        queue: queue,
        api: api,
        deviceId: 'dev-1',
      );
      expect(SubmissionSender.isInFlight(item.instanceId), isTrue);
      gate.complete();
      final results = await Future.wait([a, b]);
      expect(adapter.requests, hasLength(1));
      expect(results.every((o) => o.kind == SendOutcomeKind.settled), isTrue);
      expect(queue.pending(), isEmpty);
      expect(SubmissionSender.isInFlight(item.instanceId), isFalse);
    });

    test('رفض 4xx متكرّر ⇒ «لم يُقبل» محفوظ، لا حذف صامت', () async {
      final item = await enqueue();
      final adapter = FakeAdapter(
        (_) async =>
            const FakeReply(400, {'detail': 'X-Tenant-Id must be a UUID'}),
      );
      final coordinator = FieldFormsCoordinator(
        queue: queue,
        api: FieldFormsApi(_dio(adapter)),
        currentTenantId: () => 't',
        currentActorId: () => null,
      );
      for (var i = 0; i < SubmissionSender.maxRejectedAttempts; i++) {
        await coordinator.drain();
      }
      expect(
        queue.pending(),
        isEmpty,
        reason: 'لا يُعاد تلقائيّاً بعد التوقّف',
      );
      final failed = queue.failed().single;
      expect(failed.instanceId, item.instanceId);
      expect(failed.failedReason, contains('400'));
      // drain إضافيّ لا يرسل العنصر الفاشل.
      final before = adapter.requests.length;
      await coordinator.drain();
      expect(adapter.requests.length, before);
      // المستخدم يعيده صراحةً بالجسم نفسه.
      final back = await queue.requeue(failed);
      expect(back.isFailed, isFalse);
      expect(
        jsonEncode(back.buildEnvelope()),
        jsonEncode(item.buildEnvelope()),
      );
    });

    test('drain يبلّغ القائمة حين يعالج عناصر', () async {
      await enqueue();
      final adapter = FakeAdapter((_) async => const FakeReply(201, kAccepted));
      final coordinator = FieldFormsCoordinator(
        queue: queue,
        api: FieldFormsApi(_dio(adapter)),
        currentTenantId: () => 't',
        currentActorId: () => null,
      );
      var ticks = 0;
      coordinator.drainTick.addListener(() => ticks++);
      expect(await coordinator.drain(), 1);
      expect(ticks, 1);
    });
  });
}
