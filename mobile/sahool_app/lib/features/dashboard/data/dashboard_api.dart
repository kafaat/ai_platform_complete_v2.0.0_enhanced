// SAHOOL — features/dashboard/data/dashboard_api.dart
// لوحة المعلومات المُجمَّعة والتنبيهات. يملكه وكيل ميزة لوحة المعلومات.
//
// GET /api/v1/indicators/dashboard يردّ {kpis, alerts, fields_summary, note_ar}
// (services/sahool-platform/api/analytics_shapers.py). البوّابة لا تملك موقع
// /indicators/ القديم — لذا المسار الكامل.
//
// دمج الطلبات: عند الإقلاع تطلب عدّة شاشات اللوحة في اللحظة نفسها (الغلاف لفحص
// «صفر حقول»، اللوحة، …). [getDashboard] يدمج الطلبات المتزامنة لنفس الحساب في
// طلب واحد؛ [getDashboardCached] يضيف كاش 5 دقائق مُنطَّقاً بالمستأجِر+المستخدم.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/in_flight.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/core/network/response_shape.dart';
import 'package:sahool_app/services/auth_service.dart';

class DashboardApi {
  DashboardApi([ApiClient? client, ResponseCache? cache])
    : _client = client ?? ApiClient.instance,
      _cache = cache ?? ResponseCache.instance;
  static final DashboardApi instance = DashboardApi();
  final ApiClient _client;
  final ResponseCache _cache;
  final InFlight<Map<String, dynamic>> _inFlight = InFlight();

  // أمان: المفتاح مُنطَّق بالمستأجِر+المستخدم، فلا يرى حسابٌ لوحةَ حسابٍ سابق
  // على نفس الجهاز ضمن مهلة الكاش.
  String get _scopeKey {
    final tenant = AuthService.instance.tenantId ?? '_';
    final user = AuthService.instance.userId ?? '_';
    return 'dashboard:$tenant:$user';
  }

  Future<Map<String, dynamic>> getDashboard() => _inFlight.run(
    _scopeKey,
    () async => asJsonMap(await _client.get('/api/v1/indicators/dashboard')),
  );

  Future<Map<String, dynamic>> getDashboardCached({
    bool forceRefresh = false,
  }) async {
    final key = _scopeKey;
    if (!forceRefresh) {
      final cached = _cache.get(key);
      if (cached is Map<String, dynamic>) return cached;
    }
    final result = await getDashboard();
    _cache.set(key, result);
    return result;
  }

  /// PATCH /api/v1/alerts/{id}/acknowledge (يطابق الويب).
  Future<void> acknowledgeAlert(
    String alertId, {
    IdempotencyKey? idempotencyKey,
  }) async {
    await _client.patch(
      '/api/v1/alerts/$alertId/acknowledge',
      idempotencyKey: idempotencyKey,
    );
  }
}
