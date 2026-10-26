// شاشة الدخول: رسائل فشل صادقة لكلّ نوع (بيانات خاطئة/مهلة/انقطاع/خادم معطّل)،
// رمز MFA بأرقام عربيّة-هنديّة يُرسَل أرقاماً غربيّة، وإظهار كلمة المرور.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/auth/data/auth_api.dart';
import 'package:sahool_app/features/auth/presentation/login_screen.dart';

import '../../core/fake_http.dart';
import 'auth_test_app.dart';

Future<void> _fillAndSubmit(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const ValueKey('login_email')),
    'farmer@example.com',
  );
  await tester.enterText(
    find.byKey(const ValueKey('login_password')),
    'secret-pass',
  );
  await tester.tap(find.byKey(const ValueKey('login_submit')));
  await tester.pumpAndSettle();
}

void main() {
  Future<FakeAdapter> pumpWith(WidgetTester tester, FakeHandler handler) async {
    final adapter = FakeAdapter(handler);
    final api = AuthApi(testClient(adapter, MemoryTokenStore()));
    await tester.pumpWidget(authTestApp(LoginScreen(api: api)));
    return adapter;
  }

  testWidgets('401 ⇒ «البريد أو كلمة المرور غير صحيحة»', (tester) async {
    await pumpWith(
      tester,
      (_) async => const FakeReply(401, {'detail': 'Invalid credentials'}),
    );
    await _fillAndSubmit(tester);
    expect(
      find.text('البريد الإلكترونيّ أو كلمة المرور غير صحيحة.'),
      findsOneWidget,
    );
  });

  testWidgets('مهلة ⇒ رسالة مهلة، لا «بيانات غير صحيحة»', (tester) async {
    await pumpWith(
      tester,
      (_) async => const FakeReply.fail(DioExceptionType.receiveTimeout),
    );
    await _fillAndSubmit(tester);
    expect(find.textContaining('انتهت مهلة الاتصال'), findsOneWidget);
    expect(find.byIcon(Icons.wifi_off_rounded), findsOneWidget);
    expect(find.textContaining('غير صحيحة'), findsNothing);
  });

  testWidgets('انقطاع الشبكة ⇒ رسالة اتصال', (tester) async {
    await pumpWith(
      tester,
      (_) async => const FakeReply.fail(DioExceptionType.connectionError),
    );
    await _fillAndSubmit(tester);
    expect(find.textContaining('لا يوجد اتصال بالخادم'), findsOneWidget);
  });

  testWidgets('503 ⇒ الخدمة غير متاحة', (tester) async {
    await pumpWith(tester, (_) async => const FakeReply(503));
    await _fillAndSubmit(tester);
    expect(find.textContaining('غير متاحة حاليّاً'), findsOneWidget);
  });

  testWidgets('بريد ناقص لا يُرسَل', (tester) async {
    final adapter = await pumpWith(tester, (_) async => const FakeReply(200));
    await tester.enterText(find.byKey(const ValueKey('login_email')), 'farmer');
    await tester.enterText(find.byKey(const ValueKey('login_password')), 'x');
    await tester.tap(find.byKey(const ValueKey('login_submit')));
    await tester.pumpAndSettle();
    expect(adapter.requests, isEmpty);
    expect(find.textContaining('أدخل بريداً صحيحاً'), findsOneWidget);
  });

  testWidgets('إظهار/إخفاء كلمة المرور بزرّ له تلميح', (tester) async {
    await pumpWith(tester, (_) async => const FakeReply(200));
    EditableText field() => tester.widget<EditableText>(
      find.descendant(
        of: find.byKey(const ValueKey('login_password')),
        matching: find.byType(EditableText),
      ),
    );
    expect(field().obscureText, isTrue);
    expect(find.byTooltip('إظهار كلمة المرور'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('login_toggle_password')));
    await tester.pump();
    expect(field().obscureText, isFalse);
    expect(find.byTooltip('إخفاء كلمة المرور'), findsOneWidget);
  });

  testWidgets('MFA: رمز بأرقام عربيّة-هنديّة يُرسَل 123456', (tester) async {
    var call = 0;
    final adapter = await pumpWith(tester, (_) async {
      call++;
      if (call == 1) {
        return const FakeReply(
          401,
          {'detail': 'MFA required'},
          {
            'x-mfa-required': ['true'],
          },
        );
      }
      return const FakeReply(401, {'detail': 'رمز MFA غير صحيح'});
    });
    await _fillAndSubmit(tester);
    expect(find.byKey(const ValueKey('login_mfa_code')), findsOneWidget);
    await tester.enterText(
      find.byKey(const ValueKey('login_mfa_code')),
      '١٢٣٤٥٦',
    );
    await tester.tap(find.byKey(const ValueKey('login_submit')));
    await tester.pumpAndSettle();
    final body = adapter.requests.last.data! as Map;
    expect(body['mfa_code'], '123456');
    expect(find.textContaining('رمز التحقّق غير صحيح'), findsOneWidget);
    // الحقل يبقى ظاهراً لإعادة الإدخال.
    expect(find.byKey(const ValueKey('login_mfa_code')), findsOneWidget);
  });
}
