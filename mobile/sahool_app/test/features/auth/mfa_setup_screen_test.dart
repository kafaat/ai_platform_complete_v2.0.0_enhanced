// تفعيل المصادقة الثنائيّة: كان FilteringTextInputFormatter.digitsOnly يحذف ٠-٩
// العربيّة فلا يُكتب الرمز من لوحة عربيّة. والتعطيل يُؤكَّد صراحةً.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/auth/data/auth_api.dart';
import 'package:sahool_app/features/auth/presentation/mfa_setup_screen.dart';
import 'package:sahool_app/features/auth/presentation/widgets/otp_code_field.dart';

import '../../core/fake_http.dart';
import 'auth_test_app.dart';

void _tallScreen(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

void main() {
  test('normalizeOtp يقبل الأرقام العربيّة-الهنديّة والفارسيّة', () {
    expect(normalizeOtp('١٢٣٤٥٦'), '123456');
    expect(normalizeOtp('۱۲۳ ۴۵۶'), '123456');
    expect(normalizeOtp('12345'), isNull);
  });

  testWidgets('تفعيل برمز عربيّ-هنديّ يرسل الأرقام الغربيّة', (tester) async {
    final adapter = FakeAdapter((o) async {
      if (o.path == '/auth/mfa/setup') {
        return const FakeReply(200, {
          'secret': 'JBSWY3DPEHPK3PXP',
          'provisioning_uri': 'otpauth://totp/SAHOOL:f?secret=JBSWY3DPEHPK3PXP',
        });
      }
      return const FakeReply(200, {'mfa_enabled': true});
    });
    final api = AuthApi(testClient(adapter, MemoryTokenStore()));
    _tallScreen(tester);
    await tester.pumpWidget(authTestApp(MfaSetupScreen(api: api)));
    await tester.tap(find.byKey(const ValueKey('mfa_start')));
    await tester.pumpAndSettle();
    expect(find.text('JBSWY3DPEHPK3PXP'), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey('mfa_activate_code')),
      '٦٥٤٣٢١',
    );
    // الحقل نفسه يحمل الأرقام بعد التحويل (لم تُحذف).
    final field = tester.widget<TextField>(
      find.descendant(
        of: find.byKey(const ValueKey('mfa_activate_code')),
        matching: find.byType(TextField),
      ),
    );
    expect(field.controller!.text, '654321');
    await tester.tap(find.byKey(const ValueKey('mfa_activate')));
    await tester.pumpAndSettle();
    final activate = adapter.to('/auth/mfa/activate').single;
    expect((activate.data! as Map)['code'], '654321');
    expect(find.byKey(const ValueKey('mfa_activated')), findsOneWidget);
    expect(find.text('JBSWY3DPEHPK3PXP'), findsNothing);
  });

  testWidgets('رمز خاطئ ⇒ تفصيل الخادم سطريّاً', (tester) async {
    final adapter = FakeAdapter((o) async {
      if (o.path == '/auth/mfa/setup') {
        return const FakeReply(200, {
          'secret': 'S',
          'provisioning_uri': 'otpauth://totp/x?secret=S',
        });
      }
      return const FakeReply(400, {'detail': 'رمز غير صحيح'});
    });
    final api = AuthApi(testClient(adapter, MemoryTokenStore()));
    _tallScreen(tester);
    await tester.pumpWidget(authTestApp(MfaSetupScreen(api: api)));
    await tester.tap(find.byKey(const ValueKey('mfa_start')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('mfa_activate_code')),
      '123456',
    );
    await tester.tap(find.byKey(const ValueKey('mfa_activate')));
    await tester.pumpAndSettle();
    expect(find.text('رمز غير صحيح'), findsOneWidget);
  });

  testWidgets('التعطيل يطلب تأكيداً ولا يُرسل عند الإلغاء', (tester) async {
    final adapter = FakeAdapter((_) async => const FakeReply(200, {}));
    final api = AuthApi(testClient(adapter, MemoryTokenStore()));
    _tallScreen(tester);
    await tester.pumpWidget(authTestApp(MfaSetupScreen(api: api)));
    await tester.tap(find.byKey(const ValueKey('mfa_show_disable')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('mfa_disable_code')),
      '١١١١١١',
    );
    await tester.tap(find.byKey(const ValueKey('mfa_disable')));
    await tester.pumpAndSettle();
    expect(find.text('تعطيل المصادقة الثنائيّة؟'), findsOneWidget);
    await tester.tap(find.text('إلغاء').last);
    await tester.pumpAndSettle();
    expect(adapter.requests, isEmpty);

    await tester.tap(find.byKey(const ValueKey('mfa_disable')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(
        of: find.byType(AlertDialog),
        matching: find.widgetWithText(FilledButton, 'تعطيل'),
      ),
    );
    await tester.pumpAndSettle();
    final req = adapter.to('/auth/mfa/disable').single;
    expect((req.data! as Map)['code'], '111111');
    expect(find.byKey(const ValueKey('mfa_disabled')), findsOneWidget);
  });
}
