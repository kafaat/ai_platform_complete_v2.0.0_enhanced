// SAHOOL — features/equipment/data/equipment_api.dart
// نقاط المعدّات والصيانة (equipment:view / equipment:manage). يملكه وكيل المعدّات.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

class EquipmentApi {
  EquipmentApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final EquipmentApi instance = EquipmentApi();
  final ApiClient _client;

  Future<List<Map<String, dynamic>>> getEquipment() async =>
      asJsonList(await _client.get('/api/v1/equipment'));

  Future<Map<String, dynamic>> createEquipment(
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/equipment',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );

  Future<List<Map<String, dynamic>>> getMaintenance(String equipmentId) async =>
      asJsonList(
        await _client.get('/api/v1/equipment/$equipmentId/maintenance'),
      );

  Future<Map<String, dynamic>> logMaintenance(
    String equipmentId,
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/equipment/$equipmentId/maintenance',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );
}
