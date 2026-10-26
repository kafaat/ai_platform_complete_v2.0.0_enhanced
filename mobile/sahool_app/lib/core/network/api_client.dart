// SAHOOL — lib/core/network/api_client.dart
// العميل الشبكيّ الوحيد للتطبيق: Dio واحد بعنوان أساس واحد، ترويسة المصادقة،
// تحديث التوكن، إعادة المحاولة المقيَّدة، معرّف الطلب، وتحويل الأخطاء إلى
// [ApiException] مُنمَّط. كلّ ملفّ features/<x>/data/<x>_api.dart يبني نداءاته
// فوقه؛ لا ميزة تنشئ Dio خاصّاً بها.
//
// تحديث التوكن (إصلاح ثلاثة أعطال قِيست من قراءة الشيفرة والخادم):
//   1) طلب /auth/refresh كان يمرّ بنفس الـinterceptor فيرى التوكن المنتهي ويبدأ
//      تحديثاً ثانياً بلا نهاية ⇒ كلّ طلب يتعلّق بعد ساعة. الآن يمرّ عبر Dio
//      منفصل ([_refreshDio]) بلا أيّ interceptor مصادقة.
//   2) التحديث قبل الطلب لم يكن موحّداً، والخادم يستهلك رمز التحديث مرّة واحدة
//      (services/auth/routers/session.py GETDEL) ⇒ طلبان متزامنان يُخرجان
//      المستخدم. الآن كلّ المستدعين (قبل الطلب، بعد 401، WebSocket) ينتظرون
//      Completer واحداً ([_refreshCompleter]).
//   3) لا يُمسَح رمز التحديث لمجرّد انتهاء رمز الوصول. يُمسَح فقط حين يرفضه الخادم
//      صراحةً (400/401/403 من /auth/refresh) — لا عند انقطاع الشبكة.
//
// إعادة المحاولة: 502/503/504 فقط، بحدّ 3 وbackoff أُسّيّ + jitter. القراءات
// (GET/HEAD/OPTIONS) تُعاد دائماً؛ الكتابات **فقط** إن حملت Idempotency-Key
// (انظر idempotency.dart). multipart (FormData) لا يُعاد لأنّ جسمه يُستهلَك.
import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:flutter/foundation.dart';
import 'package:logger/logger.dart';
import 'package:sahool_app/config/app_config.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/utils/ids.dart';
import 'package:sahool_app/core/utils/jwt.dart';
import 'package:sahool_app/services/auth_service.dart';

/// مصدر التوكنات للعميل. الافتراضيّ يقرأ AuthService (تخزين آمن)؛ الاختبارات
/// تمرّر مخزناً في الذاكرة.
abstract class TokenStore {
  String? get accessToken;
  String? get refreshToken;
  Future<void> saveTokens(String access, {String? refresh});

  /// يمسح الجلسة (رفض الخادم لرمز التحديث).
  Future<void> clear();
}

class AuthServiceTokenStore implements TokenStore {
  const AuthServiceTokenStore();
  @override
  String? get accessToken => AuthService.instance.token;
  @override
  String? get refreshToken => AuthService.instance.refreshToken;
  @override
  Future<void> saveTokens(String access, {String? refresh}) =>
      AuthService.instance.saveToken(access, refresh: refresh);
  @override
  Future<void> clear() => AuthService.instance.clearAuth();
}

