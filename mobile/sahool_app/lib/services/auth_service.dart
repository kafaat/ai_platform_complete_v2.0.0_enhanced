// SAHOOL v9.1.0 — lib/services/auth_service.dart
// Fixes: F12(SecureStorage), F13(expiry check), M02(biometric hint)
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';
import '../utils/jwt.dart';

class AuthService {
  static final AuthService instance = AuthService._internal();
  AuthService._internal();

  // F12: Use flutter_secure_storage instead of SharedPreferences
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  // M02: local_auth integration. مفتاح الإعداد المُخزَّن بأمان (opt-in).
  final LocalAuthentication _localAuth = LocalAuthentication();
  static const _biometricPrefKey = 'biometric_enabled';

  String? _token;
  String? _refreshToken;
  String? _userId;
  Map<String, dynamic>? _userProfile;

  String? get token => _token;
  String? get refreshToken => _refreshToken;
  String? get userId => _userId;
  Map<String, dynamic>? get userProfile => _userProfile;

  Future<void> loadSaved() async {
    try {
      _token        = await _storage.read(key: 'access_token');
      _refreshToken = await _storage.read(key: 'refresh_token');
      _userId       = await _storage.read(key: 'user_id');
      final profile = await _storage.read(key: 'user_profile');
      if (profile != null) {
        _userProfile = json.decode(profile) as Map<String, dynamic>;
      }

      // F13: Validate token expiry on load
      if (_token != null && _isTokenExpired(_token!)) {
        debugPrint('Token expired on load — clearing auth');
        await clearAuth();
      }
    } catch (e) {
      debugPrint('Error loading auth: $e');
      await clearAuth();
    }
  }

  Future<void> saveToken(String token, {String? refresh, Map<String, dynamic>? profile}) async {
    _token = token;
    await _storage.write(key: 'access_token', value: token);
    if (refresh != null) {
      _refreshToken = refresh;
      await _storage.write(key: 'refresh_token', value: refresh);
    }
    if (profile != null) {
      _userProfile = profile;
      _userId = profile['user_id']?.toString() ?? profile['sub']?.toString();
      await _storage.write(key: 'user_id', value: _userId);
      await _storage.write(key: 'user_profile', value: json.encode(profile));  // F12: jsonEncode
    }
  }

  Future<void> clearAuth() async {
    _token = _refreshToken = _userId = _userProfile = null;
    await _storage.deleteAll();
  }

  // F13: Check JWT expiry — مصدر واحد للحقيقة (utils/jwt.dart) يفشل-مغلقاً.
  // سابقاً كان توكن بلا exp يُعدّ «غير منتهٍ» (fail-open) — ثغرة: جلسة لا تنتهي.
  // الآن يطابق ApiService والاختبارات: بلا exp/مشوّه ⇒ منتهٍ.
  bool _isTokenExpired(String token) => isJwtExpired(token);

  bool get isAuthenticated => _token != null && !_isTokenExpired(_token!);
  String? get userRole => _userProfile?['role'] as String?;
  String? get tenantId => _userProfile?['tenant_id'] as String?;

  // M02: Biometric auth عبر local_auth. fail-closed بالكامل: أيّ تعذّر أو رفض
  // أو غياب جهاز ⇒ false (لا تأكيد أمنيّ زائف)، ولا يُرمى استثناء أبداً.

  /// هل الجهاز يدعم البصمة/الوجه ومُسجَّل بياناتٍ حيويّة؟ (لإظهار/إخفاء الخيار)
  Future<bool> get isBiometricAvailable async {
    try {
      final supported = await _localAuth.isDeviceSupported();
      final canCheck = await _localAuth.canCheckBiometrics;
      return supported && canCheck;
    } on PlatformException catch (e) {
      debugPrint('Biometric availability check failed: ${e.code}');
      return false;
    } catch (e) {
      debugPrint('Biometric availability check failed: $e');
      return false;
    }
  }

  /// إعداد المستخدم: هل فعّل الدخول بالبصمة؟ (opt-in؛ افتراضيّاً معطّل).
  Future<bool> get isBiometricEnabled async {
    try {
      return (await _storage.read(key: _biometricPrefKey)) == 'true';
    } catch (_) {
      return false;
    }
  }

  /// تفعيل/تعطيل الدخول بالبصمة (يُستدعى من شاشة الإعدادات).
  Future<void> setBiometricEnabled(bool enabled) async {
    await _storage.write(
      key: _biometricPrefKey,
      value: enabled ? 'true' : 'false',
    );
  }

  /// يطلب التحقّق الحيويّ (بصمة/وجه). يفشل مغلقاً: يردّ false عند عدم التوفّر
  /// أو الرفض أو أيّ خطأ — لا يُرمى استثناء. لا يُطالِب إن لم يفعّله المستخدم.
  Future<bool> authenticateWithBiometric({
    String reason = 'تحقّق من هويتك للدخول إلى SAHOOL',
  }) async {
    try {
      // مُعطَّل من المستخدم (لا نفرضه) أو غير متوفّر ⇒ false بلا مُطالبة.
      if (!await isBiometricEnabled) return false;
      if (!await isBiometricAvailable) return false;
      return await _localAuth.authenticate(
        localizedReason: reason,
        options: const AuthenticationOptions(
          biometricOnly: true,
          stickyAuth: true,
        ),
      );
    } on PlatformException catch (e) {
      // جهاز غير مُهيَّأ/مقفل/إلخ — fail-closed
      debugPrint('Biometric auth failed: ${e.code}');
      return false;
    } catch (e) {
      debugPrint('Biometric auth error: $e');
      return false;
    }
  }
}
