// SAHOOL — features/lab_sampling/data/lab_sampling_api.dart
// نقاط ميزة «عيّنات المختبر». يملكه وكيل الميزة.
//
// المصدر (services/sahool-platform/api/routers/soil_sampling.py):
//   GET  /api/v1/lab/samples?field_id=          → [lab_samples row]
//   POST /api/v1/lab/samples                    → row (FIELD_EDIT؛ لا يقرأ Idempotency-Key بعد)
//   POST /api/v1/lab/samples/{id}/transition    → row (target_status + location/condition_notes/seal_id)
//   GET  /api/v1/fields/{id}/lab-context        → أعلام القرار (لا قيم)
//   GET  /api/v1/soil-sampling/protocol         → خطوات/تحذيرات/عمق/عدد عيّنات فرعيّة
//   GET  /api/v1/fields/{id}/soil-lab-tests     → fields.py — سجلّ فحوص التربة القديم (result JSON حرّ)
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'lab_models.dart';

class LabSamplingApi {
  LabSamplingApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final LabSamplingApi instance = LabSamplingApi();
  final ApiClient _client;

  /// مسار إنشاء العيّنة — يستعمله صندوق الإرسال دون اتّصال كما هو.
  static const String samplesPath = '/api/v1/lab/samples';

  Future<List<LabSample>> listSamples({String? fieldId}) async {
    final r = await _client.get(
      samplesPath,
      query: {if (fieldId != null) 'field_id': fieldId},
    );
    return asJsonList(r).map(LabSample.fromJson).toList();
  }

  Future<LabSample> createSample(
    Map<String, dynamic> body, {
    required IdempotencyKey idempotencyKey,
  }) async {
    final r = await _client.post(
      samplesPath,
      data: body,
      idempotencyKey: idempotencyKey,
    );
    return LabSample.fromJson(asJsonMap(r));
  }

  Future<LabSample> transition(
    String sampleId,
    LabSampleStatus target, {
    required IdempotencyKey idempotencyKey,
    String? location,
    String? conditionNotes,
    String? sealId,
  }) async {
    final r = await _client.post(
      '$samplesPath/${Uri.encodeComponent(sampleId)}/transition',
      data: {
        'target_status': target.wire,
        if (location != null) 'location': location,
        if (conditionNotes != null) 'condition_notes': conditionNotes,
        if (sealId != null) 'seal_id': sealId,
      },
      idempotencyKey: idempotencyKey,
    );
    return LabSample.fromJson(asJsonMap(r));
  }

  Future<LabContext> getLabContext(String fieldId) async {
    final r = await _client.get(
      '/api/v1/fields/${Uri.encodeComponent(fieldId)}/lab-context',
    );
    return LabContext.fromJson(asJsonMap(r));
  }

  /// بروتوكول أخذ عيّنة التربة (إرشاد عامّ من الخادم).
  Future<Map<String, dynamic>> getProtocol({
    double? areaHa,
    String purpose = 'general',
  }) async {
    final r = await _client.get(
      '/api/v1/soil-sampling/protocol',
      query: {
        if (areaHa != null && areaHa > 0) 'area_ha': areaHa,
        'purpose': purpose,
      },
    );
    return asJsonMap(r);
  }

  Future<List<Map<String, dynamic>>> listSoilLabTests(String fieldId) async {
    final r = await _client.get(
      '/api/v1/fields/${Uri.encodeComponent(fieldId)}/soil-lab-tests',
    );
    return asJsonList(r);
  }
}
