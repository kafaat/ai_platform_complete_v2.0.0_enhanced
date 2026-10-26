// SAHOOL — features/advisor/data/advisor_api.dart
// نقاط المستشار الزراعيّ: المحادثة، توصيات الحقل، توصية المحرّك وتغذيتها الراجعة،
// وتصعيد الآفة. يملكه وكيل ميزة المستشار.
//
// ملاحظة مسار مُثبَّت: نداء المحادثة (/api/ai-agronomist/chat) يبقى نصّاً في
// lib/services/api_service.dart لأنّ tests/mobile/test_phase11_mobile_offline_sync_runtime.py
// يقرأ ذلك الملفّ بالمسار. [askAgent] هنا يفوّض إليه بعميل هذا الصنف.
//
// منع التكرار (Idempotency-Key) مُرسَل فقط حيث يحترمه الخادم:
// - POST /api/v1/recommendations/outcomes: `_idempotent(...)` في recommendations.py.
// - POST /api/v1/pest-escalation/run: الخادم يستأنف بنفس workflow_id (مخزن دائم)،
//   فالمفتاح مشتقّ منه ومن نوع الخطوة.
// المحادثة وطلب توصية لحقل لا يحترمان المفتاح؛ يُرسَلان بلا مفتاح فلا يُعادان
// تلقائيّاً على 502/503/504 (إعادة صامتة قد تُنشئ توصيةً ثانية أو حدث تدقيق آخر).
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';
import 'package:sahool_app/services/api_service.dart';

/// مهلة المستشار (= ما يمرّره ApiService.askAgent، ومهلة البوّابة).
const Duration kAdvisorTimeout = Duration(seconds: 120);

class AdvisorApi {
  AdvisorApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final AdvisorApi instance = AdvisorApi();
  final ApiClient _client;

  /// سؤال المستشار (POST /api/ai-agronomist/chat) — انظر ApiService.askAgent.
  Future<Map<String, dynamic>> askAgent(String query, {String? fieldId}) =>
      ApiService.instance.askAgent(query, fieldId: fieldId, client: _client);

  /// العمود الموحَّد لتوصيات الحقل (ريّ/تسميد/أمراض/حصاد) —
  /// GET /api/v1/fields/{id}/recommendations (fields.py). 503 ⇒ لا توصية أمكن
  /// توليدها (الخادم يقول السبب في detail).
  Future<Map<String, dynamic>> getFieldRecommendations(String fieldId) async =>
      asJsonMap(
        await _client.get(
          '/api/v1/fields/${Uri.encodeComponent(fieldId)}/recommendations',
        ),
      );

  /// يطلب توصية من المحرّك لحقل (POST /api/v1/recommendations/for-field). الخادم
  /// يبني «شهادة الجودة» بنفسه. التوصية المحجوبة (422/403 بجسم delivered=false
  /// وreason_ar) نتيجةٌ صادقة لا عطل، فتُعاد كما هي ليعرض الـUI سببها.
  Future<Map<String, dynamic>> requestRecommendationForField({
    required String fieldId,
    required String crop,
    String farmId = '',
    String? growthStage,
  }) async {
    try {
      return asJsonMap(
        await _client.post(
          '/api/v1/recommendations/for-field',
          data: {
            'field_id': fieldId,
            'farm_id': farmId,
            'crop': crop,
            if (growthStage != null && growthStage.isNotEmpty)
              'growth_stage': growthStage,
          },
        ),
      );
    } on ApiException catch (e) {
      final body = serverBody(e);
      if (body != null && body['delivered'] == false) return body;
      throw _withServerArabic(e, body);
    }
  }

  /// توصية مُخزَّنة وشرحها (GET /api/v1/recommendations/{rec_id}).
  Future<Map<String, dynamic>> getRecommendation(String recId) async =>
      asJsonMap(
        await _client.get(
          '/api/v1/recommendations/${Uri.encodeComponent(recId)}',
        ),
      );

