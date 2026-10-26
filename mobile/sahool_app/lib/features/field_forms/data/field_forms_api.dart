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

/// استجابة الإرسال (201) بشكل الخادم الحقيقيّ
/// (services/scout-ingest-service/field_forms_api.py: `submit_form` و
/// `_quarantined_response`). تُعرض الحالة كما هي — لا نجاح كاذب.
///
/// الخادم يردّ `trust_status` و`field_submission_id` (لا `status` ولا
/// `submission_id`). إعادة إرسال مظروف سبق قبوله (`idempotent: true`) لا تحمل
/// `trust_status`: الصفّ المقبول دائماً `form_validation_status == 'valid'`،
/// وكلّ صفّ محجور `invalid` أو `unknown_schema` أو بلا صفّ أصلاً.
class SubmissionResult {
  /// accepted | quarantined (مشتقّ من trust_status أو من صفّ الإعادة).
  final String status;

  /// معرّف صفّ field_submissions (`field_submission_id`)؛ null لمظروف محجور
  /// بلا صفّ (نسخة نموذج مجهولة).
  final String? submissionId;

  /// current | stale_proven | withdrawn_quarantined | invalid_sync_proof | no_active_assignment
  final String? versionResolutionStatus;

  /// valid | invalid | unknown_schema
  final String? formValidationStatus;

  /// سبب الحجر كما أرسله الخادم (form_version_unknown، form_validation_failed…).
  final String? quarantineReason;

  /// أخطاء تحقّق الخادم (أوّل عشرة) عند form_validation_failed.
  final List<String> validationErrors;

  /// true ⇒ الخادم تعرّف المظروف (نفس instance_id ونفس الجسم) وأعاد نتيجته السابقة.
  final bool idempotentReplay;

  /// true ⇒ قُبل على نسخة قديمة بإثبات مزامنة صالح.
  final bool? staleVersion;

  const SubmissionResult({
    required this.status,
    this.submissionId,
    this.versionResolutionStatus,
    this.formValidationStatus,
    this.quarantineReason,
    this.validationErrors = const [],
    this.idempotentReplay = false,
    this.staleVersion,
  });

  bool get isAccepted => status == 'accepted';
  bool get isQuarantined => status == 'quarantined';

  /// يرمي [FormatException] إن لم يحمل الردّ trust_status ولم يكن إعادة: ردّ
  /// بلا حالة لا يُقرأ «محجوزاً» ولا «مقبولاً» تخميناً؛ يبقى العنصر في الطابور
  /// وتُعاد المحاولة فيُجيب الخادم بنتيجته المخزّنة (idempotent).
  factory SubmissionResult.fromJson(Map<String, Object?> json) {
    final trust = json['trust_status'];
    final replay = json['idempotent'] == true;
    final validation = json['form_validation_status'] as String?;
    final String status;
    if (trust == 'accepted' || trust == 'quarantined') {
      status = trust! as String;
    } else if (replay) {
      status = validation == 'valid' ? 'accepted' : 'quarantined';
    } else {
      throw const FormatException('استجابة إرسال النموذج بلا trust_status');
    }
    final rawErrors = json['validation_errors'];
    final rawId = json['field_submission_id'];
    return SubmissionResult(
      status: status,
      submissionId: rawId?.toString(),
      versionResolutionStatus: json['version_resolution_status'] as String?,
      formValidationStatus: validation,
      quarantineReason: json['quarantine_reason'] as String?,
      validationErrors: rawErrors is List
          ? rawErrors.map((e) => e.toString()).toList()
          : const [],
      idempotentReplay: replay,
      staleVersion: json['stale_version'] as bool?,
    );
  }
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
          .map(
            (f) => DownloadedFormPackage.fromJson(
              Map<String, Object?>.from(f as Map),
            ),
          )
          .toList(),
    );
  }

  /// POST /api/field-forms/submissions بالـenvelope الكامل.
  Future<SubmissionResult> submit(
    Map<String, Object?> envelope, {
    required String deviceId,
  }) async {
    final response = await _dio.post<Map<String, Object?>>(
      '/api/field-forms/submissions',
      data: envelope,
      options: Options(headers: {'X-Device-Id': deviceId}),
    );
    return SubmissionResult.fromJson(
      response.data ?? const <String, Object?>{},
    );
  }
}
