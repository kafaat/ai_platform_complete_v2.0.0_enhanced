// SAHOOL — lib/core/offline/cached_loader.dart
// قراءة «الشبكة أوّلاً ثمّ آخر ما حُفِظ»: نجاح الجلب ⇒ يُحفَظ في الكاش المشفَّر
// مع وقته ويُعرض حاليّاً؛ تعذّر الشبكة/الخادم ⇒ تُعرض آخر نسخة محفوظة مع عمرها
// وسبب التعذّر. أمّا 401/403/404/422 فتصعد كما هي: نسخة قديمة لا تُجيب عن
// «لا صلاحيّة» أو «غير موجود» (نفس قاعدة DashboardCubit._staleWorthy).
import 'package:flutter/foundation.dart';
import 'package:sahool_app/core/network/api_exception.dart';

import 'offline_read_cache.dart';

/// نتيجة قراءة: البيانات + وقت جلبها + هل هي من الكاش ولماذا.
@immutable
class CachedResult<T> {
  const CachedResult({
    required this.data,
    required this.fetchedAt,
    this.fromCache = false,
    this.refreshError,
  });

  final T data;

  /// وقت جلب البيانات من الخادم (لا وقت قراءتها من الكاش).
  final DateTime fetchedAt;
  final bool fromCache;

  /// سبب تعذّر التحديث حين [fromCache].
  final ApiException? refreshError;

  Duration age(DateTime now) => now.difference(fetchedAt);
}

/// أخطاء يُعرض معها آخر ما عُرِف.
bool isStaleWorthy(ApiException e) =>
    e.isConnectivity ||
    e.kind == ApiErrorKind.unavailable ||
    e.kind == ApiErrorKind.server ||
    e.kind == ApiErrorKind.rateLimited;

class CachedLoader {
  CachedLoader({
    OfflineReadCache? cache,
    CacheScope? Function()? scope,
    DateTime Function()? clock,
  })  : _cache = cache ?? OfflineReadCache.instance,
        _scope = scope ?? CacheScope.current,
        _clock = clock ?? DateTime.now;

  final OfflineReadCache _cache;
  final CacheScope? Function() _scope;
  final DateTime Function() _clock;

  /// [fetch] يعيد JSON الخادم الخام (هو ما يُحفَظ)، و[parse] يحوّله ويرمي
  /// FormatException على شكل خاطئ — فلا يُحفَظ ردّ لا يُقرأ.
  Future<CachedResult<T>> load<T>({
    required String key,
    required Future<Object?> Function() fetch,
    required T Function(Object? json) parse,
  }) async {
    final scope = _scope();
    try {
      final raw = await fetch();
      final data = parse(raw);
      final at = _clock();
      if (scope != null) await _cache.write(scope, key, raw, at);
      return CachedResult(data: data, fetchedAt: at);
    } catch (e) {
      final error = ApiException.from(e);
      if (scope == null || !isStaleWorthy(error)) throw error;
      final cached = await _cache.read(scope, key);
      if (cached == null) throw error;
      T data;
      try {
        data = parse(cached.data);
      } catch (_) {
        throw error; // نسخة محفوظة لا تُقرأ ⇒ الخطأ الأصليّ، لا بيانات مختلَقة.
      }
      return CachedResult(
        data: data,
        fetchedAt: cached.fetchedAt,
        fromCache: true,
        refreshError: error,
      );
    }
  }
}