  /// تغذية راجعة: قبول/رفض توصية (POST /api/v1/recommendations/outcomes → 201).
  /// الجسم مطابق لـOutcomeRecordRequest (api_models.py): crop وfield_id إلزاميّان.
  /// لا حقل «سبب» في العقد؛ لا يُرسَل ما لا يقرؤه الخادم.
  /// [idempotencyKey] ثابت لنيّة واحدة (فتح ورقة التغذية) عبر كلّ المحاولات.
  Future<Map<String, dynamic>> recordRecommendationOutcome({
    required String crop,
    required String fieldId,
    required bool accepted,
    required IdempotencyKey idempotencyKey,
    String? farmId,
    String? recommendationId,
    double? predictedYieldTHa,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/recommendations/outcomes',
      data: {
        'crop': crop,
        'field_id': fieldId,
        if (farmId != null && farmId.isNotEmpty) 'farm_id': farmId,
        if (recommendationId != null) 'recommendation_id': recommendationId,
        if (predictedYieldTHa != null)
          'predicted_yield_t_ha': predictedYieldTHa,
        'accepted': accepted,
        'matured_within_lag': false,
      },
      idempotencyKey: idempotencyKey,
    ),
  );

  /// تدفّق تصعيد الآفة (POST /api/v1/pest-escalation/run) — يتطلّب
  /// pesticide:approve (مالك/مهندس). أوّل نداء (pest_type/severity) يصل إلى
  /// خطوة الموافقة ويُعلَّق؛ نداء ثانٍ بنفس [workflowId] و[approvalStatus]
  /// (approved/rejected) يستأنفه.
  Future<Map<String, dynamic>> runPestEscalation({
    required String workflowId,
    String? fieldId,
    String? pestType,
    double? severity,
    String? approvalStatus,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/pest-escalation/run',
      data: {
        'workflow_id': workflowId,
        if (fieldId != null && fieldId.isNotEmpty) 'field_id': fieldId,
        if (pestType != null) 'pest_type': pestType,
        if (severity != null) 'severity': severity,
        if (approvalStatus != null) 'approval_status': approvalStatus,
      },
      idempotencyKey: IdempotencyKey(
        '$workflowId:${approvalStatus ?? 'start'}',
      ),
    ),
  );

  /// كشف الآفات بالصورة (multipart → /api/edge/v1/inference/pest-detect).
  /// لم يعد المستشار يعرضه: انتقلت واجهته إلى ميزة الاستكشاف (scouting). يبقى
  /// التوقيع لأنّ دوالّ أصناف الـAPI لا تُحذَف في الموجة الثانية. الخادم يشترط
  /// `field_id` (Form إلزاميّ)؛ النداء بلا حقل يُرفَض بـ422.
  Future<Map<String, dynamic>> analyzePestImage(
    File image, {
    String? fieldId,
    String crop = 'wheat',
  }) async {
    final fileName = image.path.split('/').last;
    final form = FormData.fromMap({
      'file': await MultipartFile.fromFile(image.path, filename: fileName),
      if (fieldId != null) 'field_id': fieldId,
      'crop': crop,
    });
    final r = await _client.send(
      'POST',
      '/api/edge/v1/inference/pest-detect',
      data: form,
      contentType: 'multipart/form-data',
      sendTimeout: kAdvisorTimeout,
      receiveTimeout: kAdvisorTimeout,
    );
    return asJsonMap(r);
  }
}

/// جسم استجابة الخطأ كما أرسله الخادم (إن كان كائناً).
Map<String, dynamic>? serverBody(ApiException e) {
  final cause = e.cause;
  if (cause is DioException) {
    final data = cause.response?.data;
    if (data is Map) return data.map((k, v) => MapEntry(k.toString(), v));
  }
  return null;
}

/// محرّك التوصية يكتب سببه العربيّ في `ar` (400/429/500 في api_adapter.py) لا في
/// `detail`، فتضيع رسالته في ApiException العامّ. نُبقي النوع والرمز ونعرض نصّه.
/// رسائل 401/403/404/503 عقدٌ ثابت لا تُستبدَل.
ApiException _withServerArabic(ApiException e, Map<String, dynamic>? body) {
  final ar = body?['ar'];
  const contract = {401, 403, 404, 503};
  if (ar is! String || ar.trim().isEmpty || contract.contains(e.statusCode)) {
    return e;
  }
  return ApiException(
    kind: e.kind,
    statusCode: e.statusCode,
    messageAr: ar.trim(),
    detail: e.detail,
    requestId: e.requestId,
    cause: e.cause,
  );
}
