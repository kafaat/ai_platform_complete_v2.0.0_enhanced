// SAHOOL — lib/core/offline/offline_read_cache.dart
// كاش قراءة دائم ومشفَّر، منطَّق بالمستأجِر+المستخدم، لفتح التطبيق دون اتّصال:
// يرى المزارع آخر ما جُلِب مع عمره بدل شاشة فارغة.
//
// يكمّل ResponseCache (ذاكرة 5 دقائق تموت مع العمليّة)، ولا يحلّ محلّه.
//
// العزل بين المستأجِرين بطبقتين مستقلّتين:
//   1. مفتاح التخزين يبدأ بمعرّف النطاق (sha256 للمستأجِر+المستخدم)، فلا تشترك
//      مدخلتان من نطاقين في مفتاح.
//   2. لكلّ نطاق مفتاح تشفير رئيسيّ خاصّ في flutter_secure_storage، والـMAC
//      يربط النصّ المشفَّر بمفتاح تخزينه: مفتاح نطاق آخر لا يفكّ المدخلة.
// ويُمسَح الكاش كلّه (المدخلات + المفاتيح) عند الخروج (SessionScope) وعند
// تبديل المستأجِر/المستخدم: أوّل قراءة/كتابة بنطاق غير النطاق النشط تمسح كلّ
// شيء قبل أن تُكمل — يشمل دخول حساب آخر دون خروج صريح (انتهاء الجلسة قسراً).
//
// كلّ مدخلة تحمل وقت جلبها داخل الحمولة المشفَّرة (لا يُعدَّل دون كشف).
// فشل-مغلق: أيّ خطأ تخزين/مفتاح ⇒ لا مدخلة (لا نصّ صريح على القرص أبداً).
import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:sahool_app/services/auth_service.dart';

import 'cache_backends.dart';
import 'cache_cipher.dart';

/// نطاق الكاش: المستأجِر والمستخدم معاً (مستخدم واحد في مستأجِرين = نطاقان).
@immutable
class CacheScope {
  const CacheScope({required this.tenantId, required this.userId});

  final String tenantId;
  final String userId;

  /// نطاق الجلسة الحاليّة، أو null إن غاب المستأجِر أو المستخدم (لا كاش حينها).
  static CacheScope? current() {
    final tenant = AuthService.instance.tenantId;
    final user = AuthService.instance.userId;
    if (tenant == null || tenant.isEmpty || user == null || user.isEmpty) {
      return null;
    }
    return CacheScope(tenantId: tenant, userId: user);
  }

  @override
  bool operator ==(Object other) =>
      other is CacheScope &&
      other.tenantId == tenantId &&
      other.userId == userId;

  @override
  int get hashCode => Object.hash(tenantId, userId);
}

/// معرّف نطاق ثابت لا يكشف المعرّفات على القرص.
String defaultScopeId(CacheScope s) => sha256
    .convert(utf8.encode('v1\u0000${s.tenantId}\u0000${s.userId}'))
    .toString()
    .substring(0, 32);

/// مدخلة مقروءة: البيانات كما وصلت من الخادم + وقت جلبها.
@immutable
class CachedRead {
  const CachedRead(this.data, this.fetchedAt);
  final Object? data;
  final DateTime fetchedAt;

  Duration age(DateTime now) => now.difference(fetchedAt);
}

class OfflineReadCache {
  OfflineReadCache({
    RawCacheStore? store,
    CacheKeyVault? vault,
    this.clearOnScopeSwitch = true,
    @visibleForTesting String Function(CacheScope)? scopeIdOf,
  })  : _store = store ?? HiveRawCacheStore(),
        _vault = vault ?? const SecureStorageCacheKeyVault(),
        _scopeIdOf = scopeIdOf ?? defaultScopeId;

  static final OfflineReadCache instance = OfflineReadCache();

  /// مفتاح محجوز يحفظ معرّف النطاق النشط (hash، لا معرّفات صريحة).
  static const String activeScopeKey = '__active_scope__';

