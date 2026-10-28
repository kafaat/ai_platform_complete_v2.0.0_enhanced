import 'dart:convert';

import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

/// An immutable submitted observation, separate from the editable form.
/// Quantity remains unknown unless the operator supplies evidence.
class IrrigationObservation {
  IrrigationObservation(Map<String, dynamic> payload)
      : body = Map<String, dynamic>.unmodifiable(
          jsonDecode(jsonEncode(payload)) as Map<String, dynamic>,
        );

  final Map<String, dynamic> body;
  String get id => body['observation_id'] as String;

  Map<String, dynamic> envelope(String taskId) => Map<String, dynamic>.unmodifiable({
        'task_id': taskId,
        'irrigation_observation': body,
      });

  OutboxOp toOutbox(String taskId, String fieldId) => OutboxOp(
        kind: 'task_irrigation_observation',
        method: 'POST',
        path: IrrigationObservationsApi.observationsPath,
        body: envelope(taskId),
        idempotencyKey: id,
        fieldId: fieldId,
        labelAr: 'إفادة ريّ للمهمّة — ليست إنجازاً أو قيد ماء',
      );
}

class IrrigationObservationsApi {
  IrrigationObservationsApi([ApiClient? client])
      : _client = client ?? ApiClient.instance;
  final ApiClient _client;

  static const observationsPath = '/api/v1/observations';
  static const historyPath = '/api/v1/tasks';

  Future<List<Map<String, dynamic>>> history(String taskId) async =>
      asWrappedJsonList(await _client.get(
        historyPath, query: {'irrigation_task_id': taskId},
      ), const ['irrigation_observations']);

  Future<List<Map<String, dynamic>>> executions(String fieldId) async =>
      asJsonList(await _client.get(
        '/api/v1/irrigation/engineering/manual-executions',
        query: {'field_id': fieldId},
      ));

  Future<Map<String, dynamic>> submit(
    String taskId,
    IrrigationObservation observation,
  ) async =>
      asJsonMap(await _client.post(
        observationsPath,
        data: observation.envelope(taskId),
        idempotencyKey: IdempotencyKey(observation.id),
      ));
}

/// Validation before any persistence/network operation. Blank values are null,
/// never a fabricated zero volume. The server remains authoritative.
String? validateIrrigationObservation(Map<String, dynamic> body, {DateTime? now}) {
  if (!{'farmer_task', 'field_inspection'}.contains(body['source'])) {
    return 'اختر مصدر الإفادة.';
  }
  final stamp = body['occurred_at'];
  final date = stamp is String ? DateTime.tryParse(stamp) : null;
  if (date == null || stamp is! String ||
      !RegExp(r'(Z|[+-]\d{2}:\d{2})$').hasMatch(stamp)) {
    return 'وقت المشاهدة يجب أن يتضمن المنطقة الزمنية.';
  }
  if (date.isAfter((now ?? DateTime.now()).toUtc().add(const Duration(seconds: 60)))) {
    return 'وقت المشاهدة لا يمكن أن يكون في المستقبل.';
  }
  if ((body['execution_id'] as String? ?? '').isEmpty) {
    return 'اختر تنفيذ ريّ مرتبطاً بهذا الحقل.';
  }
  final outcome = body['outcome'];
  if (!{'irrigated', 'not_irrigated', 'unknown'}.contains(outcome)) {
    return 'اختر نتيجة المشاهدة.';
  }
  final method = body['quantity_method'];
  if (!{'meter', 'estimated_flow', 'declared_volume', 'unknown'}.contains(method)) {
    return 'اختر طريقة تحديد الكمية.';
  }
  for (final key in [
    'meter_start_m3', 'meter_end_m3', 'flow_m3_h', 'duration_minutes',
    'interruptions_minutes', 'volume_m3', 'irrigated_area_ha',
  ]) {
    final value = body[key];
    if (value != null &&
        (value is! num || !value.isFinite || value < 0)) {
      return 'القيم الرقمية يجب أن تكون محدودة وغير سالبة.';
    }
  }
  final present = {
    for (final key in ['meter_start_m3', 'meter_end_m3', 'flow_m3_h',
      'duration_minutes', 'volume_m3'])
      if (body[key] != null) key,
  };
  final required = <String, Set<String>>{
    'meter': {'meter_start_m3', 'meter_end_m3'},
    'estimated_flow': {'flow_m3_h', 'duration_minutes'},
    'declared_volume': {'volume_m3'},
    'unknown': {},
  }[method]!;
  if (present.length != required.length || !present.containsAll(required)) {
    return 'استخدم أدلة طريقة كمية واحدة فقط دون خلط الطرق.';
  }
  if (method != 'estimated_flow' && (body['interruptions_minutes'] ?? 0) != 0) {
    return 'الانقطاعات تتطلب طريقة التدفق والمدة.';
  }
  if (body['irrigated_area_ha'] != null && body['irrigated_area_ha'] == 0) {
    return 'المساحة المروية يجب أن تكون موجبة أو تترك فارغة.';
  }
  if (method == 'meter') {
    final start = body['meter_start_m3'] as num?;
    final end = body['meter_end_m3'] as num?;
    if (start == null || end == null || end < start) {
      return 'أدخل قراءتي العداد، والنهاية لا تقل عن البداية.';
    }
  }
  if (method == 'estimated_flow') {
    final flow = body['flow_m3_h'] as num?;
    final duration = body['duration_minutes'] as num?;
    final interruptions = body['interruptions_minutes'] as num? ?? 0;
    if (flow == null || flow <= 0 || duration == null || duration <= 0 ||
        interruptions >= duration) {
      return 'أدخل التدفق والمدة، والانقطاعات لا تتجاوز المدة.';
    }
  }
  if (method == 'declared_volume' && body['volume_m3'] == null) {
    return 'أدخل الحجم المصرّح به بالمتر المكعب.';
  }
  if (outcome != 'irrigated' &&
      (method != 'unknown' || body['irrigated_area_ha'] != null)) {
    return 'لا تُسجّل كمية ريّ لنتيجة غير مؤكدة أو لم يحدث فيها ريّ.';
  }
  return null;
}
