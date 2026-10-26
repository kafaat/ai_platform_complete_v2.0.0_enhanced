// اختبارات ApiClient الحقيقيّ (interceptors نفسها) عبر محوّل HTTP مزيّف:
// تحديث التوكن الموحّد، عدم الدوران على /auth/refresh، مسح الجلسة فقط عند رفض
// الخادم، إعادة المحاولة المشروطة بـIdempotency-Key، وتحويل الأخطاء المُنمَّط.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import 'fake_http.dart';

void main() {
  group('token refresh', () {
    test('expired access token: one refresh, then the request carries the new token',
        () async {
      final fresh = fakeJwt(const Duration(hours: 1), sub: 'fresh');
      final tokens = MemoryTokenStore(
          accessToken: fakeJwt(const Duration(hours: -1)), refreshToken: 'r1');
      final adapter = FakeAdapter((o) async {
        if (o.path == '/auth/refresh') {
          return FakeReply(200, {'access_token': fresh, 'refresh_token': 'r2'});
        }
        return const FakeReply(200, {'ok': true});
      });
      final client = testClient(adapter, tokens);

      expect(await client.get('/api/v1/farms'), {'ok': true});

      final refresh = adapter.to('/auth/refresh');
      expect(refresh, hasLength(1));
      // طلب التحديث لا يمرّ بمعترض المصادقة: بلا Authorization وبجسم رمز التحديث.
      expect(refresh.single.headers.containsKey('Authorization'), isFalse);
      expect(refresh.single.data, {'refresh_token': 'r1'});
      expect(adapter.to('/api/v1/farms').single.headers['Authorization'],
          'Bearer $fresh');
      expect(tokens.accessToken, fresh);
      expect(tokens.refreshToken, 'r2');
    });

    test('concurrent requests after expiry share a single refresh call', () async {
      final fresh = fakeJwt(const Duration(hours: 1));
      final tokens = MemoryTokenStore(
          accessToken: fakeJwt(const Duration(hours: -1)), refreshToken: 'r1');
      final gate = Completer<void>();
      final adapter = FakeAdapter((o) async {
        if (o.path == '/auth/refresh') {
          await gate.future; // أبقِ التحديث معلّقاً حتّى تصل كلّ الطلبات
          return FakeReply(200, {'access_token': fresh});
        }
        return const FakeReply(200, []);
      });
      final client = testClient(adapter, tokens);

      final calls = [
        client.get('/api/v1/a'),
        client.get('/api/v1/b'),
        client.get('/api/v1/c'),
      ];
      await Future<void>.delayed(const Duration(milliseconds: 10));
      gate.complete();
      await Future.wait(calls);

      expect(adapter.to('/auth/refresh'), hasLength(1),
          reason: 'رمز التحديث أحاديّ الاستعمال على الخادم: تحديثان = خروج');
      for (final p in ['/api/v1/a', '/api/v1/b', '/api/v1/c']) {
        expect(adapter.to(p).single.headers['Authorization'], 'Bearer $fresh');
      }
    });

    test('401 on a valid-looking token: refresh once and retry once', () async {
      final fresh = fakeJwt(const Duration(hours: 1), sub: 'fresh');
      final tokens = MemoryTokenStore(
          accessToken: fakeJwt(const Duration(hours: 1)), refreshToken: 'r1');
      var firstCall = true;
      final adapter = FakeAdapter((o) async {
        if (o.path == '/auth/refresh') {
          return FakeReply(200, {'access_token': fresh});
        }
        if (firstCall) {
          firstCall = false;
          return const FakeReply(401, {'detail': 'expired'});
        }
        return const FakeReply(200, {'ok': 1});
      });
      final client = testClient(adapter, tokens);

      expect(await client.get('/api/v1/tasks'), {'ok': 1});
      expect(adapter.to('/auth/refresh'), hasLength(1));
      final calls = adapter.to('/api/v1/tasks');
      expect(calls, hasLength(2));
      expect(calls.last.headers['Authorization'], 'Bearer $fresh');
    });

    test('a second 401 after the retry is surfaced, not looped', () async {
      final tokens = MemoryTokenStore(
          accessToken: fakeJwt(const Duration(hours: 1)), refreshToken: 'r1');
      final adapter = FakeAdapter((o) async {
        if (o.path == '/auth/refresh') {
          return FakeReply(200, {'access_token': fakeJwt(const Duration(hours: 1))});
        }
        return const FakeReply(401, {'detail': 'no'});
      });
      final client = testClient(adapter, tokens);

      await expectLater(
          client.get('/api/v1/x'),
          throwsA(isA<ApiException>()
              .having((e) => e.kind, 'kind', ApiErrorKind.unauthorized)));
      expect(adapter.to('/auth/refresh'), hasLength(1));
      expect(adapter.to('/api/v1/x'), hasLength(2));
    });

    test('server rejects the refresh token: session cleared and announced',
        () async {
      final tokens = MemoryTokenStore(
          accessToken: fakeJwt(const Duration(hours: -1)), refreshToken: 'used');
      final adapter = FakeAdapter((o) async {
        if (o.path == '/auth/refresh') return const FakeReply(401, {});
        return const FakeReply(401, {});
      });
      final client = testClient(adapter, tokens);
      final expired = client.onSessionExpired.first;

      await expectLater(client.get('/api/v1/x'), throwsA(isA<ApiException>()));
      await expired.timeout(const Duration(seconds: 1));
      expect(tokens.accessToken, isNull);
      expect(tokens.refreshToken, isNull);
    });

    test('refresh fails on the network: the refresh token is kept', () async {
      final tokens = MemoryTokenStore(
          accessToken: fakeJwt(const Duration(hours: -1)), refreshToken: 'keep');
      final adapter = FakeAdapter((o) async {
        if (o.path == '/auth/refresh') {
          return const FakeReply.fail(DioExceptionType.connectionError);
        }
        return const FakeReply(401, {});
      });
      final client = testClient(adapter, tokens);

      await expectLater(client.get('/api/v1/x'), throwsA(isA<ApiException>()));
      expect(tokens.refreshToken, 'keep');
      expect(tokens.clears, 0);
    });

    test('unauthenticated calls carry no bearer and never refresh', () async {
      final tokens = MemoryTokenStore(
          accessToken: fakeJwt(const Duration(hours: -1)), refreshToken: 'r');
      final adapter = FakeAdapter((o) async => const FakeReply(200, {}));
      final client = testClient(adapter, tokens);

      await client.send('POST', '/auth/login',
          data: {'email': 'a'}, authenticated: false);
      expect(adapter.to('/auth/refresh'), isEmpty);
      expect(adapter.to('/auth/login').single.headers['Authorization'], isNull);
    });

    test('every request carries a distinct X-Request-ID', () async {
      final adapter = FakeAdapter((o) async => const FakeReply(200, {}));
      final client = testClient(adapter, MemoryTokenStore());
      await client.get('/a');
      await client.get('/b');
      final ids = adapter.requests.map((r) => r.headers['X-Request-ID']).toSet();
      expect(ids, hasLength(2));
      expect(ids.every((id) => id is String && id.isNotEmpty), isTrue);
    });
  });

  group('retry and Idempotency-Key', () {
    test('a write with a key sends the header and is retried with the same key',
        () async {
      var n = 0;
      final adapter = FakeAdapter((o) async =>
          n++ == 0 ? const FakeReply(503, {}) : const FakeReply(201, {'id': 1}));
      final client = testClient(adapter, MemoryTokenStore());
      const key = IdempotencyKey('k-123');

      expect(await client.post('/api/v1/farms', data: {}, idempotencyKey: key),
          {'id': 1});
      final calls = adapter.to('/api/v1/farms');
      expect(calls, hasLength(2));
      expect(calls.map((c) => c.headers[kIdempotencyHeader]), ['k-123', 'k-123']);
    });

    test('a write without a key is never retried', () async {
      final adapter = FakeAdapter((o) async => const FakeReply(502, {}));
      final client = testClient(adapter, MemoryTokenStore());

      await expectLater(client.post('/api/v1/farms', data: {}),
          throwsA(isA<ApiException>()));
      expect(adapter.to('/api/v1/farms'), hasLength(1));
      expect(adapter.requests.single.headers.containsKey(kIdempotencyHeader),
          isFalse);
    });

    test('reads are retried up to the cap on 502/503/504', () async {
      final adapter = FakeAdapter((o) async => const FakeReply(504, {}));
      final client = testClient(adapter, MemoryTokenStore());

      await expectLater(client.get('/api/v1/fields'),
          throwsA(isA<ApiException>()
              .having((e) => e.kind, 'kind', ApiErrorKind.server)));
      expect(adapter.to('/api/v1/fields'), hasLength(4)); // 1 + 3 retries
    });

    test('multipart bodies are not retried even with a key', () async {
      final adapter = FakeAdapter((o) async => const FakeReply(503, {}));
      final client = testClient(adapter, MemoryTokenStore());

      await expectLater(
          client.post('/upload',
              data: FormData.fromMap({'a': '1'}),
              idempotencyKey: const IdempotencyKey('k')),
          throwsA(isA<ApiException>()));
      expect(adapter.to('/upload'), hasLength(1));
    });

    test('IdempotencyKey.generate gives distinct UUIDv7 values', () {
      final a = IdempotencyKey.generate().value;
      final b = IdempotencyKey.generate().value;
      expect(a, isNot(b));
      expect(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-7').hasMatch(a), isTrue);
    });
  });

  group('error mapping', () {
    Future<ApiException> failWith(FakeReply reply) async {
      final adapter = FakeAdapter((o) async => reply);
      final client = testClient(adapter, MemoryTokenStore());
      try {
        await client.post('/x', data: {});
      } on ApiException catch (e) {
        return e;
      }
      fail('expected ApiException');
    }

    test('status codes keep their honest Arabic messages', () async {
      final cases = <int, (ApiErrorKind, String)>{
        503: (ApiErrorKind.unavailable,
            'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).'),
        403: (ApiErrorKind.forbidden, 'لا تملك صلاحيّة الوصول إلى هذا القسم.'),
        404: (ApiErrorKind.notFound, 'العنصر غير موجود.'),
        409: (ApiErrorKind.conflict, 'تعارض: السجلّ موجود مسبقاً.'),
      };
      for (final entry in cases.entries) {
        final e = await failWith(FakeReply(entry.key, {'detail': 'x'}));
        expect(e.kind, entry.value.$1, reason: '${entry.key}');
        expect(e.statusCode, entry.key);
        expect(e.messageAr, entry.value.$2);
        expect(e.requestId, isNotNull);
      }
    });

    test('401 without a session maps to unauthorized', () async {
      final e = await failWith(const FakeReply(401, {}));
      expect(e.kind, ApiErrorKind.unauthorized);
      expect(e.messageAr, 'انتهت الجلسة — يُرجى تسجيل الدخول من جديد.');
    });

    test('422 shows the server validation messages', () async {
      final e = await failWith(const FakeReply(422, {
        'detail': [
          {'loc': ['body', 'name'], 'msg': 'الاسم مطلوب', 'type': 'missing'},
        ],
      }));
      expect(e.kind, ApiErrorKind.validation);
      expect(e.messageAr, 'الاسم مطلوب');
    });

    test('timeouts and connection errors are connectivity, not "unexpected"',
        () async {
      final t = await failWith(
          const FakeReply.fail(DioExceptionType.receiveTimeout));
      expect(t.kind, ApiErrorKind.timeout);
      expect(t.isConnectivity, isTrue);
      expect(t.messageAr, contains('مهلة'));

      final c = await failWith(
          const FakeReply.fail(DioExceptionType.connectionError));
      expect(c.kind, ApiErrorKind.network);
      expect(c.messageAr, 'تعذّر الاتصال بالخادم — تحقّق من الشبكة.');
    });

    test('ApiException.from keeps FormatException messages', () {
      final e = ApiException.from(const FormatException('شكل غير متوقّع'));
      expect(e.kind, ApiErrorKind.unknown);
      expect(e.messageAr, 'شكل غير متوقّع');
    });
  });
}
