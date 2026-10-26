// SAHOOL — features/documents/data/documents_api.dart
// نقاط الوثائق (document:view / document:manage) — بيانات وصفيّة فقط.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

class DocumentsApi {
  DocumentsApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final DocumentsApi instance = DocumentsApi();
  final ApiClient _client;

  Future<List<Map<String, dynamic>>> listDocuments({
    String? category,
    String? fieldId,
  }) async {
    final q = <String, dynamic>{
      if (category != null) 'category': category,
      if (fieldId != null) 'field_id': fieldId,
    };
    return asJsonList(
      await _client.get('/api/v1/documents', query: q.isEmpty ? null : q),
    );
  }

  Future<Map<String, dynamic>> createDocument(
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/documents',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );
}
