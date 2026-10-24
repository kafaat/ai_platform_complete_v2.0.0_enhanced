import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/realtime/realtime_screen.dart';

void main() {
  testWidgets('call entry is disabled in a default build without touching auth or media', (tester) async {
    expect(realtimeCallsEnabled, isFalse);
    expect(nativeRealtimeCallsEnabled, isFalse);
    await tester.pumpWidget(const MaterialApp(home: RealtimeScreen(fieldId: 'field-1')));
    expect(find.text('المكالمات غير مفعّلة أو تتطلب تسجيل الدخول.'), findsOneWidget);
    expect(find.text('السماح للميكروفون والتحدث'), findsNothing);
  });
}
