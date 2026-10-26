// الترحيب: ثلاث شاشات قصيرة كحدّ أقصى، والتخطّي متاح من الأولى.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/auth/presentation/onboarding_screen.dart';

import 'auth_test_app.dart';

void main() {
  testWidgets('ثلاث شاشات ثمّ «إنشاء أوّل حقل» يستدعي onStart', (tester) async {
    var started = 0;
    await tester.pumpWidget(
      authTestApp(OnboardingScreen(onStart: () => started++)),
    );
    expect(OnboardingScreen.pageCount, lessThanOrEqualTo(3));
    expect(find.text('أنشئ مزرعتك'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('onboarding_next')));
    await tester.pumpAndSettle();
    expect(find.text('ارسم حدود الحقل'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('onboarding_next')));
    await tester.pumpAndSettle();
    expect(find.text('إنشاء أوّل حقل'), findsOneWidget);
    expect(started, 0);
    await tester.tap(find.byKey(const ValueKey('onboarding_next')));
    await tester.pumpAndSettle();
    expect(started, 1);
  });

  testWidgets('التخطّي من الشاشة الأولى', (tester) async {
    var skipped = 0;
    var started = 0;
    await tester.pumpWidget(
      authTestApp(
        OnboardingScreen(onStart: () => started++, onSkip: () => skipped++),
      ),
    );
    await tester.tap(find.byKey(const ValueKey('onboarding_skip')));
    await tester.pump();
    expect(skipped, 1);
    expect(started, 0);
  });
}