  final RawCacheStore _store;
  final CacheKeyVault _vault;
  final String Function(CacheScope) _scopeIdOf;

  /// true (الإنتاج): نطاق جديد يمسح كلّ ما قبله. false يُبقي النطاقات معاً
  /// كي يختبر العزلُ التشفيريّ وحده.
  final bool clearOnScopeSwitch;

  final Map<String, CacheCipher> _ciphers = {};
  Future<void>? _tail;

  /// يُسلسل العمليّات: مسحٌ لا يتداخل مع كتابة.
  Future<T> _serial<T>(Future<T> Function() body) {
    final previous = _tail;
    final run = previous == null ? body() : previous.then((_) => body());
    final tail = run.then<void>((_) {}, onError: (Object _) {});
    _tail = tail;
    unawaited(tail.whenComplete(() {
      if (identical(_tail, tail)) _tail = null;
    }));
    return run;
  }

  String storageKeyFor(CacheScope scope, String key) =>
      '${_scopeIdOf(scope)}|$key';

  Future<void> _wipe() async {
    _ciphers.clear();
    await _store.clear();
    await _vault.deleteAll();
  }

  /// يمسح كلّ شيء إن تغيّر النطاق النشط، ثمّ يثبّت [scopeId] نشطاً.
  Future<void> _enter(String scopeId) async {
    if (!clearOnScopeSwitch) return;
    final active = await _store.get(activeScopeKey);
    if (active == scopeId) return;
    if (active != null) await _wipe();
    await _store.put(activeScopeKey, scopeId);
  }

  Future<CacheCipher?> _cipher(String scopeId, {required bool create}) async {
    final cached = _ciphers[scopeId];
    if (cached != null) return cached;
    var key = await _vault.read(scopeId);
    if (key == null) {
      if (!create) return null;
      key = newMasterKey();
      await _vault.write(scopeId, key);
    }
    return _ciphers[scopeId] = CacheCipher(key);
  }

  /// آخر ما حُفِظ لـ[key] في [scope]، أو null.
  Future<CachedRead?> read(CacheScope scope, String key) => _serial(() async {
        try {
          final scopeId = _scopeIdOf(scope);
          await _enter(scopeId);
          final storageKey = storageKeyFor(scope, key);
          final sealed = await _store.get(storageKey);
          if (sealed == null) return null;
          final cipher = await _cipher(scopeId, create: false);
          final plain = cipher?.open(storageKey, sealed);
          if (plain == null) return null;
          final decoded = jsonDecode(plain);
          if (decoded is! Map) return null;
          final at = DateTime.tryParse('${decoded['fetched_at']}');
          if (at == null) return null;
          // محفوظ UTC؛ يُعاد محلّيّاً كساعة التطبيق (DateTime.now()).
          return CachedRead(decoded['data'], at.toLocal());
        } catch (e) {
          debugPrint('OfflineReadCache.read failed: $e');
          return null;
        }
      });

  /// يحفظ [data] (قابلة لـJSON) مع وقت جلبها [fetchedAt].
  Future<void> write(
    CacheScope scope,
    String key,
    Object? data,
    DateTime fetchedAt,
  ) =>
      _serial(() async {
        try {
          final scopeId = _scopeIdOf(scope);
          await _enter(scopeId);
          final cipher = await _cipher(scopeId, create: true);
          if (cipher == null) return;
          final storageKey = storageKeyFor(scope, key);
          final plain = jsonEncode({
            'fetched_at': fetchedAt.toUtc().toIso8601String(),
            'data': data,
          });
          await _store.put(storageKey, cipher.seal(storageKey, plain));
        } catch (e) {
          // الحفظ تحسين لا شرط: فشله لا يُسقط الشاشة ولا يكتب نصّاً صريحاً.
          debugPrint('OfflineReadCache.write failed: $e');
        }
      });

  /// يمسح المدخلات والمفاتيح (الخروج).
  Future<void> clear() => _serial(() async {
        try {
          await _wipe();
        } catch (e) {
          debugPrint('OfflineReadCache.clear failed: $e');
        }
      });
}
