/// طابور الإرسال Offline-first (GAP-FIELD-FORMS-01 §8.7/§15).
///
/// كلّ عنصر يحمل instance_id ثابتًا يُولَّد مرّة واحدة عند الإدراج؛
/// retry لا يُنشئ instance_id جديدًا أبدًا (idempotency أمام الخادم).
library;

import 'dart:math';

import 'package:hive_flutter/hive_flutter.dart';

String _newInstanceId() {
  final rand = Random.secure();
  final suffix = List.generate(16, (_) => rand.nextInt(256))
      .map((b) => b.toRadixString(16).padLeft(2, '0'))
      .join();
  return 'ff-${DateTime.now().toUtc().microsecondsSinceEpoch}-$suffix';
}

/// عنصر طابور إرسال: الإجابات + هويّة النسخة + definition_sync_token.
class QueuedSubmission {
  final String instanceId; // ثابت عبر كلّ retries
  final String tenantId;
  final String fieldId;
  final String assignmentId;
  final int assignmentRevision;
  final String formVersionId;
  final String schemaHash;
  final String? definitionSyncToken;
  final Map<String, Object?> answers;
  final DateTime localCreatedAt;
  final int attempts;

  const QueuedSubmission({
    required this.instanceId,
    required this.tenantId,
    required this.fieldId,
    required this.assignmentId,
    required this.assignmentRevision,
    required this.formVersionId,
    required this.schemaHash,
    this.definitionSyncToken,
    required this.answers,
    required this.localCreatedAt,
    this.attempts = 0,
  });

  QueuedSubmission copyWithAttempts(int attempts) => QueuedSubmission(
        instanceId: instanceId, // لا يتغيّر أبدًا
        tenantId: tenantId,
        fieldId: fieldId,
        assignmentId: assignmentId,
        assignmentRevision: assignmentRevision,
        formVersionId: formVersionId,
        schemaHash: schemaHash,
        definitionSyncToken: definitionSyncToken,
        answers: answers,
        localCreatedAt: localCreatedAt,
        attempts: attempts,
      );

  Map<String, Object?> toJson() => {
        'instance_id': instanceId,
        'tenant_id': tenantId,
        'field_id': fieldId,
        'assignment_id': assignmentId,
        'assignment_revision': assignmentRevision,
        'form_version_id': formVersionId,
        'schema_hash': schemaHash,
        'definition_sync_token': definitionSyncToken,
        'answers': answers,
        'local_created_at': localCreatedAt.toUtc().toIso8601String(),
        'attempts': attempts,
      };

  factory QueuedSubmission.fromJson(Map<String, Object?> json) =>
      QueuedSubmission(
        instanceId: json['instance_id'] as String,
        tenantId: json['tenant_id'] as String,
        fieldId: json['field_id'] as String,
        assignmentId: json['assignment_id'] as String,
        assignmentRevision: (json['assignment_revision'] as num).toInt(),
        formVersionId: json['form_version_id'] as String,
        schemaHash: json['schema_hash'] as String,
        definitionSyncToken: json['definition_sync_token'] as String?,
        answers: Map<String, Object?>.from(json['answers'] as Map? ?? {}),
        localCreatedAt: DateTime.parse(json['local_created_at'] as String),
        attempts: (json['attempts'] as num? ?? 0).toInt(),
      );

  /// envelope الإرسال الكامل (§8/دفعة العقود) — هويّة النسخة تُعاد كما هي.
  Map<String, Object?> buildEnvelope({
    required String provider,
    required String server,
    DateTime? submittedAt,
  }) =>
      {
        'provider': provider,
        'server': server,
        'instance_id': instanceId,
        'submitted_at':
            (submittedAt ?? DateTime.now().toUtc()).toIso8601String(),
        'local_created_at': localCreatedAt.toUtc().toIso8601String(),
        'field_id': fieldId,
        'form_version_id': formVersionId,
        'schema_hash': schemaHash,
        'assignment_revision': assignmentRevision,
        'definition_sync_token': definitionSyncToken,
        'answers': answers,
      };
}

class SubmissionQueue {
  static const String boxName = 'field_forms_queue';

  final Box<dynamic> _box;

  SubmissionQueue(this._box);

  static Future<SubmissionQueue> open() async =>
      SubmissionQueue(await Hive.openBox<dynamic>(boxName));

  /// إدراج جديد — يولّد instance_id هنا فقط، مرّة واحدة.
  Future<QueuedSubmission> enqueue({
    required String tenantId,
    required String fieldId,
    required String assignmentId,
    required int assignmentRevision,
    required String formVersionId,
    required String schemaHash,
    String? definitionSyncToken,
    required Map<String, Object?> answers,
  }) async {
    final item = QueuedSubmission(
      instanceId: _newInstanceId(),
      tenantId: tenantId,
      fieldId: fieldId,
      assignmentId: assignmentId,
      assignmentRevision: assignmentRevision,
      formVersionId: formVersionId,
      schemaHash: schemaHash,
      definitionSyncToken: definitionSyncToken,
      answers: Map<String, Object?>.from(answers),
      localCreatedAt: DateTime.now().toUtc(),
    );
    await _box.put(item.instanceId, item.toJson());
    return item;
  }

  /// تسجيل محاولة فاشلة: يزيد العدّاد ولا يمسّ instance_id.
  Future<QueuedSubmission> markRetry(QueuedSubmission item) async {
    final updated = item.copyWithAttempts(item.attempts + 1);
    await _box.put(updated.instanceId, updated.toJson());
    return updated;
  }

  Future<void> remove(String instanceId) => _box.delete(instanceId);

  List<QueuedSubmission> pending() {
    final result = <QueuedSubmission>[];
    for (final key in _box.keys) {
      final raw = _box.get(key);
      if (raw is Map) {
        result.add(
            QueuedSubmission.fromJson(Map<String, Object?>.from(raw)));
      }
    }
    result.sort((a, b) => a.localCreatedAt.compareTo(b.localCreatedAt));
    return result;
  }

  Future<void> clearAll() => _box.clear();
}
