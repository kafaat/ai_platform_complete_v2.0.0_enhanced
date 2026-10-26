// جذر التطبيق الحقيقيّ (SAHOOLApp): مندوبات اللغة موجودة فيعمل TextField وزرّ
// الرجوع (كان كلّ TextField يرمي «No MaterialLocalizations found»)، والاتّجاه RTL.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/main.dart';

void main() {
  testWidgets('real app root renders a TextField, RTL, with Material localizations',
      (t) async {
    await t.pumpWidget(const SAHOOLApp(
      home: Scaffold(body: TextField(key: ValueKey('probe'))),
    ));
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
    final ctx = t.element(find.byKey(const ValueKey('probe')));
    expect(Directionality.of(ctx), TextDirection.rtl);
    expect(MaterialLocalizations.of(ctx), isNotNull);
    await t.enterText(find.byKey(const ValueKey('probe')), 'حقل');
    expect(find.text('حقل'), findsOneWidget);
  });

  testWidgets('unknown deep link shows a page, not a crash', (t) async {
    await t.pumpWidget(const SAHOOLApp(home: Scaffold(body: Text('root'))));
    await t.pumpAndSettle();
    final nav = t.state<NavigatorState>(find.byType(Navigator).first);
    nav.pushNamed('/does-not-exist');
    await t.pumpAndSettle();
    expect(find.text('الصفحة غير موجودة'), findsOneWidget);
  });
}
