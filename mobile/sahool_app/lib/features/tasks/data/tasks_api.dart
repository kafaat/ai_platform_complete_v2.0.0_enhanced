// SAHOOL — features/tasks/data/tasks_api.dart
// نقاط المهام اليوميّة/الموزّعة. يملكه وكيل المهام.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

class TasksApi {
  TasksApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final TasksApi instance = TasksApi();
  final ApiClient _client;

  /// GET /api/v1/tasks — يردّ إمّا {tasks:[...]} أو قائمة مباشرة.
  Future<List<Map<String, dynamic>>> fetchTasks({String? fieldId}) async {
    final data = await _client.get(
      '/api/v1/tasks',
      query: (fieldId != null && fieldId.isNotEmpty)
          ? {'field_id': fieldId}
          : null,
    );
    if (data is Map && data['tasks'] is List) {
      return (data['tasks'] as List)
          .whereType<Map>()
          .map((e) => e.cast<String, dynamic>())
          .toList();
    }
    return asJsonList(data);
  }

  /// تغيير حالة مهمّة: بدء/إنجاز (PATCH /api/v1/tasks/{id}). تعيين حالة
  /// idempotent بطبيعته، والمفتاح يجعل إعادة المحاولة على 502/504 آمنة صراحةً.
  Future<Map<String, dynamic>> updateTaskStatus(
    String taskId,
    String status, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.patch(
      '/api/v1/tasks/$taskId',
      data: {'status': status},
      idempotencyKey: idempotencyKey,
    ),
  );
}
