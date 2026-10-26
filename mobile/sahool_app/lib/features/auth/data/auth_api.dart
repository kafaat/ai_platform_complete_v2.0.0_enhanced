// SAHOOL — features/auth/data/auth_api.dart
// الدخول، المصادقة الثنائيّة (TOTP)، واستعادة كلمة المرور. العقود تطابق
// services/auth (mfa_setup/activate/disable، password_reset) والويب. يملكه وكيل
// ميزة الدخول. الخروج يبقى في ApiService.logout (تفكيك الجلسة عقدٌ مُثبَّت
// تفحصه بوّابة CI) ويُستدعى من هنا عبر [logout].
import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/response_shape.dart';
import 'package:sahool_app/services/api_service.dart';
import 'package:sahool_app/services/auth_service.dart';

/// يُرمى من [AuthApi.login] حين تكون كلمة المرور صحيحة لكن الحساب يتطلّب رمز
/// المصادقة الثنائيّة (TOTP). يكتشفها الـUI ليكشف حقل الرمز ثمّ يعيد النداء مع
/// `mfaCode`. عقد الخادم: 401 + ترويسة `X-MFA-Required: true`.
class MfaRequiredException implements Exception {
  const MfaRequiredException();
  @override
  String toString() =>
      'MfaRequiredException: يتطلّب الحساب رمز المصادقة الثنائيّة';
}

class AuthApi {
  AuthApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final AuthApi instance = AuthApi();
  final ApiClient _client;

  /// تسجيل الدخول (POST /auth/login). يحفظ التوكنات + الملفّ في التخزين الآمن.
  /// صدق: يفشل برسالة واضحة إن نقص رمز الوصول (لا جلسة زائفة).
  ///
  /// المصادقة الثنائيّة: دخول بلا [mfaCode] لحساب مفعِّل لها ⇒ 401 + ترويسة
  /// `X-MFA-Required: true` ⇒ [MfaRequiredException]. رمز خاطئ ⇒ 401 عاديّ
  /// (ApiException بنوع unauthorized).
  Future<Map<String, dynamic>> login(
    String email,
    String password, {
    String? mfaCode,
  }) async {
    final dynamic body;
    try {
      body = await _client.send(
        'POST',
        '/auth/login',
        data: {
          'email': email,
          'password': password,
          if (mfaCode != null) 'mfa_code': mfaCode,
        },
        authenticated: false,
      );
    } on ApiException catch (e) {
      final cause = e.cause;
      if (e.statusCode == 401 && cause is DioException) {
        // ترويسات Dio تُقرأ بمفتاح صغير الأحرف بصرف النظر عن حالة الإرسال.
        final mfa = cause.response?.headers.value('x-mfa-required');
        if (mfa?.toLowerCase() == 'true') throw const MfaRequiredException();
      }
      rethrow;
    }
    final data = asJsonMap(body);
    final access = data['access_token'] as String?;
    if (access == null) {
      throw const FormatException('استجابة الدخول بلا رمز وصول');
    }
    await AuthService.instance.saveToken(
      access,
      refresh: data['refresh_token'] as String?,
      profile: {
        'user_id': data['user_id'],
        'role': data['role'],
        'full_name': data['full_name'],
        'tenant_id': data['tenant_id'],
      },
    );
    return data;
  }

  /// يبدأ اقتران MFA (POST /auth/mfa/setup). يولّد سرّاً ويُعيد
  /// `secret` + `provisioning_uri` (otpauth://) لعرضهما/توليد QR. لا يُفعّل MFA
  /// بعد — التفعيل يتطلّب تأكيد أوّل رمز عبر [mfaActivate]. السرّ يُعرَض مرّة
  /// واحدة فقط خادميّاً (لا يُعاد بعدها). يردّ الخادم 400 إن كان MFA مفعّلاً سلفاً.
  Future<Map<String, dynamic>> mfaSetup() async {
    final r = await _client.post('/auth/mfa/setup');
    return asJsonMap(r);
  }

  /// يفعّل MFA بعد تأكيد أوّل رمز صحيح (POST /auth/mfa/activate).
  /// [code] رمز TOTP من تطبيق المصادقة. رمز خاطئ ⇒ 400 (يُعرَض سطريّاً).
  Future<Map<String, dynamic>> mfaActivate(String code) async {
    final r = await _client.post('/auth/mfa/activate', data: {'code': code});
    return asJsonMap(r);
  }

  /// يعطّل MFA (POST /auth/mfa/disable). يتطلّب رمزاً صحيحاً حاليّاً (لا يُعطّله
  /// توكن مسروق بلا الجهاز). [code] رمز TOTP. خطأ/تعطيل بلا تفعيل ⇒ 400.
  Future<Map<String, dynamic>> mfaDisable(String code) async {
    final r = await _client.post('/auth/mfa/disable', data: {'code': code});
    return asJsonMap(r);
  }

  Future<void> requestPasswordReset(String email) async {
    await _client.send(
      'POST',
      '/auth/password-reset/request',
      data: {'email': email},
      authenticated: false,
    );
  }

  Future<void> confirmPasswordReset(String token, String newPassword) async {
    await _client.send(
      'POST',
      '/auth/password-reset/confirm',
      data: {'token': token, 'new_password': newPassword},
      authenticated: false,
    );
  }

  /// خروج كامل: إلغاء رمز الدفع، إبطال الجلسة خادميّاً، ثمّ تفكيك محلّيّ
  /// (WebSocket، الكاش، تنظيفات الميزات عبر SessionScope، التوكنات).
  Future<void> logout() => ApiService.instance.logout(
    refreshToken: AuthService.instance.refreshToken,
  );
}
