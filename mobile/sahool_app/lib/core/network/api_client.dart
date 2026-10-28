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
// جيل الجلسة (D2، R08/R09): الـCompleter نفسه مربوط بجيل الجلسة ومالكها
// ([TokenStore.generation])، وكلّ طلب مُصادَق يحمل الجيل الذي أُرسل فيه.
//   • ردّ تجديد لجيل سابق (تبديل حساب/خروج أثناء الطلب) لا يحفظ رموزاً ولا
//     يمسح الجلسة الأحدث: الحفظ والمسح مشروطان بالجيل داخل المخزن نفسه.
//   • طلب من جيل سابق لا يُرسَل (ولا يُعاد) برموز الجلسة الأحدث، و401 المتأخّرة له
//     لا تُجدِّد ولا تمسح شيئاً.
//   • 401 متأخّرة لرمز أقدم من الجلسة نفسها تُعاد بالرمز الأحدث بلا تجديد إضافيّ.
//
// إعادة المحاولة: 502/503/504 فقط، بحدّ 3 وbackoff أُسّيّ + jitter. القراءات
// (GET/HEAD/OPTIONS) تُعاد دائماً؛ الكتابات **فقط** إن حملت Idempotency-Key
// (انظر idempotency.dart). multipart (FormData) لا يُعاد لأنّ جسمه يُستهلَك؛
// استثناء وحيد: إعادة بعد تحديث التوكن (401) ترسل نسخة FormData.clone().
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

/// extra: `bool Function(String? token)` يُستدعى بالرمز الذي سيُرسَل؛ false ⇒ لا
/// يُرسَل الطلب ويُرمى إلغاءٌ سببه [kOwnerChangedBeforeSend]. null ⇒ لا رمز صالح
/// (تعذّر التجديد): الطلب سيخرج بلا ترويسة مصادقة — ليس هويّةً أخرى.
const String kOwnerGuardExtra = 'owner_guard';

/// سبب الإلغاء حين يرفض [kOwnerGuardExtra] الرمز — الطلب لم يغادر الجهاز.
const String kOwnerChangedBeforeSend = 'owner_changed_before_send';

/// extra: true ⇒ لا إعادة فوريّة لـ502/503/504؛ للمستدعي جدولة دائمة خاصّة.
const String kDurableRetryExtra = 'durable_retry';

/// مصدر التوكنات للعميل. الافتراضيّ يقرأ AuthService (تخزين آمن)؛ الاختبارات
/// تمرّر مخزناً في الذاكرة.
abstract class TokenStore {
  String? get accessToken;
  String? get refreshToken;

  /// جيل الجلسة: يتغيّر بالاستعادة والدخول وتبديل الحساب والخروج والمسح، لا
  /// بتجديد رمز الوصول. التجديد والطلب يُربطان به.
  int get generation;

  /// هويّة مالك الجلسة (للتشخيص وربط التجديد بمالكه)، أو null بلا جلسة.
  String? get owner;

  /// يحفظ رمزين مُجدَّدين. مع [generation]: الحفظ مشروط ذرّيّاً داخل المخزن
  /// (الفحص والكتابة بلا await بينهما) ويُعيد false إن تغيّرت الجلسة.
  Future<bool> saveTokens(String access, {String? refresh, int? generation});

  /// يمسح الجلسة (رفض الخادم لرمز التحديث). مع [generation]: مشروط ذرّيّاً،
  /// فرفض متأخّر لجلسة سابقة لا يمسح جلسة أحدث (false).
  Future<bool> clear({int? generation});
}

class AuthServiceTokenStore implements TokenStore {
  const AuthServiceTokenStore();
  @override
  String? get accessToken => AuthService.instance.token;
  @override
  String? get refreshToken => AuthService.instance.refreshToken;
  @override
  int get generation => AuthService.instance.sessionGeneration;
  @override
  String? get owner => AuthService.instance.sessionOwner;
  @override
  Future<bool> saveTokens(String access,
      {String? refresh, int? generation}) async {
    if (generation != null) {
      return AuthService.instance
          .saveRefreshedToken(generation, access, refresh: refresh);
    }
    await AuthService.instance.saveToken(access, refresh: refresh);
    return true;
  }

