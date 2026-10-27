// SAHOOL v9.1.0 — lib/services/auth_service.dart
// Fixes: F12(SecureStorage), F13(expiry check), M02(biometric hint)
//
// جيل الجلسة (D2): كلّ تغيير لهويّة الجلسة — استعادة من القرص، دخول (أو تبديل
// حساب)، خروج، مسح — يرفع [sessionGeneration]. تجديد الرمز يحمل الجيل الذي بدأ
// فيه، والحفظ/المسح المشروطان ([saveRefreshedToken]/[clearIfGeneration])
// يرفضانه إن تغيّر الجيل: ردّ متأخّر لجلسة سابقة لا يحفظ رموزاً ولا يمسح جلسة
// أحدث.
//
// سباق الفحص ثمّ الحفظ: الفحص وتعديل الحالة في الذاكرة يجريان في خطوة متزامنة
// واحدة (بلا await بينهما)، ثمّ تُكتَب القيم الملتقَطة إلى التخزين الآمن عبر
// سلسلة واحدة بترتيب الاستدعاء ([_serialized]). كان الحفظ يكتب الرمزين على
// خطوتين بينهما await، فيُكتَب رمز تحديث جلسة سابقة فوق رمز الجلسة الجديدة.
import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';
import 'package:sahool_app/core/utils/jwt.dart';

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

  int _generation = 0;

  /// جيل الجلسة: يرتفع عند الاستعادة والدخول وتبديل الحساب والخروج والمسح، ولا
  /// يتغيّر بتجديد رمز الوصول داخل الجلسة نفسها.
  int get sessionGeneration => _generation;

  /// هويّة مالك الجلسة (المستأجر/المستخدم) كما حفظها الدخول.
  String? get sessionOwner =>
      _userId == null ? null : '${tenantId ?? ''}/$_userId';

  /// آخر عمليّة تخزين معلّقة، أو null إن لم يبقَ شيء (لا يُحتفَظ بـFuture
  /// مكتمل: Future.value يُكمِل في Zone إنشائه، فلا يُحمَل بين Zones).
  Future<void>? _tail;

  /// يُسلسل كتابات التخزين الآمن بترتيب الاستدعاء (لا تتداخل كتابتان).
  Future<T> _serialized<T>(Future<T> Function() body) {
    final previous = _tail;
    final run = previous == null ? body() : previous.then((_) => body());
    final tail = run.then<void>((_) {}, onError: (Object _) {});
    _tail = tail;
    tail.whenComplete(() {
      if (identical(_tail, tail)) _tail = null;
    });
    return run;
  }

  Completer<void>? _restore;

  /// يعلن أنّ استعادة الجلسة من القرص قادمة (main قبل runApp): رابط عميق يُبنى
  /// قبل أن تبدأ AuthGate [loadSaved] ينتظرها بدل أن يحكم على جلسة لم تُقرأ.
  void expectRestore() {
    final current = _restore;
    if (current == null || current.isCompleted) _restore = Completer<void>();
  }

  /// غير null ما دامت استعادة مُعلَنة أو جارية لم تنتهِ؛ المسارات الخاصّة
  /// تنتظره. null ⇒ لا استعادة معلّقة (الحكم بالحالة الحاليّة).
  Future<void>? get pendingRestore {
    final current = _restore;
    return current == null || current.isCompleted ? null : current.future;
  }

  Future<void> loadSaved() async {
    expectRestore();
    final restore = _restore!;
    final generation = ++_generation;
    var clear = false;
    try {
      await _serialized(() async {
        final token = await _storage.read(key: 'access_token');
        final refresh = await _storage.read(key: 'refresh_token');
        final userId = await _storage.read(key: 'user_id');
        final profile = await _storage.read(key: 'user_profile');
        final decoded = profile == null
            ? null
            : json.decode(profile) as Map<String, dynamic>;
        // دخول/خروج وقع أثناء القراءة ⇒ حالته أحدث ممّا قُرئ.
        if (_generation != generation) return;
        _token = token;
        _refreshToken = refresh;
        _userId = userId;
        _userProfile = decoded;
      });

      // F13: Validate token expiry on load. رمز وصول منتهٍ (عمره 60 دقيقة) لا
      // يُنهي الجلسة ما دام رمز التحديث (30 يوماً) محفوظاً: AuthGate يجدّده عبر
      // ApiClient.refreshAccessToken. كان المسح هنا يحذف رمز تحديث صالحاً فيُجبَر
      // المستخدم على الدخول كلّ ساعة. نمسح فقط حين لا يبقى ما يُجدِّد الجلسة.
      if (_token != null && _isTokenExpired(_token!) && _refreshToken == null) {
        debugPrint('Token expired on load and no refresh token — clearing auth');
        clear = true;
      }
    } catch (e) {
      debugPrint('Error loading auth: $e');
      clear = true;
    }
    try {
      if (clear && _generation == generation) await clearAuth();
    } finally {
      if (!restore.isCompleted) restore.complete();
    }
  }

  /// يبدأ جلسة (دخول أو تبديل حساب): جيل جديد، فيُرفَض أيّ تجديد بدأ قبله.
  Future<void> saveToken(String token, {String? refresh, Map<String, dynamic>? profile}) {
    _generation++;
    return _write(token, refresh: refresh, profile: profile);
  }

  /// يحفظ رمزاً مُجدَّداً **فقط** إن بقيت الجلسة هي [generation]. الفحص وتعديل
  /// الذاكرة متزامنان؛ الكتابة تُسلسَل خلف كلّ تغيير سبقها. false ⇒ الردّ لجلسة
  /// سابقة ولم يُحفَظ شيء.
  Future<bool> saveRefreshedToken(int generation, String token,
      {String? refresh}) async {
    if (generation != _generation) return false;
    await _write(token, refresh: refresh);
    return true;
  }

  Future<void> _write(String token,
      {String? refresh, Map<String, dynamic>? profile}) {
    _token = token;
    if (refresh != null) _refreshToken = refresh;
    String? userId;
    if (profile != null) {
      _userProfile = profile;
      _userId = userId =
          profile['user_id']?.toString() ?? profile['sub']?.toString();
    }
    return _serialized(() async {
      await _storage.write(key: 'access_token', value: token);
      if (refresh != null) {
        await _storage.write(key: 'refresh_token', value: refresh);
      }
      if (profile != null) {
        await _storage.write(key: 'user_id', value: userId);
        await _storage.write(key: 'user_profile', value: json.encode(profile));  // F12: jsonEncode
      }
    });
  }

  Future<void> clearAuth() {
    _generation++;
    _token = _refreshToken = _userId = _userProfile = null;
    // احذف مفاتيح الجلسة فقط؛ هويّة جهاز النماذج يجب أن تبقى ثابتة
    // عبر تسجيل الخروج، وكذلك تفضيل البصمة المستقل عن الجلسة.
    return _serialized(() async {
      await Future.wait([
        _storage.delete(key: 'access_token'),
        _storage.delete(key: 'refresh_token'),
        _storage.delete(key: 'user_id'),
        _storage.delete(key: 'user_profile'),
      ]);
    });
  }

  /// يمسح الجلسة **فقط** إن بقيت [generation] (رفض الخادم لرمز تحديثها). رفض
  /// متأخّر لجلسة سابقة لا يمسح جلسة أحدث. false ⇒ لم يُمسَح شيء.
  Future<bool> clearIfGeneration(int generation) async {
    if (generation != _generation) return false;
    await clearAuth();
    return true;
  }

  // F13: Check JWT expiry — مصدر واحد للحقيقة (utils/jwt.dart) يفشل-مغلقاً.
  // سابقاً كان توكن بلا exp يُعدّ «غير منتهٍ» (fail-open) — ثغرة: جلسة لا تنتهي.
  // الآن يطابق ApiService والاختبارات: بلا exp/مشوّه ⇒ منتهٍ.
  bool _isTokenExpired(String token) => isJwtExpired(token);

  bool get isAuthenticated => _token != null && !_isTokenExpired(_token!);

  /// جلسة قابلة للاستئناف: رمز وصول صالح، أو رمز تحديث يمكن تجديده به.
  bool get canResumeSession => isAuthenticated || _refreshToken != null;
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
