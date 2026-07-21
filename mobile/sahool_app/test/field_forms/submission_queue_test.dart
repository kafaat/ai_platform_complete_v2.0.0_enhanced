/// طابور الإرسال: retry لا يُنشئ instance_id جديدًا (§15.3)،
/// والـenvelope يحمل حقول العقد كاملة.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:sahool_app/features/field_forms/data/submission_queue.dart';

void main() {
  late SubmissionQueue queue;
  late Directory tempDir;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp('queue_test');
    Hive.init(tempDir.path);
  });

  setUp(() async {
    queue = await SubmissionQueue.open();
    await queue.clearAll();
  });

  tearDownAll(() async {
    await Hive.close();
    await tempDir.delete(recursive: true);
  });

  Future<QueuedSubmission> enqueueOne() => queue.enqueue(
        tenantId: 'tenant-1',
        fieldId: 'field-9',
        assignmentId: 'assign-7',
        assignmentRevision: 3,
        formVersionId: 'v1',
        schemaHash: 'hash-v1',
        definitionSyncToken: 'sync-token-abc',
        answers: const {'crop': 'wheat'},
      );

  test('retry يبقي instance_id ثابتًا عبر محاولات متعدّدة', () async {
    final item = await enqueueOne();
    final originalId = item.instanceId;

    var current = item;
    for (var i = 0; i < 3; i++) {
      current = await queue.markRetry(current);
      expect(current.instanceId, originalId,
          reason: 'retry رقم ${i + 1} غيّر instance_id — ممنوع');
    }
    expect(current.attempts, 3);

    // المخزَّن أيضًا بنفس المعرف (لا عنصر جديد).
    final pending = queue.pending();
    expect(pending.length, 1);
    expect(pending.single.instanceId, originalId);
  });

  test('إغلاق وفتح: العنصر يبقى بنفس instance_id', () async {
    final item = await enqueueOne();
    await Hive.box(SubmissionQueue.boxName).close();
    final reopened = await SubmissionQueue.open();
    final pending = reopened.pending();
    expect(pending.single.instanceId, item.instanceId);
    expect(pending.single.answers, {'crop': 'wheat'});
  });

  test('envelope يحمل حقول العقد كاملة', () async {
    final item = await enqueueOne();
    final envelope = item.buildEnvelope(
      provider: 'sahool-flutter',
      server: 'https://api.example.test',
      submittedAt: DateTime.utc(2025, 1, 15, 12),
    );
    expect(envelope['provider'], 'sahool-flutter');
    expect(envelope['server'], 'https://api.example.test');
    expect(envelope['instance_id'], item.instanceId);
    expect(envelope['submitted_at'], '2025-01-15T12:00:00.000Z');
    expect(envelope['local_created_at'], isA<String>());
    expect(envelope['field_id'], 'field-9');
    expect(envelope['form_version_id'], 'v1');
    expect(envelope['schema_hash'], 'hash-v1');
    expect(envelope['assignment_revision'], 3);
    expect(envelope['definition_sync_token'], 'sync-token-abc');
    expect(envelope['answers'], {'crop': 'wheat'});
  });
}
