// SAHOOL — lib/core/offline/cache_backends.dart
// مخزنا كاش القراءة دون اتّصال: البايتات المشفَّرة (Hive) والمفاتيح الرئيسيّة
// لكلّ نطاق (flutter_secure_storage — Keystore/Keychain). كلاهما تبعيّة قائمة.
//
// المخزن الخام لا يرى نصّاً صريحاً قطّ: يحفظ ما ختمه CacheCipher فقط. والمفاتيح
// منفصلة عنه، فنسخ ملفّ Hive من الجهاز لا يكفي لقراءته.
import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:hive/hive.dart';

/// مخزن نصوص بمفاتيح (القيم مختومة مسبقاً).
abstract class RawCacheStore {
  Future<String?> get(String key);
  Future<void> put(String key, String value);
  Future<void> clear();
}

/// مفاتيح رئيسيّة لكلّ نطاق (معرّف النطاق ⇒ 32 بايتاً).
abstract class CacheKeyVault {
  Future<List<int>?> read(String scopeId);
  Future<void> write(String scopeId, List<int> key);

  /// يحذف كلّ مفاتيح الكاش (تمزيق تشفيريّ: ما بقي على القرص لا يُقرأ).
  Future<void> deleteAll();
}

/// للاختبارات ولغياب Hive.
class MemoryRawCacheStore implements RawCacheStore {
  final Map<String, String> entries = {};

  @override
  Future<String?> get(String key) async => entries[key];

  @override
  Future<void> put(String key, String value) async => entries[key] = value;

  @override
  Future<void> clear() async => entries.clear();
}

/// للاختبارات.
class MemoryCacheKeyVault implements CacheKeyVault {
  final Map<String, List<int>> keys = {};

  @override
  Future<List<int>?> read(String scopeId) async => keys[scopeId];

  @override
  Future<void> write(String scopeId, List<int> key) async =>
      keys[scopeId] = List<int>.of(key);

  @override
  Future<void> deleteAll() async => keys.clear();
}

const String kOfflineReadCacheBox = 'offline_read_cache';

/// صندوق يفتحه main.dart بعد Hive.initFlutter — غيابه ⇒ Hive غير مهيّأ.
const String _hiveReadyProbeBox = 'settings';

class HiveRawCacheStore implements RawCacheStore {
  HiveRawCacheStore({this.boxName = kOfflineReadCacheBox});

  final String boxName;

  Future<Box<dynamic>?> _box() async {
    if (Hive.isBoxOpen(boxName)) return Hive.box<dynamic>(boxName);
    // اختبار عارٍ بلا Hive.initFlutter: openBox يُسرّب خطأً غير ملتقَط حينها.
    if (!Hive.isBoxOpen(_hiveReadyProbeBox)) return null;
    return Hive.openBox<dynamic>(boxName);
  }

  @override
  Future<String?> get(String key) async {
    final v = (await _box())?.get(key);
    return v is String ? v : null;
  }

  @override
  Future<void> put(String key, String value) async =>
      (await _box())?.put(key, value);

  @override
  Future<void> clear() async => (await _box())?.clear();
}

class SecureStorageCacheKeyVault implements CacheKeyVault {
  const SecureStorageCacheKeyVault();

  // نفس خيارات AuthService (F12).
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
  static const _prefix = 'offline_read_cache.key.';

  @override
  Future<List<int>?> read(String scopeId) async {
    final v = await _storage.read(key: '$_prefix$scopeId');
    if (v == null) return null;
    final bytes = base64.decode(v);
    return bytes.length == 32 ? bytes : null;
  }

  @override
  Future<void> write(String scopeId, List<int> key) =>
      _storage.write(key: '$_prefix$scopeId', value: base64.encode(key));

  @override
  Future<void> deleteAll() async {
    // نسخة من الأسماء: الحذف أثناء المرور على خريطة readAll يرمي.
    final names = (await _storage.readAll()).keys.toList();
    for (final k in names) {
      if (k.startsWith(_prefix)) await _storage.delete(key: k);
    }
  }
}
