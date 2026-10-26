// أدوات اختبار المهام: خادم مزيّف للمهام والحقول، وصندوق إرسال مزيّف.
import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/tasks/data/tasks_api.dart';
import 'package:sahool_app/features/tasks/presentation/tasks_cubit.dart';

import '../../core/fake_http.dart';

class FakeOutbox implements OfflineOutbox {
  FakeOutbox({this.accept = true});
  bool accept;
  final List<OutboxOp> ops = [];

  @override
  Future<OutboxReceipt> enqueue(OutboxOp op) async {
    ops.add(op);
    return accept
        ? const OutboxReceipt.queued()
        : const OutboxReceipt.notQueued('offline_queue_unavailable');
  }

  @override
  Stream<int> get pendingCount => Stream<int>.value(ops.length);
}

Map<String, dynamic> taskJson(
  String id, {
  String status = 'pending',
  String? date = '2026-10-26',
  String field = 'f1',
  String type = 'irrigation',
  String? notes,
  String? assignedTo,
}) => {
  'task_id': id,
  'field_id': field,
  'task_type': type,
  'priority': 3,
  'status': status,
  'recommended_date': date,
  'estimated_duration_min': 120,
  'estimated_cost_usd': null,
  'assigned_to': assignedTo,
  'notes': notes,
  'photo_url': null,
  'completed_at': null,
  'created_at': '2026-10-20T08:00:00+00:00',
};

/// خادم مهامّ في الذاكرة: GET يُرجِع [tasks]، PATCH يحدّثها ويُرجِعها، إلّا إن
/// ضُبط [patchReply] (لمحاكاة فشل).
class FakeTasksServer {
  FakeTasksServer(List<Map<String, dynamic>> tasks)
    : tasks = [for (final t in tasks) Map.of(t)];

  final List<Map<String, dynamic>> tasks;
  FakeReply? Function(RequestOptions o)? patchReply;
  FakeReply? listReply;

  /// إن ضُبط: PATCH ينتظره قبل الردّ (لمحاكاة طلب بطيء).
  Future<void>? patchGate;
  final List<Map<String, dynamic>> listQueries = [];
  int? total;
  String? nextCursor;
  List<Map<String, dynamic>> fields = [
    {'field_id': 'f1', 'name': 'حقل الوادي'},
    {'field_id': 'f2', 'name': 'حقل البنّ'},
  ];

  late final FakeAdapter adapter = FakeAdapter(_handle);
  late final ApiClient client = testClient(
    adapter,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  );

  List<RecordedRequest> get patches =>
      adapter.requests.where((r) => r.method == 'PATCH').toList();
  List<RecordedRequest> get taskGets => adapter.requests
      .where((r) => r.method == 'GET' && r.path == '/api/v1/tasks')
      .toList();

  Future<FakeReply> _handle(RequestOptions o) async {
    if (o.path == '/api/v1/fields') return FakeReply(200, fields);
    if (o.path == '/api/v1/tasks' && o.method == 'GET') {
      listQueries.add(Map.of(o.queryParameters));
      return listReply ??
          FakeReply(200, {
            'tasks': tasks,
            'total': total ?? tasks.length,
            'limit': o.queryParameters['limit'],
            'next_cursor': nextCursor,
          });
    }
    if (o.method == 'PATCH' && o.path.startsWith('/api/v1/tasks/')) {
      if (patchGate != null) await patchGate;
      final custom = patchReply?.call(o);
      if (custom != null) return custom;
      final id = Uri.decodeComponent(o.path.split('/').last);
      final row = tasks.firstWhere((t) => t['task_id'] == id);
      final body = Map<String, dynamic>.from(o.data as Map);
      row.addAll(body);
      if (body['status'] == 'completed') {
        row['completed_at'] = '2026-10-26T09:30:00+00:00';
      }
      return FakeReply(200, row);
    }
    return const FakeReply(404, {'detail': 'not found'});
  }

  TasksCubit cubit({
    FakeOutbox? outbox,
    bool online = true,
    bool Function()? isOnline,
    String? userId,
    Duration undoWindow = const Duration(milliseconds: 20),
  }) => TasksCubit(
    api: TasksApi(client),
    fieldsApi: FieldsApi(client),
    outbox: outbox ?? FakeOutbox(),
    isOnline: isOnline ?? () => online,
    userId: userId,
    clock: () => DateTime(2026, 10, 26, 10),
    undoWindow: undoWindow,
  );
}
