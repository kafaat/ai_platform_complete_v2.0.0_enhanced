// SAHOOL — features/dashboard/data/dashboard_api.dart
// لوحة المعلومات المُجمَّعة والتنبيهات وقراءات شاشة «اليوم». يملكه وكيل ميزة
// لوحة المعلومات.
//
// GET /api/v1/indicators/dashboard يردّ {kpis, alerts, fields_summary, note_ar}
// (services/sahool-platform/api/analytics_shapers.py). البوّابة لا تملك موقع
// /indicators/ القديم — لذا المسار الكامل.
//
// دمج الطلبات: عند الإقلاع تطلب عدّة شاشات اللوحة في اللحظة نفسها (الغلاف لفحص
// «صفر حقول»، اللوحة، …). [getDashboard] يدمج الطلبات المتزامنة لنفس الحساب في
// طلب واحد ويملأ الكاش؛ [getDashboardCached] يقرأ كاش 5 دقائق مُنطَّقاً
// بالمستأجِر+المستخدم، فتكفي الشاشةَ حمولةٌ جلبها الغلاف قبلها.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/in_flight.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/core/network/response_shape.dart';
import 'package:sahool_app/services/auth_service.dart';

/// حمولة اللوحة مع وقت جلبها الفعليّ من الخادم (لا وقت قراءتها من الكاش).
class DashboardFetch {
  const DashboardFetch(this.data, this.fetchedAt);
  final Map<String, dynamic> data;
  final DateTime fetchedAt;
}

class DashboardApi {
  DashboardApi([ApiClient? client, ResponseCache? cache, this.scopeOverride])
    : _client = client ?? ApiClient.instance,
      _cache = cache ?? ResponseCache.instance;
  static final DashboardApi instance = DashboardApi();
  final ApiClient _client;
  final ResponseCache _cache;
  final InFlight<Map<String, dynamic>> _inFlight = InFlight();
  final Map<String, DateTime> _fetchedAt = {};

  /// للاختبارات: نطاق ثابت بدل جلسة AuthService.
  final String? scopeOverride;

  // أمان: المفتاح مُنطَّق بالمستأجِر+المستخدم، فلا يرى حسابٌ لوحةَ حسابٍ سابق
  // على نفس الجهاز ضمن مهلة الكاش.
  String get scopeKey {
    if (scopeOverride != null) return 'dashboard:$scopeOverride';
    final tenant = AuthService.instance.tenantId ?? '_';
    final user = AuthService.instance.userId ?? '_';
    return 'dashboard:$tenant:$user';
  }

  Future<Map<String, dynamic>> getDashboard() {
    final key = scopeKey;
    return _inFlight.run(key, () async {
      final data = asJsonMap(await _client.get('/api/v1/indicators/dashboard'));
      _cache.set(key, data);
      _fetchedAt[key] = DateTime.now();
      return data;
    });
  }

  Future<Map<String, dynamic>> getDashboardCached({
    bool forceRefresh = false,
  }) async => (await fetchDashboard(forceRefresh: forceRefresh)).data;

  /// مثل [getDashboardCached] لكن يعيد وقت الجلب الفعليّ («آخر تحديث»).
  Future<DashboardFetch> fetchDashboard({bool forceRefresh = false}) async {
    final key = scopeKey;
    if (!forceRefresh) {
      final cached = _cache.get(key);
      final at = _fetchedAt[key];
      if (cached is Map<String, dynamic> && at != null) {
        return DashboardFetch(cached, at);
      }
    }
    final data = await getDashboard();
    return DashboardFetch(data, _fetchedAt[key] ?? DateTime.now());
  }

  /// PATCH /api/v1/alerts/{id}/acknowledge (يطابق الويب). FIELD_EDIT على الخادم.
  Future<void> acknowledgeAlert(
    String alertId, {
    IdempotencyKey? idempotencyKey,
  }) async {
    await _client.patch(
      '/api/v1/alerts/${Uri.encodeComponent(alertId)}/acknowledge',
      idempotencyKey: idempotencyKey,
    );
  }

  /// حقول مزرعة (GET /api/v1/farms/{id}/fields، routers/farms.py:139):
  /// [{field_id, name, area_ha, crop, soil_type}]. 404 لمزرعة ليست للمستأجِر.
  Future<List<Map<String, dynamic>>> listFarmFields(String farmId) async =>
      asJsonList(
        await _client.get(
          '/api/v1/farms/${Uri.encodeComponent(farmId)}/fields',
        ),
      );

  /// طابور أولويّات المزرعة (GET /api/v1/farms/{id}/priority-queue،
  /// routers/field_priority_queue.py:178): {scope, farm_id, items[], degraded,
  /// warning_ar, note_ar}. العناصر من alerts/field_tasks فقط، مرتّبة بالخادم.
  Future<Map<String, dynamic>> getFarmPriorityQueue(
    String farmId, {
    int limit = 30,
  }) async => asJsonMap(
    await _client.get(
      '/api/v1/farms/${Uri.encodeComponent(farmId)}/priority-queue',
      query: {'limit': limit},
    ),
  );

  /// ملخّص طقس زراعيّ لنقطة (GET /api/v1/weather/field-weather-summary،
  /// routers/weather.py): {sample, operations{spraying,irrigation,...},
  /// alerts_ar, cache_state, cache_age_s, upstream_error, source}.
  Future<Map<String, dynamic>> getWeatherSummary(
    double lat,
    double lon,
  ) async => asJsonMap(
    await _client.get(
      '/api/v1/weather/field-weather-summary',
      query: {'lat': lat, 'lon': lon},
    ),
  );
}
