// D2 (R08/R09): تجديد الجلسة مربوط بجيلها ومالكها، وردود متأخّرة لا تمسّ جلسة
// أحدث. ApiClient الحقيقيّ (interceptors نفسها) فوق محوّل HTTP يتحكّم بتوقيت كلّ
// ردّ عبر Completer، فيُفرَض ترتيب السباق الحقيقيّ: الطلب يصل «الخادم»، يتبدّل
// المالك، ثمّ يصل الردّ. نسختان من المخزن: في الذاكرة، والحقيقيّ (AuthService
// فوق تخزين آمن وهميّ) مع إعادة فتحه من القرص بعد السباق.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/services/auth_service.dart';

import 'fake_http.dart';

/// يصرّف المهامّ الدقيقة والأحداث المعلّقة (لا مؤقّتات حقيقيّة).
Future<void> settle() async {
  for (var i = 0; i < 20; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

Future<Object?> outcome(Future<dynamic> call) =>
    call.then<Object?>((v) => v, onError: (Object e) => e);

ApiClient clientFor(FakeAdapter adapter, TokenStore tokens) => ApiClient(
      baseUrl: 'https://api.test.invalid',
      tokens: tokens,
      adapter: adapter,
      retryBaseDelay: const Duration(milliseconds: 1),
      retryJitterMs: 0,
    );

void main() {
  final expiredA = fakeJwt(const Duration(hours: -1), sub: 'A-old');
  final validA = fakeJwt(const Duration(hours: 1), sub: 'A1');
  final freshA = fakeJwt(const Duration(hours: 1), sub: 'A2');
  final validB = fakeJwt(const Duration(hours: 1), sub: 'B1');
  final expiredB = fakeJwt(const Duration(hours: -1), sub: 'B-old');
  final freshB = fakeJwt(const Duration(hours: 1), sub: 'B2');

  group('R08 — one refresh for many requests, no loop', () {
    test('10 concurrent requests with an expired token share ONE refresh; '
        'keys and bodies are kept', () async {
      final tokens = MemoryTokenStore(
          accessToken: expiredA, refreshToken: 'rA', owner: 'A');
      final gate = Completer<void>();
      final adapter = FakeAdapter((o) async {
        if (o.path == '/auth/refresh') {
          await gate.future;
          return FakeReply(200, {'access_token': freshA, 'refresh_token': 'rA2'});
        }
        return FakeReply(200, {'path': o.path});
      });
      final client = clientFor(adapter, tokens);

      final calls = [
        for (var i = 0; i < 5; i++) client.get('/api/v1/read/$i'),
        for (var i = 0; i < 5; i++)
          client.post('/api/v1/write/$i',
              data: {'n': i}, idempotencyKey: IdempotencyKey('k-$i')),
      ];
      await settle();
      // كلّ العشرة تنتظر التجديد الواحد؛ لم يصل الخادمَ غيرُه.
      expect(adapter.requests.map((r) => r.path), ['/auth/refresh']);
      gate.complete();
      await Future.wait(calls);

      expect(adapter.to('/auth/refresh'), hasLength(1));
      expect(adapter.requests, hasLength(11), reason: 'لا حلقة ولا تكرار');
      for (var i = 0; i < 5; i++) {
        final w = adapter.to('/api/v1/write/$i').single;
        expect(w.headers['Authorization'], 'Bearer $freshA');
        expect(w.headers[kIdempotencyHeader], 'k-$i');
        expect(w.data, {'n': i});
        expect(adapter.to('/api/v1/read/$i').single.headers['Authorization'],
            'Bearer $freshA');
      }
      expect(tokens.refreshToken, 'rA2');
    });

    test('late 401s for the old token retry with the newer token, without a '
        'second refresh (refresh tokens are single-use)', () async {
      final tokens =
          MemoryTokenStore(accessToken: validA, refreshToken: 'rA', owner: 'A');
      // الخادم: رمز A1 مرفوض، A2 مقبول. رمز التحديث أحاديّ الاستعمال: rA مرّة
      // واحدة، وأيّ تجديد ثانٍ (rA2) يُرفَض كما يرفضه GETDEL في services/auth.
      final late = <String, Completer<void>>{
        for (var i = 5; i < 10; i++) '/api/v1/w/$i': Completer<void>(),
      };
      final adapter = FakeAdapter((o) async {
        if (o.path == '/auth/refresh') {
          final body = o.data as Map;
          if (body['refresh_token'] == 'rA') {
            return FakeReply(
                200, {'access_token': freshA, 'refresh_token': 'rA2'});
          }
          return const FakeReply(401, {'detail': 'refresh token reused'});
        }
        if (o.headers['Authorization'] == 'Bearer $freshA') {
          return FakeReply(200, {'ok': o.path});
        }
        await late[o.path]?.future; // ردّ 401 يتأخّر لنصف الطلبات
        return const FakeReply(401, {'detail': 'expired'});
      });
      final client = clientFor(adapter, tokens);
      final expired = <void>[];
      final sub = client.onSessionExpired.listen(expired.add);

      final calls = [
        for (var i = 0; i < 10; i++)
          client.post('/api/v1/w/$i',
              data: {'v': i}, idempotencyKey: IdempotencyKey('k-$i')),
      ];
      await settle();
      // الخمسة الأولى رُفضت وجُدِّدت الجلسة وأُعيدت؛ الخمسة الأخرى ما زالت عند
      // الخادم بالرمز القديم.
      expect(adapter.to('/auth/refresh'), hasLength(1));
      expect(tokens.accessToken, freshA);
      for (final c in late.values) {
        c.complete();
      }
      final results = await Future.wait(calls);

      expect(results, [for (var i = 0; i < 10; i++) {'ok': '/api/v1/w/$i'}]);
      expect(adapter.to('/auth/refresh'), hasLength(1),
          reason: '401 متأخّرة لرمز أقدم لا تستهلك رمز تحديث ثانياً');
      for (var i = 0; i < 10; i++) {
        final sent = adapter.to('/api/v1/w/$i');
        expect(sent, hasLength(2), reason: 'إرسال + إعادة واحدة، بلا حلقة');
        expect(sent.last.headers['Authorization'], 'Bearer $freshA');
        expect(sent.map((r) => r.headers[kIdempotencyHeader]), ['k-$i', 'k-$i']);
        expect(sent.map((r) => r.data), [
          {'v': i},
          {'v': i},
        ]);
      }
      expect(tokens.clears, 0);
      expect(expired, isEmpty);
      await sub.cancel();
    });
  });

  group('R09 — owner switch during refresh (memory store)', () {
    late MemoryTokenStore tokens;
    late Completer<FakeReply> refreshA;
    late FakeAdapter adapter;
    late ApiClient client;
    late List<void> expired;
    late StreamSubscription<void> sub;

    setUp(() {
      tokens = MemoryTokenStore(
          accessToken: expiredA, refreshToken: 'rA', owner: 'A');
      refreshA = Completer<FakeReply>();
      adapter = FakeAdapter((o) async {
        if (o.path == '/auth/refresh') {
          final body = o.data as Map;
          if (body['refresh_token'] == 'rA') return refreshA.future;
          if (body['refresh_token'] == 'rB') {
            return FakeReply(200, {'access_token': freshB, 'refresh_token': 'rB2'});
          }
          return const FakeReply(401, {});
        }
        return FakeReply(200, {'auth': o.headers['Authorization']});
      });
      client = clientFor(adapter, tokens);
      expired = [];
      sub = client.onSessionExpired.listen(expired.add);
    });

    tearDown(() => sub.cancel());

    Future<Future<Object?>> startOldSessionWrite() async {
      final call = outcome(client.post('/api/v1/fields',
          data: {'name': 'A-field'},
          idempotencyKey: const IdempotencyKey('k-A')));
      await settle();
      expect(adapter.to('/auth/refresh'), hasLength(1));
      return call;
    }

    test('late SUCCESS for the old owner neither saves its tokens nor sends '
        'the old write with any token', () async {
      final call = await startOldSessionWrite();
      tokens.switchOwner('B', access: validB, refresh: 'rB');
      refreshA.complete(
          FakeReply(200, {'access_token': freshA, 'refresh_token': 'rA2'}));
      final result = await call;
      await settle();

      expect(tokens.accessToken, validB);
      expect(tokens.refreshToken, 'rB');
      expect(tokens.owner, 'B');
      // كتابة الجلسة السابقة لم تُرسَل برمز B ولا برمز A2.
      expect(adapter.to('/api/v1/fields'), isEmpty);
      expect(result, isA<ApiException>()
          .having((e) => e.kind, 'kind', ApiErrorKind.cancelled));
      expect(expired, isEmpty);
    });

    test('late REJECTION for the old owner neither clears nor expires the new '
        'session', () async {
      final call = await startOldSessionWrite();
      tokens.switchOwner('B', access: validB, refresh: 'rB');
      refreshA.complete(const FakeReply(401, {'detail': 'refresh token reused'}));
      await call;
      await settle();

      expect(tokens.accessToken, validB);
      expect(tokens.refreshToken, 'rB');
      expect(tokens.clears, 0);
      expect(expired, isEmpty, reason: 'لا «انتهت الجلسة» لجلسة B السليمة');
      expect(adapter.to('/api/v1/fields'), isEmpty);
    });

    test('the new owner does not join the old owner\'s refresh: it refreshes '
        'with its own token and never receives the old one', () async {
      final oldCall = await startOldSessionWrite();
      tokens.switchOwner('B', access: expiredB, refresh: 'rB');
      final newCall = client.get('/api/v1/farms');
      await settle();
      // B جدّد برمزه بينما تجديد A ما زال معلّقاً.
      expect(adapter.to('/auth/refresh').map((r) => (r.data as Map)['refresh_token']),
          ['rA', 'rB']);
      refreshA.complete(
          FakeReply(200, {'access_token': freshA, 'refresh_token': 'rA2'}));
      expect(await newCall, {'auth': 'Bearer $freshB'});
      await oldCall;
      await settle();

      expect(tokens.accessToken, freshB);
      expect(tokens.refreshToken, 'rB2');
      expect(adapter.requests.where(
              (r) => r.headers['Authorization'] == 'Bearer $freshA'),
          isEmpty);
    });

    test('a late 401 for an old-owner request is not refreshed or retried '
        'with the new owner\'s tokens, and does not clear them', () async {
      tokens.switchOwner('A', access: validA, refresh: 'rA');
      final held = Completer<void>();
      final server = FakeAdapter((o) async {
        if (o.path == '/auth/refresh') {
          return FakeReply(200, {'access_token': freshB, 'refresh_token': 'rB2'});
        }
        if (o.path == '/api/v1/fields') {
          await held.future;
          return const FakeReply(401, {'detail': 'revoked'});
        }
        return const FakeReply(200, {});
      });
      final c = clientFor(server, tokens);
      final call = outcome(c.post('/api/v1/fields',
          data: {'name': 'A-field'},
          idempotencyKey: const IdempotencyKey('k-A')));
      await settle();
      expect(server.to('/api/v1/fields').single.headers['Authorization'],
          'Bearer $validA');

      tokens.switchOwner('B', access: validB, refresh: 'rB');
      held.complete();
      final result = await call;
      await settle();

      expect(result, isA<ApiException>()
          .having((e) => e.kind, 'kind', ApiErrorKind.unauthorized));
      expect(server.to('/auth/refresh'), isEmpty);
      expect(server.to('/api/v1/fields'), hasLength(1),
          reason: 'لا إعادة لطلب A برموز B');
      expect(tokens.accessToken, validB);
      expect(tokens.refreshToken, 'rB');
      expect(tokens.clears, 0);
    });
  });

  group('R09 — real AuthService store, reopened from storage', () {
    const store = AuthServiceTokenStore();
    final auth = AuthService.instance;

    Future<void> signInA() async {
      FlutterSecureStorage.setMockInitialValues({
        'access_token': expiredA,
        'refresh_token': 'rA',
        'user_id': 'A',
        'user_profile': '{"user_id":"A","tenant_id":"t-A","role":"owner"}',
      });
      await auth.loadSaved();
      expect(auth.refreshToken, 'rA');
    }

    Future<void> switchToB() async {
      // خروج A ثمّ دخول B (ما يفعله ApiService.logout ثمّ AuthApi.login).
      await auth.clearAuth();
      await auth.saveToken(validB,
          refresh: 'rB',
          profile: {'user_id': 'B', 'tenant_id': 't-B', 'role': 'owner'});
    }

    Future<void> expectBPersisted() async {
      await settle();
      await auth.loadSaved(); // أعِد فتح المخزن: ما على القرص هو الحكم
      expect(auth.token, validB);
      expect(auth.refreshToken, 'rB');
      expect(auth.userId, 'B');
      expect(auth.tenantId, 't-B');
    }

    tearDown(() => auth.clearAuth());

    for (final late in [
      FakeReply(200, {'access_token': freshA, 'refresh_token': 'rA2'}),
      const FakeReply(401, {'detail': 'refresh token reused'}),
    ]) {
      test('late ${late.status} from A\'s refresh after switching to B keeps B '
          'on disk', () async {
        await signInA();
        final gate = Completer<FakeReply>();
        final adapter = FakeAdapter((o) async {
          if (o.path == '/auth/refresh') return gate.future;
          return FakeReply(200, {'auth': o.headers['Authorization']});
        });
        final client = clientFor(adapter, store);
        final expired = <void>[];
        final sub = client.onSessionExpired.listen(expired.add);
        final call = outcome(client.get('/api/v1/farms'));
        await settle();
        expect(adapter.to('/auth/refresh').single.data, {'refresh_token': 'rA'});

        await switchToB();
        gate.complete(late);
        await call;

        expect(expired, isEmpty);
        expect(adapter.requests.where(
                (r) => r.headers['Authorization'] == 'Bearer $validB'),
            isEmpty);
        await expectBPersisted();
        await sub.cancel();
      });
    }

    test('logout while a refresh is being written does not resurrect the old '
        'session on disk', () async {
      await signInA();
      // الحفظ بدأ (أوّل كتابة معلّقة) ثمّ خرج المستخدم قبل أن يكتمل.
      final saving = store.saveTokens(freshA, refresh: 'rA2');
      final logout = auth.clearAuth();
      await Future.wait([saving, logout]);
      expect(auth.refreshToken, isNull);
      expect(auth.canResumeSession, isFalse);

      await settle();
      await auth.loadSaved();
      expect(auth.token, isNull);
      expect(auth.refreshToken, isNull,
          reason: 'رمز تحديث A لا يُكتب على القرص بعد الخروج');
      expect(auth.canResumeSession, isFalse);
    });

    test('generation-conditional save: a stale save is refused and a racing '
        'login wins in memory and on disk', () async {
      await signInA();
      final gA = store.generation;

      // (1) الحفظ يبدأ لجيل A ثمّ يدخل B فوراً (قبل أيّ await).
      final saved = store.saveTokens(freshA, refresh: 'rA2', generation: gA);
      final login = switchToB();
      expect(await saved, isTrue, reason: 'جيل A كان حاليّاً لحظة الفحص');
      await login;
      expect(auth.token, validB);
      expect(auth.refreshToken, 'rB');
      await expectBPersisted();

      // (2) بعد التبديل: حفظ ومسح بجيل A مرفوضان ولا يمسّان B.
      expect(store.generation, isNot(gA));
      expect(await store.saveTokens(freshA, refresh: 'rA2', generation: gA),
          isFalse);
      expect(await store.clear(generation: gA), isFalse);
      await expectBPersisted();
    });

    test('the session generation moves on restore, login, logout and clear, '
        'not on a refresh', () async {
      await signInA();
      final g0 = auth.sessionGeneration;
      expect(await auth.saveRefreshedToken(g0, freshA, refresh: 'rA2'), isTrue);
      expect(auth.sessionGeneration, g0, reason: 'التجديد لا يبدّل الجلسة');
      await auth.saveToken(validB, refresh: 'rB', profile: {'user_id': 'B'});
      final g1 = auth.sessionGeneration;
      expect(g1, greaterThan(g0));
      await auth.clearAuth();
      final g2 = auth.sessionGeneration;
      expect(g2, greaterThan(g1));
      await auth.loadSaved();
      expect(auth.sessionGeneration, greaterThan(g2));
      expect(auth.sessionOwner, isNull);
    });
  });

  test('the refresh request never passes through the auth interceptor',
      () async {
    final tokens =
        MemoryTokenStore(accessToken: expiredA, refreshToken: 'rA', owner: 'A');
    final adapter = FakeAdapter((o) async {
      if (o.path == '/auth/refresh') {
        return FakeReply(200, {'access_token': freshA});
      }
      return const FakeReply(200, {});
    });
    await clientFor(adapter, tokens).get('/api/v1/x');
    final refresh = adapter.to('/auth/refresh').single;
    expect(refresh.headers.containsKey('Authorization'), isFalse);
    expect(refresh.extra.containsKey('session_generation'), isFalse);
    expect(refresh.extra['is_refresh'], isTrue);
  });

  test('a network failure during refresh keeps the session (unknown, not '
      'rejected)', () async {
    final tokens =
        MemoryTokenStore(accessToken: expiredA, refreshToken: 'rA', owner: 'A');
    final adapter = FakeAdapter((o) async {
      if (o.path == '/auth/refresh') {
        return const FakeReply.fail(DioExceptionType.connectionError);
      }
      return const FakeReply(401, {});
    });
    final client = clientFor(adapter, tokens);
    final expired = <void>[];
    final sub = client.onSessionExpired.listen(expired.add);
    await outcome(client.get('/api/v1/x'));
    await settle();
    expect(tokens.refreshToken, 'rA');
    expect(tokens.clears, 0);
    expect(expired, isEmpty);
    await sub.cancel();
  });
}
