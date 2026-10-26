// SAHOOL — features/farms/data/farms_api.dart
// نقاط المزارع (أب الحقول). تطابق api/routers/farms.py والويب (farmsApi).
// صدق: 503 (DB) / 403 (RBAC) تُرمى ApiException ليعرض الـUI حالة صادقة.
// يملكه وكيل ميزة المزارع وحده؛ أضِف نقاط المزارع هنا لا في ApiService.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

class FarmsApi {
  FarmsApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final FarmsApi instance = FarmsApi();
  final ApiClient _client;

  /// قائمة مزارع المستأجِر (GET /api/v1/farms، مُرشّحة بـRLS).
  /// كلّ عنصر: {farm_id, name, location, area_ha, region, ...}.
  Future<List<Map<String, dynamic>>> listFarms() async =>
      asJsonList(await _client.get('/api/v1/farms'));

  /// ينشئ مزرعة (POST /api/v1/farms). [payload] يطابق FarmCreateRequest:
  /// name لازم؛ البقيّة اختياريّة. يردّ {farm_id, name, ...}.
  Future<Map<String, dynamic>> createFarm(
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/farms',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );

  /// حقول مزرعة (GET /api/v1/farms/{id}/fields): [{field_id, name, area_ha,
  /// crop, soil_type}]. 404 = مزرعة ليست ضمن المستأجِر (لا «بلا حقول»).
  Future<List<Map<String, dynamic>>> listFarmFields(String farmId) async =>
      asJsonList(await _client.get('/api/v1/farms/$farmId/fields'));

  /// أولويّات المزرعة التشغيليّة (GET /api/v1/farms/{id}/priority-queue):
  /// {items:[{id, type, field_id, title_ar, severity, ...}], degraded,
  /// warning_ar}. العناصر من التنبيهات والمهام المخزّنة فقط.
  Future<Map<String, dynamic>> getFarmPriorityQueue(
    String farmId, {
    int limit = 100,
  }) async => asJsonMap(
    await _client.get(
      '/api/v1/farms/$farmId/priority-queue',
      query: {'limit': limit},
    ),
  );
}
