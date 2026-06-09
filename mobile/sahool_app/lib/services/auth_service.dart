// SAHOOL v9.1.0 — lib/services/auth_service.dart
// Fixes: F12(SecureStorage), F13(expiry check), M02(biometric hint)
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthService {
  static final AuthService instance = AuthService._internal();
  AuthService._internal();

  // F12: Use flutter_secure_storage instead of SharedPreferences
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

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

  // F13: Check JWT expiry
  bool _isTokenExpired(String token) {
    try {
      final parts = token.split('.');
      if (parts.length != 3) return true;
      final payload = json.decode(
        utf8.decode(base64Url.decode(base64Url.normalize(parts[1])))
      ) as Map<String, dynamic>;
      final exp = payload['exp'] as int?;
      if (exp == null) return false;
      // Expire 60s early to avoid edge cases
      return DateTime.now().millisecondsSinceEpoch ~/ 1000 > exp - 60;
    } catch (_) { return true; }
  }

  bool get isAuthenticated => _token != null && !_isTokenExpired(_token!);
  String? get userRole => _userProfile?['role'] as String?;
  String? get tenantId => _userProfile?['tenant_id'] as String?;

  // M02: Biometric auth — غير مُنفّذ بعد. يفشل مغلقاً (false) لئلّا يمنح
  // تأكيداً أمنيّاً زائفاً. أيّ مستدعٍ يُرفَض حتّى يُنفَّذ فعليّاً بـlocal_auth.
  bool get isBiometricAvailable => false;  // الواجهة تُخفي الخيار حتّى التنفيذ

  Future<bool> authenticateWithBiometric() async {
    // غير مُنفّذ — للتنفيذ بحزمة local_auth:
    //   final auth = LocalAuthentication();
    //   return auth.authenticate(localizedReason: 'تحقق من هويتك للدخول إلى SAHOOL');
    // حتّى ذلك الحين: false (fail-closed) لا true (لا تأكيد زائف).
    return false;
  }
}
