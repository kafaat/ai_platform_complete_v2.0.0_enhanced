// The three cases the integration session's review of W3-13 asks for, on the real
// OfflineReadCache and CachedLoader: an entry sealed under another tenant's or user's
// key, an entry moved to another storage key, and a tampered or truncated entry. None
// of them returns data; an entry that fails authentication is deleted, so the next load
// reads the server again instead of showing it.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/offline/cache_backends.dart';
import 'package:sahool_app/core/offline/cached_loader.dart';
import 'package:sahool_app/core/offline/offline_read_cache.dart';

const tenantA = CacheScope(tenantId: 'tenant-a', userId: 'u1');
const tenantB = CacheScope(tenantId: 'tenant-b', userId: 'u1');
const userA2 = CacheScope(tenantId: 'tenant-a', userId: 'u2');
final fetched = DateTime.utc(2026, 11, 10, 6, 30);
const recipe = {'recipe': 'UREA-46', 'rate': 120};

const offline = ApiException(
  kind: ApiErrorKind.network,
  messageAr: 'لا اتّصال',
);

OfflineReadCache _cache(MemoryRawCacheStore store, MemoryCacheKeyVault vault) =>
    OfflineReadCache(store: store, vault: vault, clearOnScopeSwitch: false);

void main() {
  test(
    'an entry sealed under another tenant or user key returns nothing',
    () async {
      final store = MemoryRawCacheStore();
      final cache = _cache(store, MemoryCacheKeyVault());
      await cache.write(tenantA, 'k', recipe, fetched);
      final sealedForA = store.entries[cache.storageKeyFor(tenantA, 'k')]!;
      for (final other in [tenantB, userA2]) {
        // A's ciphertext placed under the other scope's own storage key.
        await cache.write(other, 'k', {'own': true}, fetched);
        store.entries[cache.storageKeyFor(other, 'k')] = sealedForA;
        expect(await cache.read(other, 'k'), isNull, reason: other.userId);
        expect(
          store.entries.containsKey(cache.storageKeyFor(other, 'k')),
          isFalse,
          reason: 'the unreadable entry is deleted',
        );
      }
      expect(
        (await cache.read(tenantA, 'k'))!.data,
        recipe,
        reason: 'A still reads its own',
      );
    },
  );

  test(
    'an entry moved to another storage key of the same scope returns nothing',
    () async {
      final store = MemoryRawCacheStore();
      final cache = _cache(store, MemoryCacheKeyVault());
      await cache.write(tenantA, 'recipes:f1', recipe, fetched);
      final moved = store.entries[cache.storageKeyFor(tenantA, 'recipes:f1')]!;
      store.entries[cache.storageKeyFor(tenantA, 'recipes:f2')] = moved;
      expect(await cache.read(tenantA, 'recipes:f2'), isNull);
      expect(
        store.entries.containsKey(cache.storageKeyFor(tenantA, 'recipes:f2')),
        isFalse,
      );
      expect((await cache.read(tenantA, 'recipes:f1'))!.data, recipe);
    },
  );

  test('a tampered or truncated entry is deleted, never returned', () async {
    for (final damage in <String Function(String)>[
      (s) {
        final b = base64.decode(s);
        b[b.length ~/ 2] ^= 0x01;
        return base64.encode(b);
      },
      (s) => base64.encode(base64.decode(s).sublist(0, 20)),
      (s) => 'not base64 at all',
    ]) {
      final store = MemoryRawCacheStore();
      final cache = _cache(store, MemoryCacheKeyVault());
      await cache.write(tenantA, 'k', recipe, fetched);
      final key = cache.storageKeyFor(tenantA, 'k');
      store.entries[key] = damage(store.entries[key]!);
      expect(await cache.read(tenantA, 'k'), isNull);
      expect(store.entries.containsKey(key), isFalse);
    }
  });

  test(
    'after corruption, offline shows the error and online reads the server again',
    () async {
      final store = MemoryRawCacheStore();
      final cache = _cache(store, MemoryCacheKeyVault());
      final loader = CachedLoader(cache: cache, scope: () => tenantA);
      final key = cache.storageKeyFor(tenantA, 'recipes:f1');
      Map<String, Object?> parse(Object? j) =>
          Map<String, Object?>.from(j! as Map);

      await loader.load(
        key: 'recipes:f1',
        fetch: () async => recipe,
        parse: parse,
      );
      final b = base64.decode(store.entries[key]!);
      b[b.length - 1] ^= 0x01;
      store.entries[key] = base64.encode(b);

      // Offline: the tampered copy is not shown; the original error is.
      await expectLater(
        loader.load(
          key: 'recipes:f1',
          fetch: () async => throw offline,
          parse: parse,
        ),
        throwsA(isA<ApiException>()),
      );
      expect(store.entries.containsKey(key), isFalse);

      // Online again: the server answer is shown and cached afresh.
      final fresh = await loader.load(
        key: 'recipes:f1',
        fetch: () async => {'recipe': 'UREA-46', 'rate': 90},
        parse: parse,
      );
      expect(fresh.fromCache, isFalse);
      expect(fresh.data['rate'], 90);
      expect((await cache.read(tenantA, 'recipes:f1'))!.data, {
        'recipe': 'UREA-46',
        'rate': 90,
      });
    },
  );
}
