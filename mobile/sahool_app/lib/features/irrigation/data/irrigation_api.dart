// SAHOOL — features/irrigation/data/irrigation_api.dart
// نقاط الريّ التشغيليّ (irrigation:view / irrigation:manage). يملكه وكيل الريّ.
// setValveState يسجّل النيّة فقط؛ التشغيل الفيزيائيّ عبر HIL (موافقة بشريّة).
// أوامر المشغِّلات مجمَّدة بقرار المالك (GATE-01): لا يُضاف هنا مسار أمرٍ جديد؛
// القراءات (التوصية، الدفتر، الكفاءة) والخطّة الافتراضيّة ليست أوامر عتاد.
//
// الدوالّ العامّة append-only في الموجة الثانية (الحقول تقرأ listSchedules).
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

class IrrigationApi {
  IrrigationApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final IrrigationApi instance = IrrigationApi();
  final ApiClient _client;

  Future<List<Map<String, dynamic>>> listValves() async =>
      asJsonList(await _client.get('/api/v1/irrigation/valves'));

  Future<Map<String, dynamic>> createValve(
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/irrigation/valves',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );

  Future<Map<String, dynamic>> setValveState(
    String valveId,
    String status, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/irrigation/valves/$valveId/state',
      data: {'status': status},
      idempotencyKey: idempotencyKey,
    ),
  );

  Future<List<Map<String, dynamic>>> listSchedules({String? fieldId}) async =>
      asJsonList(
        await _client.get(
          '/api/v1/irrigation/schedules',
          query: fieldId != null ? {'field_id': fieldId} : null,
        ),
      );

  Future<Map<String, dynamic>> createSchedule(
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/irrigation/schedules',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );

  /// حقول المستأجر لمنتقي حقل الجدول (D5) — GET /api/v1/fields بالعميل نفسه، قراءة فقط.
  Future<List<Map<String, dynamic>>> listFields() async =>
      asJsonList(await _client.get('/api/v1/fields'));

  Future<void> deleteSchedule(
    String scheduleId, {
    IdempotencyKey? idempotencyKey,
  }) async {
    await _client.delete(
      '/api/v1/irrigation/schedules/$scheduleId',
      idempotencyKey: idempotencyKey,
    );
  }

  // ── «هل أروي اليوم؟» — مرشَّح توصية من حالة الحقل (irrigation_recommendation.py) ──

  /// POST /api/v1/fields/{id}/irrigation-recommendation بجسم فارغ: الخادم يجلب
  /// الطقس والاستنزاف والتربة بنفسه (المسار الأساسيّ). قراءةٌ لا تُنشئ شيئاً
  /// (`submit_to_decision` يبقى false)، فلا مفتاح idempotency. الاستجابة اتّحاد
  /// على `status`: recommendation_ready / insufficient_data / inconsistent_state /
  /// dependency_unavailable.
  Future<Map<String, dynamic>> getFieldRecommendation(
    String fieldId,
  ) async => asJsonMap(
    await _client.post(
      '/api/v1/fields/${Uri.encodeComponent(fieldId)}/irrigation-recommendation',
      data: const <String, dynamic>{},
    ),
  );

  // ── دفتر المياه اليوميّ (water_ledger.py) ─────────────────────────────

  static String waterLedgerPath(String fieldId) =>
      '/api/v1/fields/${Uri.encodeComponent(fieldId)}/water-ledger';

  /// GET …/water-ledger?from=&to= ⇒ `{field_id, entries, total, note_ar?}`.
  Future<Map<String, dynamic>> listWaterLedger(
    String fieldId, {
    String? from,
    String? to,
  }) async => asJsonMap(
    await _client.get(
      waterLedgerPath(fieldId),
      query: {if (from != null) 'from': from, if (to != null) 'to': to},
    ),
  );

  /// POST …/water-ledger — upsert قيد يوم كامل (الخادم يستبدل كلّ أعمدة اليوم).
  /// المستدعي مسؤول عن دمج قيم اليوم القائمة قبل الإرسال (انظر WaterLedgerCubit).
  Future<Map<String, dynamic>> upsertWaterLedger(
    String fieldId,
    Map<String, dynamic> body, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      waterLedgerPath(fieldId),
      data: body,
      idempotencyKey: idempotencyKey,
    ),
  );

  /// GET …/water-efficiency ⇒ `{field_id, period, efficiency, note_ar?}`.
  Future<Map<String, dynamic>> getWaterEfficiency(
    String fieldId, {
    String? from,
    String? to,
  }) async => asJsonMap(
    await _client.get(
      '/api/v1/fields/${Uri.encodeComponent(fieldId)}/water-efficiency',
      query: {if (from != null) 'from': from, if (to != null) 'to': to},
    ),
  );

  // ── خطّة ريّ افتراضيّة (irrigation_plan.py) — حساب بمدخلات المستخدم ──

  /// POST /api/v1/irrigation-plan. حسابٌ لا يُشغّل شيئاً؛ قد يُدام كأثر نَسَب.
  Future<Map<String, dynamic>> computeIrrigationPlan(
    Map<String, dynamic> body, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/irrigation-plan',
      data: body,
      idempotencyKey: idempotencyKey,
    ),
  );
}
