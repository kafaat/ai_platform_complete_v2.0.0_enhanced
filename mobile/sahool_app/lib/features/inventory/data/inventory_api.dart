// SAHOOL — features/inventory/data/inventory_api.dart
// نقاط المخزون (inventory:view / inventory:manage). يملكه وكيل المخزون.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'inventory_models.dart';

class InventoryApi {
  InventoryApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final InventoryApi instance = InventoryApi();
  final ApiClient _client;

  Future<List<Map<String, dynamic>>> getInventoryItems() async =>
      asJsonList(await _client.get('/api/v1/inventory/items'));

  Future<List<Map<String, dynamic>>> getExpiringBatches({
    int days = 30,
  }) async => asJsonList(
    await _client.get('/api/v1/inventory/expiring', query: {'days': days}),
  );

  Future<Map<String, dynamic>> createInventoryItem(
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/inventory/items',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );

  Future<Map<String, dynamic>> addInventoryBatch(
    String itemId,
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/inventory/items/$itemId/batches',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );

  // ── نسخ مُنمَّطة (إضافيّة؛ الدوالّ أعلاه باقية لمستهلكيها) ──────────────

  /// العناصر مع الكمّيّة الكلّيّة وعلَم «منخفض» المحسوبَين خادميّاً.
  Future<List<InventoryItem>> listItems() async =>
      (await getInventoryItems()).map(InventoryItem.fromJson).toList();

  /// دفعات كمّيّتها > 0 تنتهي خلال [days] يوماً (والمنتهية فعلاً)، الأقرب أوّلاً.
  /// الخادم يقيّد [days] بـ1..3650.
  Future<List<ExpiringBatch>> listExpiring({int days = 30}) async =>
      (await getExpiringBatches(
        days: days,
      )).map(ExpiringBatch.fromJson).toList();
}
