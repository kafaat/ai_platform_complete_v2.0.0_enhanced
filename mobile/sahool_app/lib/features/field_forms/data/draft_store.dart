/// مسودّات النماذج الميدانيّة Offline-first (GAP-FIELD-FORMS-01 §8.7).
///
/// مفتاح المسودّة الخماسيّ: tenant + field_id + assignment_id +
/// form_version_id + schema_hash. لا ترحيل إجابات بين نسختين أبدًا —
/// نسخة جديدة (أو hash جديد) تعني مفتاحًا جديدًا ومسودّة فارغة.
library;

import 'package:hive_flutter/hive_flutter.dart';

/// مسودّة محفوظة محليًّا: الإجابات + هويّة النسخة الكاملة.
class FormDraft {
  final String tenantId;
  final String fieldId;
  final String assignmentId;
  final int revision;
  final String formVersionId;
  final String schemaHash;
  final String? definitionSyncToken;
  final Map<String, Object?> answers;
  final DateTime savedAt;

  const FormDraft({
    required this.tenantId,
    required this.fieldId,
    required this.assignmentId,
    required this.revision,
    required this.formVersionId,
    required this.schemaHash,
    this.definitionSyncToken,
    required this.answers,
    required this.savedAt,
  });

  Map<String, Object?> toJson() => {
        'tenant_id': tenantId,
        'field_id': fieldId,
        'assignment_id': assignmentId,
        'revision': revision,
        'form_version_id': formVersionId,
        'schema_hash': schemaHash,
        'definition_sync_token': definitionSyncToken,
        'answers': answers,
        'saved_at': savedAt.toUtc().toIso8601String(),
      };

  factory FormDraft.fromJson(Map<String, Object?> json) => FormDraft(
        tenantId: json['tenant_id'] as String,
        fieldId: json['field_id'] as String,
        assignmentId: json['assignment_id'] as String,
        revision: (json['revision'] as num).toInt(),
        formVersionId: json['form_version_id'] as String,
        schemaHash: json['schema_hash'] as String,
        definitionSyncToken: json['definition_sync_token'] as String?,
        answers: Map<String, Object?>.from(json['answers'] as Map? ?? {}),
        savedAt: DateTime.parse(json['saved_at'] as String),
      );
}

class DraftStore {
  static const String boxName = 'field_forms_drafts';

  final Box<dynamic> _box;

  DraftStore(this._box);

  static Future<DraftStore> open() async =>
      DraftStore(await Hive.openBox<dynamic>(boxName));

  /// المفتاح الخماسيّ — يمنع أيّ ترحيل ضمنيّ بين النسخ.
  static String draftKey({
    required String tenantId,
    required String fieldId,
    required String assignmentId,
    required String formVersionId,
    required String schemaHash,
  }) =>
      '$tenantId|$fieldId|$assignmentId|$formVersionId|$schemaHash';

  String keyOf(FormDraft draft) => draftKey(
        tenantId: draft.tenantId,
        fieldId: draft.fieldId,
        assignmentId: draft.assignmentId,
        formVersionId: draft.formVersionId,
        schemaHash: draft.schemaHash,
      );

  Future<void> save(FormDraft draft) async {
    await _box.put(keyOf(draft), draft.toJson());
  }

  /// يسترجع المسودّة بنفس هويّة النسخة بالضبط؛ لا يوجد fallback لنسخة أقدم.
  FormDraft? load({
    required String tenantId,
    required String fieldId,
    required String assignmentId,
    required String formVersionId,
    required String schemaHash,
  }) {
    final raw = _box.get(draftKey(
      tenantId: tenantId,
      fieldId: fieldId,
      assignmentId: assignmentId,
      formVersionId: formVersionId,
      schemaHash: schemaHash,
    ));
    if (raw is! Map) return null;
    return FormDraft.fromJson(Map<String, Object?>.from(raw));
  }

  Future<void> discard(FormDraft draft) => _box.delete(keyOf(draft));

  Future<void> clearAll() => _box.clear();
}