class ApiClient {
  ApiClient({
    String? baseUrl,
    TokenStore? tokens,
    HttpClientAdapter? adapter,
    this.retryBaseDelay = const Duration(seconds: 1),
    this.retryJitterMs = 500,
    Random? random,
  })  : _tokens = tokens ?? const AuthServiceTokenStore(),
        _rand = random ?? Random() {
    final base = baseUrl ?? AppConfig.apiUri.toString();
    _dio = Dio(_options(base));
    _refreshDio = Dio(_options(base));
    if (adapter != null) {
      _dio.httpClientAdapter = adapter;
      _refreshDio.httpClientAdapter = adapter;
    } else if (kDebugMode) {
      _allowSelfSignedInDebug(_dio);
      _allowSelfSignedInDebug(_refreshDio);
    }
    _refreshDio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        options.headers['X-Request-ID'] = generateRequestId();
        handler.next(options);
      },
    ));
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: _onRequest,
      onResponse: (response, handler) {
        _logger.d('← ${response.statusCode} ${response.requestOptions.path}');
        handler.next(response);
      },
      onError: _onError,
    ));
  }

  /// العميل المشترك للتطبيق.
  static final ApiClient instance = ApiClient();

  static const String userAgent = 'SAHOOL-Mobile/9.1.0 (Flutter)';

  // حدّ أقصى للمحاولات + مولّد jitter (يمنع retry storm).
  static const int _maxRetries = 3;
  final Duration retryBaseDelay;
  final int retryJitterMs;
  final Random _rand;

  final TokenStore _tokens;
  // سطر واحد لكلّ حدث، ومن مستوى info فما فوق (لا ضجيج debug لكلّ طلب).
  final _logger = Logger(printer: SimplePrinter(), level: Level.info);
  late final Dio _dio;
  late final Dio _refreshDio;

  /// Dio المشترك (للميزات التي تحتاج Dio خاماً، مثل field_forms وrealtime).
  Dio get dio => _dio;

  final _sessionExpired = StreamController<void>.broadcast();

  /// يُطلَق حين يرفض الخادم رمز التحديث فتُمسَح الجلسة. AuthGate يستمع إليه
  /// ليعرض شاشة الدخول بدل أن تبقى الشاشات تفشل بـ401.
  Stream<void> get onSessionExpired => _sessionExpired.stream;

  static BaseOptions _options(String base) => BaseOptions(
        baseUrl: base,
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 30),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'User-Agent': userAgent,
        },
      );

  static void _allowSelfSignedInDebug(Dio d) {
    final adapter = d.httpClientAdapter;
    if (adapter is! IOHttpClientAdapter) return;
    adapter.createHttpClient = () {
      final client = HttpClient();
      client.badCertificateCallback = (cert, host, port) {
        debugPrint('⚠️ Self-signed cert: $host:$port');
        return true; // debug فقط
      };
      return client;
    };
  }

  // ── المصادقة ───────────────────────────────────────────────────────

  bool _isUsable(String? token) => token != null && !isJwtExpired(token);

  /// توكن وصول صالح الآن، مُحدَّثاً عند الحاجة (للـWebSocket وما شابه).
  /// null ⇒ لا جلسة أو تعذّر التحديث.
  Future<String?> validAccessToken() async {
    final token = _tokens.accessToken;
    if (_isUsable(token)) return token;
    if (_tokens.refreshToken == null) return null;
    return refreshAccessToken();
  }

  Completer<String?>? _refreshCompleter;

  /// تحديث موحّد: نداءات متزامنة تتشارك طلب /auth/refresh واحداً.
  Future<String?> refreshAccessToken() {
    final existing = _refreshCompleter;
    if (existing != null) return existing.future;
    final completer = Completer<String?>();
    _refreshCompleter = completer;
    _performRefresh()
        .then(completer.complete, onError: (Object _) => completer.complete(null))
        .whenComplete(() => _refreshCompleter = null); // حرّر القفل دائماً
    return completer.future;
  }

  Future<String?> _performRefresh() async {
    final refresh = _tokens.refreshToken;
    if (refresh == null) return null;
    try {
      final r = await _refreshDio.post<dynamic>(
        '/auth/refresh',
        data: {'refresh_token': refresh},
        options: Options(extra: {'is_refresh': true}),
      );
      final data = r.data;
      final access = data is Map ? data['access_token'] as String? : null;
      if (access == null) return null;
      await _tokens.saveTokens(access,
          refresh: data is Map ? data['refresh_token'] as String? : null);
      return access;
    } on DioException catch (e) {
      final code = e.response?.statusCode;
      if (code == 400 || code == 401 || code == 403) {
        // الخادم رفض رمز التحديث صراحةً ⇒ الجلسة انتهت فعلاً.
        await _expireSession();
      }
      // شبكة/5xx ⇒ نُبقي الجلسة؛ المحاولة التالية قد تنجح.
      return null;
    }
  }

  Future<void> _expireSession() async {
    await _tokens.clear();
    if (!_sessionExpired.isClosed) _sessionExpired.add(null);
  }

  Future<void> _onRequest(
      RequestOptions options, RequestInterceptorHandler handler) async {
    options.headers['X-Request-ID'] = generateRequestId();
    if (options.extra['skip_auth'] != true) {
      var token = _tokens.accessToken;
      if (!_isUsable(token) && _tokens.refreshToken != null) {
        token = await refreshAccessToken();
      }
      if (_isUsable(token)) {
        options.headers['Authorization'] = 'Bearer $token';
      } else {
        options.headers.remove('Authorization');
      }
    }
    _logger.d('→ ${options.method} ${options.path} [${options.headers['X-Request-ID']}]');
    handler.next(options);
  }

  Future<void> _onError(
      DioException error, ErrorInterceptorHandler handler) async {
    final options = error.requestOptions;

    if (error.response?.statusCode == 401 &&
        options.extra['skip_auth'] != true &&
        options.extra['auth_retried'] != true) {
      if (_tokens.refreshToken == null) {
        // لا رمز تحديث ⇒ رمز الوصول وحده رُفض: الجلسة منتهية.
        if (_tokens.accessToken != null) await _expireSession();
        return handler.next(error);
      }
      final token = await refreshAccessToken();
      if (token != null) {
        options.extra['auth_retried'] = true;
        options.headers['Authorization'] = 'Bearer $token';
        try {
          return handler.resolve(await _dio.fetch<dynamic>(options));
        } on DioException catch (retryError) {
          return handler.next(retryError);
        }
      }
      return handler.next(error);
    }

    if (_shouldRetry(error)) {
      final attempt = (options.extra['retry_attempt'] as int?) ?? 0;
      if (attempt < _maxRetries) {
        options.extra['retry_attempt'] = attempt + 1;
        // backoff أُسّيّ: 2^attempt × الأساس + jitter عشوائيّ.
        final backoffMs = (retryBaseDelay.inMilliseconds * (1 << attempt)) +
            (retryJitterMs > 0 ? _rand.nextInt(retryJitterMs) : 0);
        await Future<void>.delayed(Duration(milliseconds: backoffMs));
        try {
          return handler.resolve(await _dio.fetch<dynamic>(options));
        } on DioException catch (retryError) {
          return handler.next(retryError);
        }
      }
    }

    _logger.w('✗ ${error.response?.statusCode ?? error.type.name}: ${options.method} ${options.path}');
    handler.next(error);
  }

  /// طرقٌ آمنة (idempotent بالتعريف في HTTP).
  static const _safeMethods = {'GET', 'HEAD', 'OPTIONS'};

  bool _shouldRetry(DioException error) {
    final code = error.response?.statusCode;
    if (code == null || ![502, 503, 504].contains(code)) return false;
    final options = error.requestOptions;
    if (options.data is FormData) return false; // جسم مُستهلَك لا يُعاد إرساله
    if (_safeMethods.contains(options.method.toUpperCase())) return true;
    final key = options.headers[kIdempotencyHeader];
    return key is String && key.isNotEmpty;
  }

  // ── نداءات مُنمَّطة (ترمي ApiException) ─────────────────────────────

  /// ينفّذ طلباً ويُعيد جسم الاستجابة. كلّ فشل يُرمى [ApiException].
  ///
  /// [idempotencyKey]: للكتابات فقط، ثابت لنفس النيّة (انظر idempotency.dart).
  /// [receiveTimeout]/[sendTimeout]: لنداءات بطيئة (المستشار ≥120ث، الرفع).
  /// [authenticated]=false: لا ترويسة مصادقة ولا تحديث (الدخول، استعادة كلمة المرور).
  Future<dynamic> send(
    String method,
    String path, {
    Object? data,
    Map<String, dynamic>? query,
    IdempotencyKey? idempotencyKey,
    Map<String, String>? headers,
    Duration? receiveTimeout,
    Duration? sendTimeout,
    CancelToken? cancelToken,
    String? contentType,
    bool authenticated = true,
  }) async {
    try {
      final r = await _dio.request<dynamic>(
        path,
        data: data,
        queryParameters: query,
        cancelToken: cancelToken,
        options: Options(
          method: method,
          headers: {
            ...?headers,
            if (idempotencyKey != null) kIdempotencyHeader: idempotencyKey.value,
          },
          receiveTimeout: receiveTimeout,
          sendTimeout: sendTimeout,
          contentType: contentType,
          extra: authenticated ? null : const {'skip_auth': true},
        ),
      );
      return r.data;
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<dynamic> get(String path,
          {Map<String, dynamic>? query,
          Duration? receiveTimeout,
          CancelToken? cancelToken}) =>
      send('GET', path,
          query: query,
          receiveTimeout: receiveTimeout,
          cancelToken: cancelToken);

  Future<dynamic> post(String path,
          {Object? data,
          Map<String, dynamic>? query,
          IdempotencyKey? idempotencyKey,
          Duration? receiveTimeout,
          Duration? sendTimeout}) =>
      send('POST', path,
          data: data,
          query: query,
          idempotencyKey: idempotencyKey,
          receiveTimeout: receiveTimeout,
          sendTimeout: sendTimeout);

  Future<dynamic> put(String path,
          {Object? data, IdempotencyKey? idempotencyKey}) =>
      send('PUT', path, data: data, idempotencyKey: idempotencyKey);

  Future<dynamic> patch(String path,
          {Object? data, IdempotencyKey? idempotencyKey}) =>
      send('PATCH', path, data: data, idempotencyKey: idempotencyKey);

  Future<dynamic> delete(String path,
          {Object? data, IdempotencyKey? idempotencyKey}) =>
      send('DELETE', path, data: data, idempotencyKey: idempotencyKey);
}
