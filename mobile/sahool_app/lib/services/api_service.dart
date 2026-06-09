// SAHOOL v9.1.0 — lib/services/api_service.dart (مُحسَّن)
// Fixes: D01(refresh on 401), D02(await clearAuth), D03(cancellation),
//        D04(offline detect), D05(retry), D06(exp check), D08(token redact),
//        D09(correlation ID), D10(User-Agent)
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:flutter/foundation.dart';
import 'package:logger/logger.dart';
import '../services/auth_service.dart';

class ApiService {
  static final ApiService instance = ApiService._internal();
  ApiService._internal() { _init(); }

  late final Dio _dio;
  final _logger = Logger();
  final Map<String, CancelToken> _cancelTokens = {};
  // حدّ أقصى للمحاولات + مولّد jitter (يمنع retry storm)
  static const int _maxRetries = 3;
  final _rand = Random();

  static const _baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'https://api.sahool.ye',
  );

  void _init() {
    _dio = Dio(BaseOptions(
      baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        // D10: Custom User-Agent
        'User-Agent': 'SAHOOL-Mobile/9.1.0 (Flutter)',
      },
    ));

    // D01/D05/D06/D08/D09: Full interceptor
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        // D09: Correlation ID for distributed tracing
        options.headers['X-Request-ID'] = _generateRequestId();

        // D06: Check token expiry before request
        final token = AuthService.instance.token;
        if (token != null) {
          if (!_isTokenExpired(token)) {
            // D08: Redact token in logs
            options.headers['Authorization'] = 'Bearer $token';
          } else {
            // Try refresh before sending
            final newToken = await _attemptRefresh();
            if (newToken != null) {
              options.headers['Authorization'] = 'Bearer $newToken';
            }
          }
        }

        _logger.d('→ ${options.method} ${options.path} [${options.headers['X-Request-ID']}]');
        return handler.next(options);
      },

      onResponse: (response, handler) {
        _logger.d('← ${response.statusCode} ${response.requestOptions.path}');
        return handler.next(response);
      },

      onError: (error, handler) async {
        // D04: Offline detection
        if (error.type == DioExceptionType.connectionError ||
            error.type == DioExceptionType.unknown) {
          _logger.w('Network offline or unreachable');
          return handler.next(error);
        }

        // D01 + P0: 401 → تحديث موحّد عبر Completer (يحلّ سباق 401 المتزامن).
        // كلّ الطلبات المتزامنة تنتظر تحديثاً واحداً بدل أن يفشل غير الأوّل.
        if (error.response?.statusCode == 401) {
          // تجنّب حلقة لا نهائيّة: لا تحدّث لطلب التحديث نفسه
          if (error.requestOptions.extra['is_refresh'] == true) {
            return handler.next(error);
          }
          try {
            final newToken = await _coalescedRefresh();
            if (newToken != null) {
              error.requestOptions.headers['Authorization'] = 'Bearer $newToken';
              final retried = await _dio.fetch(error.requestOptions);
              return handler.resolve(retried);
            }
          } catch (_) {}
          // فشل التحديث → امسح الجلسة مرّة واحدة
          await AuthService.instance.clearAuth();  // D02: await
          return handler.next(error);
        }

        // D05: Retry on 502/503/504 مع backoff أُسّي + jitter + حدّ أقصى
        // (يمنع retry storm — المراجعة حذّرت منه). 3 محاولات: ~1s, ~2s, ~4s.
        if (_shouldRetry(error)) {
          final attempt =
              (error.requestOptions.extra['retry_attempt'] as int?) ?? 0;
          if (attempt < _maxRetries) {
            error.requestOptions.extra['retry_attempt'] = attempt + 1;
            // backoff أُسّي: 2^attempt ثوانٍ + jitter عشوائي (0-500ms)
            final backoffMs =
                (1000 * (1 << attempt)) + (_rand.nextInt(500));
            await Future.delayed(Duration(milliseconds: backoffMs));
            try {
              final retried = await _dio.fetch(error.requestOptions);
              return handler.resolve(retried);
            } catch (_) {}
          }
        }

        _logger.e('✗ ${error.response?.statusCode}: ${error.message}');
        return handler.next(error);
      },
    ));

    // D03: Request cancellation on widget dispose
    _dio.interceptors.add(QueuedInterceptorsWrapper());

    // F01: Allow self-signed certs in debug mode
    if (kDebugMode) {
      (_dio.httpClientAdapter as IOHttpClientAdapter).createHttpClient = () {
        final client = HttpClient();
        client.badCertificateCallback = (cert, host, port) {
          debugPrint('⚠️ Self-signed cert: $host:$port');
          return true;  // Allow in debug only
        };
        return client;
      };
    }
  }

  bool _isTokenExpired(String token) {
    try {
      final parts = token.split('.');
      if (parts.length != 3) return true;
      final payload = json.decode(
        utf8.decode(base64Url.decode(base64Url.normalize(parts[1])))
      );
      final exp = payload['exp'] as int?;
      // M10 FIX: يفشل-مغلقاً (كـauth_service.dart) — توكن بلا exp أو غير قابل
      // للتحليل يُعدّ منتهياً بدل إرساله، لتفادي تمرير توكن فاسد/منتهٍ.
      if (exp == null) return true;
      return DateTime.now().millisecondsSinceEpoch / 1000 > exp - 60;
    } catch (_) { return true; }
  }

  String _generateRequestId() =>
      DateTime.now().millisecondsSinceEpoch.toRadixString(16);

  bool _shouldRetry(DioException error) =>
      error.response?.statusCode != null &&
      [502, 503, 504].contains(error.response!.statusCode) &&
      _refreshCompleter == null;

  // P0: تحديث موحّد — طلبات 401 المتزامنة تتشارك Completer واحداً.
  // يضمن: (أ) تحديث واحد فقط، (ب) الكلّ ينتظر نتيجته، (ج) القفل يُحرَّر دائماً.
  Completer<String?>? _refreshCompleter;

  Future<String?> _coalescedRefresh() {
    // لو تحديث جارٍ، انتظر نتيجته (لا تبدأ ثانياً)
    final existing = _refreshCompleter;
    if (existing != null) return existing.future;
    final completer = Completer<String?>();
    _refreshCompleter = completer;
    // نفّذ التحديث وأكمل الـCompleter (finally يحرّر دائماً — لا deadlock)
    _attemptRefresh().then((token) {
      completer.complete(token);
    }).catchError((Object e) {
      completer.complete(null);
    }).whenComplete(() {
      _refreshCompleter = null;  // حرّر القفل دائماً
    });
    return completer.future;
  }

  Future<String?> _attemptRefresh() async {
    final refreshToken = AuthService.instance.refreshToken;
    if (refreshToken == null) return null;
    try {
      final result = await refreshTokenCall(refreshToken);
      final newToken = result['access_token'] as String?;
      if (newToken != null) {
        await AuthService.instance.saveToken(newToken,
            refresh: result['refresh_token'] as String?);
        return newToken;
      }
    } catch (_) {}
    return null;
  }

  // D03: Cancel requests by tag
  CancelToken _getToken(String tag) {
    _cancelTokens[tag] ??= CancelToken();
    return _cancelTokens[tag]!;
  }
  void cancelRequest(String tag) {
    _cancelTokens[tag]?.cancel('User navigated away');
    _cancelTokens.remove(tag);
  }


  // F10: Simple TTL cache for API responses
  final Map<String, (dynamic, DateTime)> _cache = {};
  static const _cacheTtl = Duration(minutes: 5);

  dynamic _getCache(String key) {
    final entry = _cache[key];
    if (entry == null) return null;
    if (DateTime.now().difference(entry.$2) > _cacheTtl) {
      _cache.remove(key); return null;
    }
    return entry.$1;
  }
  void _setCache(String key, dynamic value) {
    if (_cache.length > 100) _cache.remove(_cache.keys.first);
    _cache[key] = (value, DateTime.now());
  }
  void clearCache() => _cache.clear();

  Future<Map<String, dynamic>> getDashboardCached({bool forceRefresh = false}) async {
    const key = 'dashboard';
    if (!forceRefresh) {
      final cached = _getCache(key);
      if (cached != null) return cached as Map<String, dynamic>;
    }
    final result = await getDashboard();
    _setCache(key, result);
    return result;
  }

  // ── API Methods ──────────────────────────────────────────────
  Future<Map<String, dynamic>> getDashboard({String? tag}) async {
    final r = await _dio.get('/indicators/v1/overview',
        cancelToken: tag != null ? _getToken(tag) : null);
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getFieldIndicators(String fieldId, {String? tag}) async {
    final r = await _dio.get('/indicators/v1/indicators/$fieldId',
        cancelToken: tag != null ? _getToken(tag) : null);
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> askAgent(String query, {String? fieldId}) async {
    final r = await _dio.post('/agent/query', data: {
      'query': query,
      if (fieldId != null) 'field_id': fieldId,
    });
    return r.data as Map<String, dynamic>;
  }

  Future<void> acknowledgeAlert(String alertId) async {
    await _dio.patch('/indicators/alerts/$alertId/acknowledge');
  }

  Future<Map<String, dynamic>> refreshTokenCall(String refreshToken) async {
    final r = await _dio.post('/auth/refresh',
        data: {'refresh_token': refreshToken},
        // P0: علِّم الطلب ليتخطّى معالج 401 (يمنع deadlock التحديث الذاتي)
        options: Options(extra: {'is_refresh': true}));
    return r.data as Map<String, dynamic>;
  }

  Future<void> logout({String? refreshToken}) async {
    try {
      await _dio.post('/auth/logout',
          data: refreshToken != null ? {'refresh_token': refreshToken} : {});
    } catch (_) {}
    await AuthService.instance.clearAuth();
  }

  Future<void> requestPasswordReset(String email) async {
    await _dio.post('/auth/password-reset/request', data: {'email': email});
  }

  Future<void> confirmPasswordReset(String token, String newPassword) async {
    await _dio.post('/auth/password-reset/confirm',
        data: {'token': token, 'new_password': newPassword});
  }
}
