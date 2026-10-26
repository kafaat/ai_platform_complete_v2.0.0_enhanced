// خادم أنشطة مزيّف: الحقول، الأنشطة لكلّ حقل، الخطّ الزمنيّ.
import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/features/activities/data/activities_api.dart';
import 'package:sahool_app/features/activities/data/activity_writer.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../../core/fake_http.dart';
import '../tasks/tasks_fakes.dart' show FakeOutbox;

export '../tasks/tasks_fakes.dart' show FakeOutbox;

Map<String, dynamic> activityJson(
  String id, {
  String field = 'f1',
  String type = 'spraying',
  String? performed = '2026-10-25',
  String? scheduled,
  String? title,
  String? notes,
}) => {
  'activity_id': id,
  'field_id': field,
  'season_id': null,
  'activity_type': type,
  'title_ar': title,
  'details': {'notes': ?notes},
  'scheduled_for': scheduled,
  'performed_on': performed,
  'status': performed != null ? 'done' : 'planned',
  'created_at': '2026-10-25T06:00:00+00:00',
};

class FakeActivitiesServer {
  List<Map<String, dynamic>> fields = [
    {'field_id': 'f1', 'name': 'حقل الوادي'},
    {'field_id': 'f2', 'name': 'حقل البنّ'},
  ];
  final Map<String, List<Map<String, dynamic>>> activities = {
    'f1': [],
    'f2': [],
  };
  Map<String, dynamic> timeline = {
    'field_id': 'f1',
    'total_events': 0,
    'events': <Map<String, dynamic>>[],
    'category_counts': <String, int>{},
    'degraded': false,
  };
  final Map<String, FakeReply> failFieldList = {};
  FakeReply? Function(RequestOptions o)? postReply;
  int _seq = 0;

  late final FakeAdapter adapter = FakeAdapter(_handle);
  late final ApiClient client = testClient(
    adapter,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  );

  List<RecordedRequest> get posts =>
      adapter.requests.where((r) => r.method == 'POST').toList();

  Future<FakeReply> _handle(RequestOptions o) async {
    if (o.path == '/api/v1/fields') return FakeReply(200, fields);
    final m = RegExp(
      r'^/api/v1/fields/([^/]+)/(activities|unified-timeline)$',
    ).firstMatch(o.path);
    if (m == null) return const FakeReply(404, {'detail': 'x'});
    final fid = Uri.decodeComponent(m.group(1)!);
    if (m.group(2) == 'unified-timeline') return FakeReply(200, timeline);
    if (o.method == 'GET') {
      return failFieldList[fid] ?? FakeReply(200, activities[fid] ?? []);
    }
    final custom = postReply?.call(o);
    if (custom != null) return custom;
    final body = Map<String, dynamic>.from(o.data as Map);
    final row = {
      'activity_id': 'act_${++_seq}',
      'field_id': fid,
      'season_id': null,
      'activity_type': body['activity_type'],
      'title_ar': body['title_ar'],
      'details': body['details'] ?? {},
      'scheduled_for': body['scheduled_for'],
      'performed_on': body['performed_on'],
      'status': body['performed_on'] != null ? 'done' : 'planned',
    };
    activities.putIfAbsent(fid, () => []).insert(0, row);
    return FakeReply(201, row);
  }

  ActivitiesApi get api => ActivitiesApi(client);
  FieldsApi get fieldsApi => FieldsApi(client);

  ActivityWriter writer({
    OfflineOutbox? outbox,
    bool online = true,
    PendingActivities? pending,
  }) => ActivityWriter(
    api: api,
    outbox: outbox ?? FakeOutbox(),
    isOnline: () => online,
    pending: pending ?? PendingActivities(),
    clock: () => DateTime(2026, 10, 26, 9),
  );
}
