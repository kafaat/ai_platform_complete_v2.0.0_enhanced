// SAHOOL — features/irrigation/data/irrigation_api.dart
// نقاط الريّ التشغيليّ (irrigation:view / irrigation:manage). يملكه وكيل الريّ.
// setValveState يسجّل النيّة فقط؛ التشغيل الفيزيائيّ عبر HIL (موافقة بشريّة).
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

  Future<void> deleteSchedule(String scheduleId) async {
    await _client.delete('/api/v1/irrigation/schedules/$scheduleId');
  }
}
