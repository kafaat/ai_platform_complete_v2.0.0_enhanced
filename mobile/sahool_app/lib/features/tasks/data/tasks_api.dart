// SAHOOL — features/tasks/data/tasks_api.dart
// نقاط المهام اليوميّة/الموزّعة. يملكه وكيل المهام.
//
// الخادم (services/sahool-platform/api/routers/tasks.py) يملك نقطتين فقط:
//   GET   /api/v1/tasks?field_id=&limit=&offset=  ⇒ {tasks:[...], total, limit, next_cursor}
//   PATCH /api/v1/tasks/{task_id}  {status?, notes?, photo_url?}  ⇒ TaskSummary
// لا إنشاء يدويّ (POST /api/v1/tasks غير موجود): المهام تُنشأ من خطط العمليّات
// (POST /api/v1/weather/tasks/from-operation-plan) ومن التوصيات.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'field_task.dart';

class TasksApi {
  TasksApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final TasksApi instance = TasksApi();
  final ApiClient _client;

  /// أقصى صفحة يقبلها الخادم (tasks.py يقصر limit إلى 1..500).
  static const int maxPageSize = 500;

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

  /// صفحة مُرقَّمة من المهام (الأعلى أولويّةً ثمّ الأقرب موعداً). بتمرير
  /// [limit] يردّ الخادم `total` و`next_cursor` فتعرف الواجهة أنّها لم ترَ
  /// كلّ المهام بدل افتراض ذلك.
  Future<TasksPage> fetchTaskPage({
    String? fieldId,
    int limit = 200,
    int offset = 0,
  }) async {
    final data = asJsonMap(
      await _client.get(
        '/api/v1/tasks',
        query: {
          if (fieldId != null && fieldId.isNotEmpty) 'field_id': fieldId,
          'limit': limit.clamp(1, maxPageSize),
          'offset': offset < 0 ? 0 : offset,
        },
      ),
    );
    final rows = asWrappedJsonList(data, const ['tasks']);
    final total = data['total'];
    final cursor = data['next_cursor'];
    return TasksPage(
      tasks: rows.map(FieldTask.fromJson).toList(),
      total: total is num ? total.toInt() : null,
      nextCursor: cursor?.toString(),
    );
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

  /// تحديث جزئيّ لمهمّة بجسم [body] كما يقبله TaskUpdateRequest
  /// ({status?, notes?, photo_url?}). يُرجِع المهمّة المحدَّثة من الخادم.
  Future<FieldTask> updateTask(
    String taskId,
    Map<String, dynamic> body, {
    IdempotencyKey? idempotencyKey,
  }) async => FieldTask.fromJson(
    asJsonMap(
      await _client.patch(
        taskPath(taskId),
        data: body,
        idempotencyKey: idempotencyKey,
      ),
    ),
  );

  /// المسار نفسه للإرسال المباشر ولعمليّة صندوق الإرسال.
  static String taskPath(String taskId) =>
      '/api/v1/tasks/${Uri.encodeComponent(taskId)}';
}
