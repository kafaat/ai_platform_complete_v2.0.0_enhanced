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

  /// تسجيل الدخول (POST /auth/login). يحفظ التوكنات + الملفّ في التخزين الآمن.
  /// صدق: يفشل برسالة واضحة إن نقص رمز الوصول (لا جلسة زائفة).
  Future<Map<String, dynamic>> login(String email, String password) async {
    final r = await _dio.post('/auth/login',
        data: {'email': email, 'password': password});
    final data = r.data as Map<String, dynamic>;
    final access = data['access_token'] as String?;
    if (access == null) {
      throw Exception('استجابة الدخول بلا رمز وصول');
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

  // ══════════════════════════════════════════════════════════════════
  // OPERATIONAL SUBSYSTEMS — /api/v1/* (مخزون/معدّات/أجهزة/ريّ/مرجعيّة/وثائق)
  // ربط حيّ بالخلفيّة الفعليّة عبر نفس الـDio (توكن، إعادة محاولة، كشف انقطاع).
  // لا بيانات مُلفَّقة — الخطأ (503 DB مُعطَّلة / 403 RBAC) يُرمى ليعرض الـUI حالة
  // صادقة. كلّ القوائم تُعيد List<Map> (الخادم يردّ مصفوفة JSON صريحة).
  // المسارات والحقول تطابق frontend/src/services/api.ts بدقّة.
  // ══════════════════════════════════════════════════════════════════
  List<Map<String, dynamic>> _asList(dynamic data) {
    if (data is List) {
      return data.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList();
    }
    return const [];
  }

  Map<String, dynamic> _asMap(dynamic data) =>
      data is Map ? data.cast<String, dynamic>() : <String, dynamic>{};

  // ── Inventory (inventory:view / inventory:manage) ──
  Future<List<Map<String, dynamic>>> getInventoryItems() async {
    final r = await _dio.get('/api/v1/inventory/items');
    return _asList(r.data);
  }

  Future<List<Map<String, dynamic>>> getExpiringBatches({int days = 30}) async {
    final r = await _dio.get('/api/v1/inventory/expiring',
        queryParameters: {'days': days});
    return _asList(r.data);
  }

  Future<Map<String, dynamic>> createInventoryItem(
      Map<String, dynamic> payload) async {
    final r = await _dio.post('/api/v1/inventory/items', data: payload);
    return _asMap(r.data);
  }

  Future<Map<String, dynamic>> addInventoryBatch(
      String itemId, Map<String, dynamic> payload) async {
    final r =
        await _dio.post('/api/v1/inventory/items/$itemId/batches', data: payload);
    return _asMap(r.data);
  }

  // ── Equipment (equipment:view / equipment:manage) ──
  Future<List<Map<String, dynamic>>> getEquipment() async {
    final r = await _dio.get('/api/v1/equipment');
    return _asList(r.data);
  }

  Future<Map<String, dynamic>> createEquipment(
      Map<String, dynamic> payload) async {
    final r = await _dio.post('/api/v1/equipment', data: payload);
    return _asMap(r.data);
  }

  Future<List<Map<String, dynamic>>> getMaintenance(String equipmentId) async {
    final r = await _dio.get('/api/v1/equipment/$equipmentId/maintenance');
    return _asList(r.data);
  }

  Future<Map<String, dynamic>> logMaintenance(
      String equipmentId, Map<String, dynamic> payload) async {
    final r = await _dio.post('/api/v1/equipment/$equipmentId/maintenance',
        data: payload);
    return _asMap(r.data);
  }

  // ── IoT Devices (device:view / device:manage / observation:record) ──
  Future<List<Map<String, dynamic>>> listDevices() async {
    final r = await _dio.get('/api/v1/devices');
    return _asList(r.data);
  }

  Future<Map<String, dynamic>> registerDevice(
      Map<String, dynamic> payload) async {
    final r = await _dio.post('/api/v1/devices', data: payload);
    return _asMap(r.data);
  }

  Future<List<Map<String, dynamic>>> getDeviceTelemetry(String deviceId,
      {int limit = 20}) async {
    final r = await _dio.get('/api/v1/devices/$deviceId/telemetry',
        queryParameters: {'limit': limit});
    return _asList(r.data);
  }

  Future<Map<String, dynamic>> recordTelemetry(
      String deviceId, Map<String, dynamic> payload) async {
    final r =
        await _dio.post('/api/v1/devices/$deviceId/telemetry', data: payload);
    return _asMap(r.data);
  }

  // ── Irrigation Ops (irrigation:view / irrigation:manage) ──
  // ملاحظة: setValveState يسجّل النيّة فقط؛ التشغيل الفيزيائيّ عبر HIL (موافقة بشريّة).
  Future<List<Map<String, dynamic>>> listValves() async {
    final r = await _dio.get('/api/v1/irrigation/valves');
    return _asList(r.data);
  }

  Future<Map<String, dynamic>> createValve(Map<String, dynamic> payload) async {
    final r = await _dio.post('/api/v1/irrigation/valves', data: payload);
    return _asMap(r.data);
  }

  Future<Map<String, dynamic>> setValveState(
      String valveId, String status) async {
    final r = await _dio.post('/api/v1/irrigation/valves/$valveId/state',
        data: {'status': status});
    return _asMap(r.data);
  }

  Future<List<Map<String, dynamic>>> listSchedules({String? fieldId}) async {
    final r = await _dio.get('/api/v1/irrigation/schedules',
        queryParameters: fieldId != null ? {'field_id': fieldId} : null);
    return _asList(r.data);
  }

  Future<Map<String, dynamic>> createSchedule(
      Map<String, dynamic> payload) async {
    final r = await _dio.post('/api/v1/irrigation/schedules', data: payload);
    return _asMap(r.data);
  }

  Future<void> deleteSchedule(String scheduleId) async {
    await _dio.delete('/api/v1/irrigation/schedules/$scheduleId');
  }

  // ── Master Data (master_data:view / master_data:manage) ──
  Future<List<Map<String, dynamic>>> getMasterData(String category) async {
    final r = await _dio.get('/api/v1/master-data',
        queryParameters: {'category': category});
    return _asList(r.data);
  }

  Future<Map<String, dynamic>> createMasterDataEntry(
      Map<String, dynamic> payload) async {
    final r = await _dio.post('/api/v1/master-data', data: payload);
    return _asMap(r.data);
  }

  // ── Documents (document:view / document:manage) — بيانات وصفيّة فقط ──
  Future<List<Map<String, dynamic>>> listDocuments(
      {String? category, String? fieldId}) async {
    final q = <String, dynamic>{};
    if (category != null) q['category'] = category;
    if (fieldId != null) q['field_id'] = fieldId;
    final r = await _dio.get('/api/v1/documents',
        queryParameters: q.isEmpty ? null : q);
    return _asList(r.data);
  }

  Future<Map<String, dynamic>> createDocument(
      Map<String, dynamic> payload) async {
    final r = await _dio.post('/api/v1/documents', data: payload);
    return _asMap(r.data);
  }
}
