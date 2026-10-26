// SAHOOL — features/profile/data/profile_api.dart
// الحساب والإعدادات. يملكه وكيل ميزة الملفّ الشخصيّ.
// تفضيلات الإشعار تُدار خادميّاً في services/sahool-platform/api/routers/notifications.py
// (GET/PUT /api/v1/notifications/preferences، PUT يستبدل الصفّ كاملاً).
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_shape.dart';

class ProfileApi {
  ProfileApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final ProfileApi instance = ProfileApi();
  final ApiClient _client;

  /// هويّة المستخدم الحاليّ من الخادم (GET /api/v1/me، routers/me.py):
  /// `user_id`، `tenant_id`، `role`، `name_ar`، `ai_policy_envelope`. لا نقطة
  /// لتعديل الملفّ الشخصيّ في الخادم بعد — القراءة فقط.
  Future<Map<String, dynamic>> getMe() async =>
      asJsonMap(await _client.get('/api/v1/me'));

  /// تفضيلات الإشعار الحاليّة (لا صفّ ⇒ الخادم يردّ افتراضيّات: كلّ القنوات معطّلة).
  Future<Map<String, dynamic>> getNotificationPreferences() async =>
      asJsonMap(await _client.get('/api/v1/notifications/preferences'));

  /// يستبدل التفضيلات كاملةً. أرسل الصفّ المقروء بعد تعديله، لا حقلاً منفرداً،
  /// وإلّا مُسحت القنوات الأخرى.
  Future<Map<String, dynamic>> putNotificationPreferences(
    Map<String, dynamic> prefs,
  ) async => asJsonMap(
    await _client.put('/api/v1/notifications/preferences', data: prefs),
  );
}
