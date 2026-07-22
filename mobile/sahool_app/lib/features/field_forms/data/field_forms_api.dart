/// وصول النماذج الميدانيّة عبر مسار BFF فقط (GAP-FIELD-FORMS-01 §8.6/§8.7).
///
/// يستقبل Dio المهيّأ من ApiService الموجود (baseUrl = AppConfig.apiUri مع JWT
/// عبر interceptor) — لا يُنشئ Dio جديدًا ولا يحمل أيّ توكن خدمة؛
/// المصادقة الخاصّة بالخدمة يحقنها الـBFF خادميًّا.
library;

import 'package:dio/dio.dart';

/// حزمة نموذج واحدة كما نزّلها الخادم (تُحفظ كما هي).
class DownloadedFormPackage {
  final String assignmentId;
  final int revision;
  final String formVersionId;
  final int versionNumber;
  final Map<String, Object?> schemaJson;
  final Map<String, Object?>? logicJson;
  final String schemaHash;
  final String? definitionSyncToken;

  const DownloadedFormPackage({
    required this.assignmentId,
    required this.revision,
    required this.formVersionId,
    required this.versionNumber,
    required this.schemaJson,
    this.logicJson,
    required this.schemaHash,
    this.definitionSyncToken,
  });

  factory DownloadedFormPackage.fromJson(Map<String, Object?> json) {
    return DownloadedFormPackage(
      assignmentId: json['assignment_id'] as String,
      revision: (json['revision'] as num).toInt(),
      formVersionId: json['form_version_id'] as String,
      versionNumber: (json['version_number'] as num).toInt(),
      schemaJson: Map<String, Object?>.from(json['schema_json'] as Map),
      logicJson: json['logic_json'] == null
          ? null
          : Map<String, Object?>.from(json['logic_json'] as Map),
      schemaHash: json['schema_hash'] as String,
      definitionSyncToken: json['definition_sync_token'] as String?,
    );
  }

  Map<String, Object?> toJson() => {
        'assignment_id': assignmentId,
        'revision': revision,
        'form_version_id': formVersionId,
        'version_number': versionNumber,
        'schema_json': schemaJson,
        'logic_json': logicJson,
        'schema_hash': schemaHash,
        'definition_sync_token': definitionSyncToken,
      };
}

/// نتيجة التنزيل: field_id + قائمة الحزم.
class FieldFormsDownload {
  final String fieldId;
  final List<DownloadedFormPackage> forms;

  const FieldFormsDownload({required this.fieldId, required this.forms});
}

/// استجابة الإرسال (201): تُعرض الحالة كما هي — لا نجاح كاذب.
class SubmissionResult {
  /// accepted | quarantined (كما يرد من الخادم)
  final String status;
  final String? submissionId;

  /// current | stale_proven | withdrawn_quarantined | invalid_sync_proof | no_active_assignment
  final String? versionResolutionStatus;

  /// valid | invalid | unknown_schema
  final String? formValidationStatus;

  const SubmissionResult({
    required this.status,
    this.submissionId,
    this.versionResolutionStatus,
    this.formValidationStatus,
  });

  factory SubmissionResult.fromJson(Map<String, Object?> json) =>
      SubmissionResult(
        status: json['status'] as String? ?? 'quarantined',
        submissionId: json['submission_id'] as String?,
        versionResolutionStatus: json['version_resolution_status'] as String?,
        formValidationStatus: json['form_validation_status'] as String?,
      );
}

class FieldFormsApi {
  final Dio _dio;

  /// مرّر dio الخاصّ بـ ApiService الموجود (نفس baseUrl والـJWT interceptor).
  FieldFormsApi(this._dio);

  /// GET /api/field-forms/download?field_id&actor_id&device_id
  Future<FieldFormsDownload> download({
    required String fieldId,
    required String actorId,
    required String deviceId,
  }) async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/field-forms/download',
      queryParameters: {
        'field_id': fieldId,
        'actor_id': actorId,
        'device_id': deviceId,
      },
    );
    final data = response.data ?? const <String, Object?>{};
    final rawForms = (data['forms'] as List? ?? const []);
    return FieldFormsDownload(
      fieldId: data['field_id'] as String? ?? fieldId,
      forms: rawForms
          .map((f) => DownloadedFormPackage.fromJson(
              Map<String, Object?>.from(f as Map)))
          .toList(),
    );
  }

  /// POST /api/field-forms/submissions بالـenvelope الكامل.
  Future<SubmissionResult> submit(Map<String, Object?> envelope) async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/field-forms/submissions',
      data: envelope,
    );
    return SubmissionResult.fromJson(
        response.data ?? const <String, Object?>{});
  }
}
