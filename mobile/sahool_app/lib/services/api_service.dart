// SAHOOL — lib/services/api_service.dart
//
// واجهة الجلسة والعقود المُثبَّتة. كانت هذه الطبقة تحمل كلّ نقاط التطبيق (1059
// سطراً)؛ انقسمت الآن إلى:
//   • lib/core/network/api_client.dart — Dio الوحيد: المصادقة، تحديث التوكن،
//     إعادة المحاولة، Idempotency-Key، تحويل الأخطاء إلى ApiException.
//   • lib/features/<x>/data/<x>_api.dart — نقاط كلّ ميزة في ملفّها.
//
// ما بقي هنا يبقى لسببين: (1) تفكيك الجلسة والمزامنة دون اتّصال شأنان مشتركان لا
// تملكهما ميزة، و(2) بوّابات CI خارج التطبيق تقرأ هذا الملفّ بالمسار وتفحص نصّه:
//   • scripts/ci/mobile_contract_gate.py: logout (finally + WebSocketService.dispose
//     + clearCache)، وsyncOfflineOperations بلا tenantId من العميل.
//   • tests/mobile/test_phase11_mobile_offline_sync_runtime.py: مسارات
//     /api/ai-agronomist/chat و/api/v1/sync/manifest و/api/v1/sync/status.
//   • tests_v9/test_field_forms_mobile_runtime_wiring.py: `Dio get dio => _dio`.
// لا تُضِف نقاط ميزة هنا. المالك الوحيد لدالّة [askAgent] هو وكيل المستشار.
import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/core/network/response_shape.dart';
import 'package:sahool_app/core/session/session_scope.dart';
import 'package:sahool_app/services/auth_service.dart';
import 'package:sahool_app/services/websocket_service.dart';

class ApiService {
  ApiService._internal();
  static final ApiService instance = ApiService._internal();

  ApiClient get _client => ApiClient.instance;
  late final Dio _dio = _client.dio;

  /// عميل Dio القانونيّ المشترك؛ يحافظ على JWT والتتبّع وسياسات retry.
  Dio get dio => _dio;

  /// يمسح كاش الاستجابات (مُنطَّق بالمستخدم) — يُستدعى عند الخروج.
  void clearCache() => ResponseCache.instance.clear();

  // ── المستشار (مسار مُثبَّت؛ يملكه وكيل المستشار) ──────────────────

  /// Runtime AI Advisor الحقيقيّ عبر ai_agronomist (البوّابة: /api/ai-agronomist/chat
  /// ← /v1/chat). العقد من services/ai_agronomist/main.py (AdvisorQuery): `question`
  /// إلزاميّ (min_length=1، max_length=4000)، و`field_id` اختياريّ يربط الإجابة
  /// بحالة الحقل القانونيّة. لا يُرسَل tenant_id: البوّابة تحقنه من JWT. كان العميل
  /// يرسل `message`/`query` فيُرفَض بـ422 دائماً؛ أُزيلا. الاستجابة تُقرأ من
  /// `answer_ar` (انظر features/advisor/data/advisor_models.dart).
  ///
  /// مهلة الاستقبال 120ث (= مهلة البوّابة) لأنّ التوليد بطيء على شبكة ضعيفة. بلا
  /// مفتاح منع تكرار: النداء يسجّل حدث تدقيق خادميّاً، فلا يُعاد تلقائيّاً.
  /// [client] للاختبار فقط (عميل بمحوّل مزيّف)؛ الافتراضيّ العميل المشترك.
  Future<Map<String, dynamic>> askAgent(
    String query, {
    String? fieldId,
    ApiClient? client,
  }) async {
    final r = await (client ?? _client).send(
      'POST',
      '/api/ai-agronomist/chat',
      data: {
        'question': query,
        if (fieldId != null && fieldId.isNotEmpty) 'field_id': fieldId,
        'language': 'ar',
        'final_k': 5,
      },
      receiveTimeout: const Duration(seconds: 120),
    );
    return asJsonMap(r);
  }

