// OfflineReadCache: تشفير على القرص، عزل بين المستأجِرين، عمر المدخلة، المسح عند
// الخروج وعند تبديل المستأجِر — مع ضابط سلبيّ يُثبت أنّ اختبار العزل يحمرّ إن
// سقط المستأجِر من مفتاح الكاش.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/offline/cache_backends.dart';
import 'package:sahool_app/core/offline/cache_cipher.dart';
import 'package:sahool_app/core/offline/offline_read_cache.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/session/session_scope.dart';

const tenantA = CacheScope(tenantId: 'tenant-a', userId: 'u1');
// المستخدم نفسه في مستأجِر آخر: لو سقط المستأجِر من المفتاح لتطابق النطاقان.
const tenantB = CacheScope(tenantId: 'tenant-b', userId: 'u1');

final fetched = DateTime.utc(2026, 11, 10, 6, 30);
const secret = {'recipe': 'SECRET-UREA-46-RATE', 'rate': 120};

/// خاصّيّة العزل نفسها، تُشغَّل على أيّ كاش: هل يقرأ B مدخلة A؟
Future<bool> tenantBReadsTenantA(OfflineReadCache cache) async {
  await cache.write(tenantA, 'recipes:f1', secret, fetched);
  final read = await cache.read(tenantB, 'recipes:f1');
  return read != null;
}