  @override
  Future<bool> clear({int? generation}) async {
    if (generation != null) {
      return AuthService.instance.clearIfGeneration(generation);
    }
    await AuthService.instance.clearAuth();
    return true;
  }
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

  /// جيل الجلسة ومالكها اللذان بدأ فيهما [_refreshCompleter] الجاري.
  int? _refreshGeneration;
  String? _refreshOwner;

  /// تجديد جارٍ للجلسة الحاليّة (لا لجلسة سابقة)، أو null. المسارات الخاصّة
  /// تنتظره قبل الحكم على الجلسة.
  Future<void>? get pendingRefresh {
    final current = _refreshCompleter;
    if (current == null || _refreshGeneration != _tokens.generation) {
      return null;
    }
    return current.future;
  }

  /// تحديث موحّد: نداءات متزامنة **للجلسة نفسها** تتشارك طلب /auth/refresh
  /// واحداً. تجديدٌ بدأ لجيل سابق لا يُشارَك: نتيجته تخصّ جلسةً انتهت.
  Future<String?> refreshAccessToken() {
    final generation = _tokens.generation;
    final owner = _tokens.owner;
    final existing = _refreshCompleter;
    if (existing != null &&
        _refreshGeneration == generation &&
        _refreshOwner == owner) {
      return existing.future;
    }
    // تجديد جيل سابق (إن وُجد) يُترك ليُحسَم وحده؛ المخزن يرفض نتيجته.
    final completer = Completer<String?>();
    _refreshCompleter = completer;
    _refreshGeneration = generation;
    _refreshOwner = owner;
    _performRefresh(generation, owner)
        .then(completer.complete, onError: (Object _) => completer.complete(null))
        .whenComplete(() {
      // حرّر القفل دائماً — ما لم يحلّ محلّه تجديد جيل أحدث.
      if (identical(_refreshCompleter, completer)) {
        _refreshCompleter = null;
        _refreshGeneration = null;
        _refreshOwner = null;
      }
    });
    return completer.future;
  }

  bool _isCurrent(int generation, String? owner) =>
      _tokens.generation == generation && _tokens.owner == owner;

