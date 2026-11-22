// بديل ErrorWidget يُبنى أحياناً بلا سلف Material (خطأ في initState فوق Scaffold).
// بدون Material يرث Text زخرفة الخطأ الافتراضيّة (خطّ أصفر مزدوج) — اكتُشف في محاكاة المختبر.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/widgets/app_error_widget.dart';

void main() {
  testWidgets('AppErrorWidget text carries no inherited error decoration',
      (t) async {
    // WidgetsApp لا يوفّر Material ولا DefaultTextStyle من السمة: أسوأ موضع.
    await t.pumpWidget(WidgetsApp(
      color: const Color(0xFFFFFFFF),
      builder: (context, child) => AppErrorWidget(
        details: FlutterErrorDetails(exception: StateError('boom')),
        message: 'رسالة آمنة',
      ),
    ));
    final text = t.widget<Text>(find.byType(Text));
    final style = DefaultTextStyle.of(t.element(find.byType(Text))).style
        .merge(text.style);
    expect(style.decoration, isNot(TextDecoration.underline),
        reason: 'the error fallback must not render the yellow debug underline');
    expect(find.ancestor(of: find.byType(Text), matching: find.byType(Material)),
        findsOneWidget);
  });
}
