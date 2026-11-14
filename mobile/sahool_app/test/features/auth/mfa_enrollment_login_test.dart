// Password-proven MFA enrollment (403 challenge -> setup -> activate -> login).
// Tests use the app's real ApiClient interceptors and FakeAdapter.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/auth/data/auth_api.dart';
import 'package:sahool_app/features/auth/presentation/login_screen.dart';

import '../../core/fake_http.dart';
import 'auth_test_app.dart';

const _challenge = FakeReply(
  403,
  {
    'detail': 'MFA enrollment required',
    'enrollment_token': 'proof-setup',
    'expires_in': 600,
  },
  {
    'x-mfa-enrollment-required': ['true'],
  },
);
const _setup = FakeReply(200, {
  'secret': 'EXAMPLETESTBASE32KEY',
  'provisioning_uri': 'otpauth://totp/SAHOOL:test?secret=EXAMPLETESTBASE32KEY',
  'enrollment_token': 'proof-activate',
  'expires_in': 600,
});

Future<void> _submit(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const ValueKey('login_email')),
    'demo@example.com',
  );
  await tester.enterText(
    find.byKey(const ValueKey('login_password')),
    'password',
  );
  await tester.tap(find.byKey(const ValueKey('login_submit')));
  await tester.pumpAndSettle();
}

void main() {
  Future<(FakeAdapter, MemoryTokenStore)> mount(
    WidgetTester tester,
    FakeHandler handler,
  ) async {
    final store = MemoryTokenStore();
    final adapter = FakeAdapter(handler);
    final api = AuthApi(testClient(adapter, store));
    await tester.pumpWidget(authTestApp(LoginScreen(api: api)));
    return (adapter, store);
  }

  testWidgets(
    '403 with proof + header offers setup but never starts it automatically',
    (tester) async {
      final (adapter, store) = await mount(tester, (o) async => _challenge);
      await _submit(tester);
      expect(find.byKey(const ValueKey('enroll_start')), findsOneWidget);
      expect(adapter.requests.length, 1);
      expect(store.accessToken, isNull);
    },
  );

  testWidgets('403 without explicit enrollment header stays forbidden', (
    tester,
  ) async {
    await mount(
      tester,
      (o) async =>
          const FakeReply(403, {'enrollment_token': 'malicious-proof'}),
    );
    await _submit(tester);
    expect(find.byKey(const ValueKey('enroll_start')), findsNothing);
    expect(find.textContaining('غير مسموح'), findsOneWidget);
  });

  testWidgets('full flow uses two distinct proofs; no session is created', (
    tester,
  ) async {
    final (adapter, store) = await mount(tester, (o) async {
      if (o.path == '/auth/login') return _challenge;
      if (o.path == '/auth/mfa/setup') return _setup;
      if (o.path == '/auth/mfa/activate') {
        return const FakeReply(200, {
          'mfa_enabled': true,
          'recovery_codes': ['keep-me-once', 'backup-only'],
        });
      }
      return const FakeReply(404);
    });
    await _submit(tester);
    await tester.tap(find.byKey(const ValueKey('enroll_start')));
    await tester.pumpAndSettle();
    final setup = adapter.to('/auth/mfa/setup').single;
    expect(setup.headers['Authorization'], 'Bearer proof-setup');
    expect(find.byKey(const ValueKey('enroll_secret')), findsOneWidget);
    await tester.enterText(find.byKey(const ValueKey('enroll_code')), '١٢٣٤٥٦');
    await tester.tap(find.byKey(const ValueKey('enroll_activate')));
    await tester.pumpAndSettle();
    final activation = adapter.to('/auth/mfa/activate').single;
    expect(activation.headers['Authorization'], 'Bearer proof-activate');
    expect((activation.data as Map)['code'], '123456');
    expect(find.byKey(const ValueKey('enroll_recovery_codes')), findsOneWidget);
    expect(find.textContaining('keep-me-once'), findsWidgets);
    expect(
      store.accessToken,
      isNull,
    ); // No access session is minted by setup/activate.
    await tester.tap(find.byKey(const ValueKey('enroll_back')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('login_password')), findsOneWidget);
    expect(find.textContaining('keep-me-once'), findsNothing);
  });

  testWidgets(
    'wrong activation code permits retry with SAME activation proof',
    (tester) async {
      var calls = 0;
      final (adapter, _) = await mount(tester, (o) async {
        if (o.path == '/auth/login') return _challenge;
        if (o.path == '/auth/mfa/setup') return _setup;
        if (o.path == '/auth/mfa/activate') {
          calls++;
          return calls == 1
              ? const FakeReply(400, {'detail': 'bad code'})
              : const FakeReply(200, {
                  'mfa_enabled': true,
                  'recovery_codes': ['last-once'],
                });
        }
        return const FakeReply(404);
      });
      await _submit(tester);
      await tester.tap(find.byKey(const ValueKey('enroll_start')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const ValueKey('enroll_code')),
        '123456',
      );
      await tester.tap(find.byKey(const ValueKey('enroll_activate')));
      await tester.pumpAndSettle();
      expect(find.textContaining('رمز غير صحيح'), findsOneWidget);
      expect(find.byKey(const ValueKey('enroll_code')), findsOneWidget);
      await tester.enterText(
        find.byKey(const ValueKey('enroll_code')),
        '654321',
      );
      await tester.tap(find.byKey(const ValueKey('enroll_activate')));
      await tester.pumpAndSettle();
      expect(adapter.to('/auth/mfa/activate'), hasLength(2));
      expect(
        adapter.to('/auth/mfa/activate').first.headers['Authorization'],
        adapter.to('/auth/mfa/activate').last.headers['Authorization'],
      );
      expect(find.textContaining('last-once'), findsWidgets);
    },
  );

  testWidgets(
    'expired proof returns to password login, not retrying setup automatically',
    (tester) async {
      final (adapter, _) = await mount(tester, (o) async {
        if (o.path == '/auth/login') return _challenge;
        if (o.path == '/auth/mfa/setup') {
          return const FakeReply(401, {'detail': 'expired'});
        }
        return const FakeReply(404);
      });
      await _submit(tester);
      await tester.tap(find.byKey(const ValueKey('enroll_start')));
      await tester.pumpAndSettle();
      expect(find.textContaining('ابدأ الدخول من جديد'), findsWidgets);
      expect(find.byKey(const ValueKey('enroll_secret')), findsNothing);
      expect(adapter.to('/auth/mfa/setup'), hasLength(1));
      await tester.tap(find.byKey(const ValueKey('enroll_back')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('login_password')), findsOneWidget);
    },
  );
}
