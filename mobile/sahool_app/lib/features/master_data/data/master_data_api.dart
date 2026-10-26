// SAHOOL — features/master_data/data/master_data_api.dart
// نقاط البيانات المرجعيّة (master_data:view / master_data:manage).
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

class MasterDataApi {
  MasterDataApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final MasterDataApi instance = MasterDataApi();
  final ApiClient _client;

  Future<List<Map<String, dynamic>>> getMasterData(String category) async =>
      asJsonList(
        await _client.get('/api/v1/master-data', query: {'category': category}),
      );

  Future<Map<String, dynamic>> createMasterDataEntry(
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/master-data',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );
}
