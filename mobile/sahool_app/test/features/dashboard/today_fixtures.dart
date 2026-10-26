// حمولات بالشكل الحقيقيّ لمنتِجي الخادم (لا أشكال مخترعة) + خادم مزيّف يردّ
// بحسب المسار عبر FakeAdapter نفسه الذي يختبر ApiClient الحقيقيّ.
//
// المصادر: analytics_shapers.py `_shape_indicators_dashboard`،
// alert_models.py AlertSummary، api_models.py TaskListResponse، routers/farms.py،
// routers/field_priority_queue.py، routers/weather.py field-weather-summary.
import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_api.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_snapshot_store.dart';
import 'package:sahool_app/features/dashboard/presentation/dashboard_cubit.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/tasks/data/tasks_api.dart';

import '../../core/fake_http.dart';

final DateTime kNow = DateTime(2026, 10, 26, 9);

Map<String, dynamic> realDashboard() => {
  'kpis': [
    {
      'id': 'fields_total',
      'category': 'operations',
      'name_ar': 'إجماليّ الحقول',
      'value': 3,
      'unit': 'حقل',
      'status': 'good',
    },
    {
      'id': 'area_total',
      'category': 'operations',
      'name_ar': 'إجماليّ المساحة',
      'value': 12.75,
      'unit': 'هـ',
      'status': 'good',
    },
    {
      'id': 'active_seasons',
      'category': 'operations',
      'name_ar': 'حقول بموسم نشط',
      'value': 2,
      'unit': 'حقل',
      'status': 'good',
    },
    {
      'id': 'open_alerts',
      'category': 'operations',
      'name_ar': 'تنبيهات مفتوحة',
      'value': 2,
      'unit': 'تنبيه',
      'status': 'critical',
    },
  ],
  'alerts': [
    {
      'alert_id': 'alr_warn',
      'field_id': 'f1',
      'alert_type': 'low_moisture',
      'severity': 'warning',
      'title_ar': 'رطوبة التربة منخفضة',
      'message_ar': 'الرطوبة أقلّ من العتبة منذ يومين.',
      'status': 'active',
      'created_at': '2026-10-26T04:00:00+00:00',
    },
    {
      'alert_id': 'alr_frost',
      'field_id': 'f2',
      'alert_type': 'frost_risk',
      'severity': 'critical',
      'title_ar': 'خطر صقيع الليلة',
      'message_ar': null,
      'status': 'active',
      'created_at': '2026-10-26T02:00:00+00:00',
    },
  ],
  'fields_summary': [
    {
      'field_id': 'f1',
      'field_name': 'حقل البنّ الشرقيّ',
      'crop': 'بنّ',
      'area_ha': 4.5,
      'has_active_season': true,
      'geometry': {
        'type': 'Polygon',
        'coordinates': [
          [
            [44.0, 15.0],
            [44.2, 15.0],
            [44.2, 15.2],
            [44.0, 15.2],
            [44.0, 15.0],
          ],
        ],
      },
    },
    {
      'field_id': 'f2',
      'field_name': 'حقل الذرة',
      'crop': 'ذرة رفيعة',
      'area_ha': 8.25,
      'has_active_season': true,
      'geometry': null,
    },
    {
      'field_id': 'f3',
      'field_name': 'الحقل الغربيّ',
      'crop': null,
      'area_ha': 0.0,
      'has_active_season': false,
      'geometry': null,
    },
  ],
  'note_ar':
      'عدّادات حيّة من جداولك — المؤشّرات الطيفيّة لكلّ حقل من شاشة الأقمار.',
};

Map<String, dynamic> realTasks() => {
  'tasks': [
    {
      'task_id': 't_today',
      'field_id': 'f1',
      'task_type': 'irrigation',
      'priority': 2,
      'status': 'pending',
      'recommended_date': '2026-10-26',
    },
    {
      'task_id': 't_late',
      'field_id': 'f3',
      'task_type': 'scouting',
      'priority': 1,
      'status': 'in_progress',
      'recommended_date': '2026-10-24',
    },
    {
      'task_id': 't_future',
      'field_id': 'f2',
      'task_type': 'harvest',
      'priority': 1,
      'status': 'pending',
      'recommended_date': '2026-11-20',
    },
    {
      'task_id': 't_done',
      'field_id': 'f2',
      'task_type': 'spraying',
      'priority': 1,
      'status': 'completed',
      'recommended_date': '2026-10-25',
    },
  ],
  'total': null,
  'limit': null,
  'next_cursor': null,
};

