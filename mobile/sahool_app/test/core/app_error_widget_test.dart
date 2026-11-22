// بديل ErrorWidget قد يُبنى تحت MaterialApp خارج أيّ Scaffold/Material (خطأ في
// initState لـAuthGate). هناك يمرّر MaterialApp نمط الخطأ الافتراضيّ (خطّ أصفر
// مزدوج) حتى في الإصدار، فيرثه Text ما لم يوجد Material. اكتُشف في محاكاة المختبر.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/widgets/app_error_widget.dart';

TextStyle _rendered(WidgetTester t) => t
    .widget<RichText>(
        find.descendant(of: find.byType(Text), matching: find.byType(RichText)))
    .text
    .style!;

void main() {
  testWidgets('harness reproduces the fallback underline outside a Material',
      (t) async {
    await t.pumpWidget(
        const MaterialApp(home: Text('x', textDirection: TextDirection.rtl)));
    final s = _rendered(t);
    expect(s.decoration, TextDecoration.underline);
    expect(s.decorationStyle, TextDecorationStyle.double);
  });

  testWidgets(
      'AppErrorWidget under MaterialApp, outside Scaffold, has no fallback underline',
      (t) async {
    await t.pumpWidget(MaterialApp(
      home: AppErrorWidget(
        details: FlutterErrorDetails(exception: StateError('boom')),
        message: 'رسالة آمنة',
      ),
    ));
    final s = _rendered(t);
    // ليس isNull: نمط السمة يحمل TextDecoration.none.
    expect(s.decoration, isNot(TextDecoration.underline));
    expect(s.decorationStyle, isNot(TextDecorationStyle.double));
    expect(s.color, const Color(0xFFC0392B));
    expect(
        find.ancestor(of: find.byType(Text), matching: find.byType(Material)),
        findsWidgets);
  });
}