  Future<String?> _performRefresh(int generation, String? owner) async {
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
      // ردّ متأخّر بعد تبديل الحساب/الخروج ⇒ لا يُحفَظ. الفحص هنا اختصار؛
      // الضمان في المخزن (حفظ مشروط بالجيل بلا await بين الفحص والكتابة).
      if (!_isCurrent(generation, owner)) return null;
      final saved = await _tokens.saveTokens(access,
          refresh: data is Map ? data['refresh_token'] as String? : null,
          generation: generation);
      return saved ? access : null;
    } on DioException catch (e) {
      final code = e.response?.statusCode;
      if (code == 400 || code == 401 || code == 403) {
        // الخادم رفض رمز التحديث صراحةً ⇒ جلسة **ذلك الجيل** انتهت فعلاً.
        await _expireSession(generation);
      }
      // شبكة/5xx ⇒ نُبقي الجلسة؛ المحاولة التالية قد تنجح.
      return null;
    }
  }

  /// يمسح جلسة [generation] ويعلن انتهاءها — لا شيء إن حلّت محلّها جلسة أحدث.
  Future<void> _expireSession(int generation) async {
    final cleared = await _tokens.clear(generation: generation);
    if (cleared && !_sessionExpired.isClosed) _sessionExpired.add(null);
  }

  /// مفتاح extra: جيل الجلسة الذي أُرسل فيه الطلب أوّل مرّة.
  static const _kSessionGeneration = 'session_generation';

  DioException _sessionChanged(RequestOptions options) => DioException(
        requestOptions: options,
        type: DioExceptionType.cancel,
        error: 'session changed',
      );

  Future<void> _onRequest(
      RequestOptions options, RequestInterceptorHandler handler) async {
    options.headers['X-Request-ID'] = generateRequestId();
    if (options.extra['skip_auth'] != true) {
      final generation = _tokens.generation;
      final bound = options.extra[_kSessionGeneration];
      // إعادة (بعد 401 أو 5xx) لطلب جلسة سابقة: لا يُرسَل برموز الجلسة الأحدث.
      if (bound is int && bound != generation) {
        return handler.reject(_sessionChanged(options));
      }
      options.extra[_kSessionGeneration] = generation;
      var token = _tokens.accessToken;
      if (!_isUsable(token) && _tokens.refreshToken != null) {
        token = await refreshAccessToken();
        if (_tokens.generation != generation) {
          return handler.reject(_sessionChanged(options));
        }
      }
      // حارس المالك (صندوق الإرسال): يُفحَص بعد آخر await وقبل الإرسال مباشرةً،
      // على الرمز الذي سيُرسَل فعلاً — لا يخرج طلبُ مالكٍ برمز جلسةٍ أخرى.
      // رمزٌ غير صالح لا يُرسَل ⇒ يُمرَّر null: «بلا هويّة»، لا «مالك آخر».
      if (!_ownerGuardAllows(options, _isUsable(token) ? token : null)) {
        return handler.reject(_ownerChanged(options));
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
      final generation = _tokens.generation;
      final bound = options.extra[_kSessionGeneration];
      if (bound is int && bound != generation) {
        // 401 لطلب من جلسة سابقة: لا تجديد برمز الجلسة الأحدث، لا إعادة
        // برموزها، ولا مسح لها.
        return handler.next(error);
      }
      final sent = options.headers['Authorization'];
      final current = _tokens.accessToken;
      String? token;
      if (_isUsable(current) && sent != 'Bearer $current') {
        // 401 متأخّرة لرمز أقدم من الجلسة نفسها: جُدِّد بعد إرسال الطلب ⇒ أعِد
        // بالرمز الأحدث بلا تجديد إضافيّ (رمز التحديث أحاديّ الاستعمال).
        token = current;
      } else if (_tokens.refreshToken == null) {
        // لا رمز تحديث ⇒ رمز الوصول وحده رُفض: الجلسة منتهية.
        if (current != null) await _expireSession(generation);
        return handler.next(error);
      } else {
        token = await refreshAccessToken();
        if (_tokens.generation != generation) return handler.next(error);
      }
      if (token != null) {
        // التجديد قد يحمل رمز جلسةٍ أحدث (تبدّل المستخدم أثناء الطلب): لا يُعاد
        // طلب المالك القديم بهويّة غيره.
        if (!_ownerGuardAllows(options, token)) {
          return handler.next(_ownerChanged(options));
        }
        options.extra['auth_retried'] = true;
        options.headers['Authorization'] = 'Bearer $token';
        // جسم multipart يُستهلَك عند الإرسال الأوّل؛ الإعادة بعد 401 تحتاج نسخة.
        final body = options.data;
        if (body is FormData) options.data = body.clone();
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
    // طلبٌ له جدولة دائمة (صندوق الإرسال) يُعاد هناك بموعدٍ محفوظ يحترم
    // Retry-After — لا ثلاث إعادات فوريّة هنا تتجاهله.
    if (options.extra[kDurableRetryExtra] == true) return false;
    if (options.data is FormData) return false; // جسم مُستهلَك لا يُعاد إرساله
    if (_safeMethods.contains(options.method.toUpperCase())) return true;
    final key = options.headers[kIdempotencyHeader];
    return key is String && key.isNotEmpty;
  }

  static bool _ownerGuardAllows(RequestOptions options, String? token) {
    final guard = options.extra[kOwnerGuardExtra];
    return guard is! bool Function(String?) || guard(token);
  }

  static DioException _ownerChanged(RequestOptions options) => DioException(
        requestOptions: options,
        type: DioExceptionType.cancel,
        error: kOwnerChangedBeforeSend,
      );

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
    Map<String, Object?>? extra,
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
          extra: {
            ...?extra,
            if (!authenticated) 'skip_auth': true,
          },
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