  // ── المزامنة دون اتّصال (/api/v1/sync) ─────────────────────────────

  Future<Map<String, dynamic>> getSyncManifest() async =>
      asJsonMap(await _client.get('/api/v1/sync/manifest'));

  Future<Map<String, dynamic>> getSyncStatus() async =>
      asJsonMap(await _client.get('/api/v1/sync/status'));

  Future<Map<String, dynamic>> syncOfflineOperations(
    List<Map<String, dynamic>> operations, {
    String? since,
  }) async {
    // Tenant isolation is derived from the JWT on the server. The mobile client must
    // not send tenant_id in the body; doing so can create drift or a future tenant
    // spoofing footgun if a backend handler accidentally trusts request JSON.
    final r = await _client.post(
      '/api/v1/sync',
      query: since != null ? {'since': since} : null,
      data: {'operations': operations},
    );
    return asJsonMap(r);
  }

  // ── رمز الدفع (FCM) ────────────────────────────────────────────────
  // عقد الخادم: لا مسار تسجيل رمز مفرد — push_token يُدار ضمن تفضيلات الإشعار
  // (PUT /api/v1/notifications/preferences، upsert يستبدل الصفّ كاملاً). لذا نقرأ
  // التفضيلات أوّلاً ثمّ نعيد إرسالها معدَّلة، كي لا نمحو القنوات الأخرى.

  /// يسجّل رمز جهاز FCM للمستخدم الحاليّ. إن تعذّرت قراءة التفضيلات نتوقّف
  /// (نرمي الخطأ) بدل إرسال صفّ فارغ يمحو بريد/SMS/واتساب المُفعَّلة سابقاً.
  Future<void> registerPushToken(String token) =>
      _updatePushPreferences(enabled: true, token: token);

  /// يُلغي رمز الدفع لهذا الجهاز (عند الخروج)، فلا يتلقّى الجهاز المشترك
  /// تنبيهات المستخدم السابق.
  Future<void> unregisterPushToken() =>
      _updatePushPreferences(enabled: false, token: null);

  Future<void> _updatePushPreferences({
    required bool enabled,
    required String? token,
  }) async {
    final prefs = asJsonMap(
      await _client.get('/api/v1/notifications/preferences'),
    );
    await _client.put(
      '/api/v1/notifications/preferences',
      data: {...prefs, 'push_enabled': enabled, 'push_token': token},
    );
  }

  // ── الخروج ───────────────────────────────────────────────────────

  /// خروج كامل. الخادم أوّلاً (إلغاء رمز الدفع ثمّ إبطال رمز التحديث) بأفضل
  /// جهد، ثمّ تفكيك محلّيّ يجري **دائماً** (finally) حتّى بلا شبكة:
  /// WebSocket ← الكاش ← تنظيفات الميزات (SessionScope) ← التوكنات.
  Future<void> logout({String? refreshToken}) async {
    final ending = SessionEnd(
      tenantId: AuthService.instance.tenantId,
      userId: AuthService.instance.userId,
    );
    try {
      // سقف زمنيّ للجزء الشبكيّ: بلا شبكة لا ينتظر المستخدم مهلتَي اتّصال.
      await Future(() async {
        try {
          await unregisterPushToken();
        } catch (_) {
          // لا رمز مسجَّل/لا شبكة — لا يمنع الخروج.
        }
        await _client.post(
          '/auth/logout',
          data: refreshToken != null ? {'refresh_token': refreshToken} : {},
        );
      }).timeout(const Duration(seconds: 10));
    } catch (_) {
      // Logout must remain local fail-closed even when the server is unreachable.
    } finally {
      await WebSocketService.instance.dispose();
      clearCache();
      await SessionScope.instance.endSession(ending);
      await AuthService.instance.clearAuth();
    }
  }
}