List<Map<String, dynamic>> realFarms() => [
  {
    'farm_id': 'farm1',
    'name': 'مزرعة الوادي',
    'location': null,
    'area_ha': 12.75,
    'centroid_lat': 15.35,
    'centroid_lon': 44.2,
  },
];

Map<String, dynamic> realPriorityQueue() => {
  'scope': 'farm',
  'farm_id': 'farm1',
  'items': [
    {
      'id': 'alr_frost',
      'type': 'alert',
      'field_id': 'f2',
      'title_ar': 'خطر صقيع الليلة',
      'severity': 'critical',
    },
    {
      'id': 't_late',
      'type': 'task',
      'field_id': 'f3',
      'title_ar': 'مهمة تفتيش',
      'severity': 'high',
    },
  ],
  'degraded': false,
  'warning_ar': null,
  'note_ar': 'تُبنى الأولوية من تنبيهات ومهام مخزنة فقط؛ لا توجد عناصر مصطنعة.',
};

Map<String, dynamic> realWeather() => {
  'location': {'lat': 15.35, 'lon': 44.2},
  'time': 'now',
  'model': 'best_match',
  'sample': {
    'temperature_2m_c': 24.4,
    'relative_humidity_2m_pct': 52,
    'wind_speed_10m_kmh': 9,
    'precipitation_mm': 0,
  },
  'operations': {
    'spraying': {
      'operation': 'spraying',
      'score': 1.0,
      'suitability': 'optimal',
    },
    'irrigation': {
      'operation': 'irrigation',
      'score': 0.67,
      'suitability': 'acceptable',
    },
  },
  'alerts_ar': <String>[],
  'cache_state': 'live',
  'cache_age_s': 0,
  'upstream_error': null,
  'source': 'open-meteo+sahool-rules',
};

/// خادم مزيّف: [overrides] تستبدل ردّ مسار بعينه.
FakeAdapter fakeBackend({
  Map<String, FakeReply Function()> overrides = const {},
  Duration delay = Duration.zero,
}) => FakeAdapter((RequestOptions o) async {
  if (delay > Duration.zero) await Future<void>.delayed(delay);
  final o2 = overrides[o.path];
  if (o2 != null) return o2();
  return switch (o.path) {
    '/api/v1/indicators/dashboard' => FakeReply(200, realDashboard()),
    '/api/v1/tasks' => FakeReply(200, realTasks()),
    '/api/v1/farms' => FakeReply(200, realFarms()),
    '/api/v1/farms/farm1/fields' => const FakeReply(200, [
      {'field_id': 'f1', 'name': 'حقل البنّ الشرقيّ'},
      {'field_id': 'f2', 'name': 'حقل الذرة'},
      {'field_id': 'f3', 'name': 'الحقل الغربيّ'},
    ]),
    '/api/v1/farms/farm1/priority-queue' => FakeReply(200, realPriorityQueue()),
    '/api/v1/weather/field-weather-summary' => FakeReply(200, realWeather()),
    _ when o.path.endsWith('/acknowledge') => const FakeReply(200, {}),
    _ => const FakeReply(404, {'detail': 'not found'}),
  };
});

const FakeReply Function() offline = _offline;
FakeReply _offline() => const FakeReply.fail(DioExceptionType.connectionError);

class TodayHarness {
  TodayHarness(this.adapter, {DashboardSnapshotStore? snapshots})
    : snapshots = snapshots ?? MemoryDashboardSnapshotStore() {
    final client = testClient(
      adapter,
      MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
    );
    api = DashboardApi(client, ResponseCache(), 'tenant:user');
    tasks = TasksApi(client);
    farms = FarmsApi(client);
  }

  final FakeAdapter adapter;
  final DashboardSnapshotStore snapshots;
  late final DashboardApi api;
  late final TasksApi tasks;
  late final FarmsApi farms;

  DashboardCubit cubit({Stream<Object?>? events}) => DashboardCubit(
    api: api,
    tasksApi: tasks,
    farmsApi: farms,
    snapshots: snapshots,
    alertEvents: events,
    eventDebounce: const Duration(milliseconds: 10),
  );
}