void main() {
  group('encryption at rest', () {
    test('round trip returns the data and its fetch time', () async {
      final cache = OfflineReadCache(
        store: MemoryRawCacheStore(),
        vault: MemoryCacheKeyVault(),
      );
      await cache.write(tenantA, 'k', secret, fetched);
      final read = await cache.read(tenantA, 'k');
      expect(read, isNotNull);
      expect(read!.data, secret);
      expect(read.fetchedAt, fetched.toLocal());
    });

    test('the stored bytes hold no plaintext and are not JSON', () async {
      final store = MemoryRawCacheStore();
      final cache = OfflineReadCache(store: store, vault: MemoryCacheKeyVault());
      await cache.write(tenantA, 'k', secret, fetched);
      final entries = Map.of(store.entries)
        ..remove(OfflineReadCache.activeScopeKey);
      expect(entries, hasLength(1));
      final stored = entries.values.single;
      expect(stored, isNot(contains('SECRET-UREA')));
      expect(utf8.decode(base64.decode(stored), allowMalformed: true),
          isNot(contains('SECRET-UREA')));
      expect(() => jsonDecode(stored), throwsFormatException);
      // ولا معرّفات المستأجِر/المستخدم في مفاتيح التخزين.
      expect(entries.keys.single, isNot(contains('tenant-a')));
    });

    test('a wrong key, a flipped byte or a moved entry opens to null', () {
      final c1 = CacheCipher(newMasterKey());
      final c2 = CacheCipher(newMasterKey());
      final sealed = c1.seal('scope|k', '{"a":1}');
      expect(c1.open('scope|k', sealed), '{"a":1}');
      expect(c2.open('scope|k', sealed), isNull, reason: 'wrong key');
      expect(c1.open('scope|other', sealed), isNull, reason: 'moved entry');
      final bytes = base64.decode(sealed);
      bytes[bytes.length - 20] ^= 0x01;
      expect(c1.open('scope|k', base64.encode(bytes)), isNull,
          reason: 'tampered');
    });

    test('AEAD: a flip at any byte (nonce, ciphertext or tag) opens to null',
        () {
      // GCM authenticates the whole entry: unlike CBC with a hash inside, no single
      // bit flip may yield a changed plaintext, wherever it lands.
      final c = CacheCipher(newMasterKey());
      final sealed = c.seal('scope|k', '{"rate_kg_ha":120,"zone":"A"}');
      final bytes = base64.decode(sealed);
      expect(bytes.length, 12 + 29 + 16, reason: 'nonce ‖ ct ‖ 128-bit tag');
      for (var i = 0; i < bytes.length; i++) {
        final tampered = Uint8List.fromList(bytes)..[i] ^= 0x01;
        expect(c.open('scope|k', base64.encode(tampered)), isNull,
            reason: 'byte $i');
      }
      expect(c.open('scope|k', base64.encode(bytes.sublist(0, 27))), isNull,
          reason: 'truncated');
      expect(c.open('scope|k', sealed), '{"rate_kg_ha":120,"zone":"A"}');
    });

    test('AEAD: each seal uses a fresh nonce', () {
      final c = CacheCipher(newMasterKey());
      final a = base64.decode(c.seal('scope|k', 'same'));
      final b = base64.decode(c.seal('scope|k', 'same'));
      expect(a.sublist(0, 12), isNot(equals(b.sublist(0, 12))));
      expect(a, isNot(equals(b)));
    });

    test('a key that is not 32 bytes is refused', () {
      expect(() => CacheCipher(List<int>.filled(16, 1)), throwsArgumentError);
    });

    test('a failing key vault never writes plaintext', () async {
      final store = MemoryRawCacheStore();
      final cache = OfflineReadCache(store: store, vault: _BrokenVault());
      await cache.write(tenantA, 'k', secret, fetched);
      expect(store.entries.values.join(), isNot(contains('SECRET-UREA')));
      expect(await cache.read(tenantA, 'k'), isNull);
    });
  });

  group('tenant isolation', () {
    test('tenant B cannot read tenant A (production policy)', () async {
      final cache = OfflineReadCache(
        store: MemoryRawCacheStore(),
        vault: MemoryCacheKeyVault(),
      );
      expect(await tenantBReadsTenantA(cache), isFalse);
    });

    test('tenant B cannot read tenant A even with both scopes kept on disk',
        () async {
      // بلا مسح عند التبديل: العزل يقوم على المفتاح والتشفير وحدهما.
      final cache = OfflineReadCache(
        store: MemoryRawCacheStore(),
        vault: MemoryCacheKeyVault(),
        clearOnScopeSwitch: false,
      );
      expect(await tenantBReadsTenantA(cache), isFalse);
      expect((await cache.read(tenantA, 'recipes:f1'))?.data, secret,
          reason: 'A still reads its own entry');
    });

    test("A's sealed entry copied under B's key does not open for B",
        () async {
      final store = MemoryRawCacheStore();
      final cache = OfflineReadCache(
        store: store,
        vault: MemoryCacheKeyVault(),
        clearOnScopeSwitch: false,
      );
      await cache.write(tenantA, 'k', secret, fetched);
      await cache.write(tenantB, 'k', {'other': true}, fetched);
      store.entries[cache.storageKeyFor(tenantB, 'k')] =
          store.entries[cache.storageKeyFor(tenantA, 'k')]!;
      expect(await cache.read(tenantB, 'k'), isNull);
    });

    test('negative control: dropping the tenant from the key leaks, and the '
        'isolation check catches it', () async {
      // نفس الخاصّيّة على كاش مكسور عمداً (المفتاح = المستخدم وحده): يجب أن
      // تكشف التسرّب. لو مرّت هنا لكان اختبار العزل أعلاه أعمى.
      for (final clearOnSwitch in [true, false]) {
        final broken = OfflineReadCache(
          store: MemoryRawCacheStore(),
          vault: MemoryCacheKeyVault(),
          clearOnScopeSwitch: clearOnSwitch,
          scopeIdOf: (s) => s.userId,
        );
        expect(await tenantBReadsTenantA(broken), isTrue,
            reason: 'clearOnScopeSwitch=$clearOnSwitch');
      }
    });
  });

  group('clearing', () {
    test('switching tenant wipes the previous tenant, entries and keys',
        () async {
      final store = MemoryRawCacheStore();
      final vault = MemoryCacheKeyVault();
      final cache = OfflineReadCache(store: store, vault: vault);
      await cache.write(tenantA, 'k', secret, fetched);
      expect(vault.keys, hasLength(1));
      await cache.write(tenantB, 'k2', {'b': 1}, fetched);
      expect(vault.keys, hasLength(1), reason: "A's key was deleted");
      expect(store.entries.keys,
          isNot(contains(cache.storageKeyFor(tenantA, 'k'))));
      expect(await cache.read(tenantA, 'k'), isNull);
    });

    test('clear() removes every entry and key', () async {
      final store = MemoryRawCacheStore();
      final vault = MemoryCacheKeyVault();
      final cache = OfflineReadCache(store: store, vault: vault);
      await cache.write(tenantA, 'k', secret, fetched);
      await cache.clear();
      expect(store.entries, isEmpty);
      expect(vault.keys, isEmpty);
      expect(await cache.read(tenantA, 'k'), isNull);
    });
  });

  group('production backends (Hive on disk + secure storage)', () {
    late Directory dir;

    setUp(() async {
      dir = Directory.systemTemp.createTempSync('offline_read_cache');
      Hive.init(dir.path);
      await Hive.openBox<dynamic>('settings'); // دليل التهيئة كما في main.dart
      FlutterSecureStorage.setMockInitialValues({});
    });

    tearDown(() async {
      await Hive.close();
      dir.deleteSync(recursive: true);
    });

    test('an entry survives a restart (Hive closed and reopened)', () async {
      await OfflineReadCache().write(tenantA, 'k', secret, fetched);
      await Hive.close(); // «قتل» العمليّة
      Hive.init(dir.path);
      await Hive.openBox<dynamic>('settings');
      final read = await OfflineReadCache().read(tenantA, 'k');
      expect(read?.data, secret);
      expect(read?.fetchedAt, fetched.toLocal());
      final raw = File('${dir.path}/$kOfflineReadCacheBox.hive')
          .readAsBytesSync();
      expect(latin1.decode(raw), isNot(contains('SECRET-UREA')));
    });

    test('logout runs the registered cleanup and clears the shared cache',
        () async {
      // مفتاحان في التخزين الآمن (نطاقان محفوظان معاً) كي يُختبَر حذف أكثر من
      // مفتاح، ومفتاح لا يخصّ الكاش يجب أن يبقى.
      FlutterSecureStorage.setMockInitialValues({
        'offline_read_cache.key.stale-scope': base64.encode(newMasterKey()),
        'access_token': 'kept-by-auth-service',
      });
      await OfflineReadCache.instance.write(tenantA, 'k', secret, fetched);
      expect(await OfflineReadCache.instance.read(tenantA, 'k'), isNotNull);
      final scope = SessionScope();
      AppRouter.instance.registerSessionCleanups(scope);
      expect(scope.owners, contains('field_plans'));
      final failed = await scope.endSession(
        const SessionEnd(tenantId: 'tenant-a', userId: 'u1'),
      );
      expect(failed, isNot(contains('field_plans')));
      expect(await OfflineReadCache.instance.read(tenantA, 'k'), isNull);
      expect(Hive.box<dynamic>(kOfflineReadCacheBox).keys,
          isNot(contains(OfflineReadCache.instance.storageKeyFor(tenantA, 'k'))));
      final keys = await const FlutterSecureStorage().readAll();
      expect(keys.keys.where((k) => k.startsWith('offline_read_cache.')),
          isEmpty);
      expect(keys['access_token'], 'kept-by-auth-service');
    });
  });
}

class _BrokenVault implements CacheKeyVault {
  @override
  Future<List<int>?> read(String scopeId) async => throw StateError('vault');
  @override
  Future<void> write(String scopeId, List<int> key) async =>
      throw StateError('vault');
  @override
  Future<void> deleteAll() async {}
}
