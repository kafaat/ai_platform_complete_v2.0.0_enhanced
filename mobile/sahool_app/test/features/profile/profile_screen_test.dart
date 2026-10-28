// الحساب والإعدادات: إطار صفحة بزرّ رجوع حين تُفتح من «المزيد» (كانت بلا
// Scaffold)، هويّة من الخادم مع بقاء بيانات الجلسة عند الفشل، وضع السمة، رابط
// تفضيلات الإشعار، الإصدار، والخروج بتأكيد.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/core/theme/theme_controller.dart';
import 'package:sahool_app/features/profile/data/profile_api.dart';
import 'package:sahool_app/features/profile/presentation/profile_screen.dart';

import '../../core/fake_http.dart';

const _session = {
  'user_id': 'u1',
  'full_name': 'أحمد',
  'role': 'manager',
  'tenant_id': 'tenant-1',
};

void main() {
  late ThemeController theme;
  setUp(() => theme = ThemeController());

  Widget screen({
    required FakeHandler me,
    Future<void> Function()? logout,
    AppRouter? router,
  }) => ProfileScreen(
    api: ProfileApi(testClient(FakeAdapter(me), MemoryTokenStore())),
    session: _session,
    themeController: theme,
    versionLoader: () async => '2.0.0 (42)',
    logout: logout ?? () async {},
    router: router ?? AppRouter(features: const []),
  );

  Widget app(Widget home) => MaterialApp(
    theme: AppTheme.light,
    locale: const Locale('ar'),
    supportedLocales: const [Locale('ar')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    home: home,
  );

  testWidgets('مدفوعة من «المزيد» ⇒ شريط علويّ وزرّ رجوع', (tester) async {
    await tester.pumpWidget(
      app(
        Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => screen(
                    me: (_) async => const FakeReply(200, {
                      'user_id': 'u1',
                      'tenant_id': 'tenant-1',
                      'role': 'manager',
                      'name_ar': 'أحمد',
                    }),
                  ),
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(AppBar, 'الحساب والإعدادات'), findsOneWidget);
    expect(find.byType(BackButton), findsOneWidget);
    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();
    expect(find.text('open'), findsOneWidget);
  });

  testWidgets('الاسم من /api/v1/me يحلّ محلّ اسم الجلسة', (tester) async {
    await tester.pumpWidget(
      app(
        screen(
          me: (_) async => const FakeReply(200, {
            'user_id': 'u1',
            'tenant_id': 'tenant-1',
            'role': 'owner',
            'name_ar': 'أحمد اليمني',
          }),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('أحمد اليمني'), findsOneWidget);
    expect(find.text('مالك'), findsWidgets);
    expect(find.byKey(const ValueKey('profile_refresh_error')), findsNothing);
  });

  testWidgets('فشل /me ⇒ بيانات الجلسة مع سبب الفشل', (tester) async {
    await tester.pumpWidget(app(screen(me: (_) async => const FakeReply(503))));
    await tester.pumpAndSettle();
    expect(find.text('أحمد'), findsOneWidget);
    expect(find.byKey(const ValueKey('profile_refresh_error')), findsOneWidget);
    expect(find.textContaining('غير متاحة حاليّاً'), findsOneWidget);
  });

  testWidgets('وضع السمة يُضبط عبر ThemeController', (tester) async {
    await tester.pumpWidget(
      app(screen(me: (_) async => const FakeReply(200, {}))),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('profile_theme')),
      200,
    );
    await tester.tap(find.text('داكن'));
    await tester.pumpAndSettle();
    expect(theme.value, ThemeMode.dark);
    await tester.tap(find.text('فاتح'));
    await tester.pumpAndSettle();
    expect(theme.value, ThemeMode.light);
    await tester.tap(find.text('حسب الجهاز'));
    await tester.pumpAndSettle();
    expect(theme.value, ThemeMode.system);
  });

  testWidgets('تفضيلات الإشعار: معطّلة بصدق حتى يُسجَّل مسارها', (
    tester,
  ) async {
    await tester.pumpWidget(
      app(screen(me: (_) async => const FakeReply(200, {}))),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('profile_notification_prefs')),
      200,
    );
    expect(find.text('غير متاحة بعد في هذا الإصدار.'), findsOneWidget);

    final router = AppRouter(
      features: [
        FeatureModule(
          id: 'alerts',
          routes: [
            AppRoute(
              path: kNotificationPreferencesPath,
              titleAr: 'تفضيلات',
              builder: (_, _) => const Text('prefs-page'),
            ),
          ],
        ),
      ],
      isAuthenticated: () => true,
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        locale: const Locale('ar'),
        supportedLocales: const [Locale('ar')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        onGenerateRoute: router.onGenerateRoute,
        home: screen(me: (_) async => const FakeReply(200, {}), router: router),
      ),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('profile_notification_prefs')),
      200,
    );
    await tester.tap(find.byKey(const ValueKey('profile_notification_prefs')));
    await tester.pumpAndSettle();
    expect(find.text('prefs-page'), findsOneWidget);
  });

  testWidgets('with the real router the preferences link is enabled', (
    tester,
  ) async {
    // المسار تسجّله ميزة التنبيهات فعلاً ⇒ الرابط فعّال في التطبيق الحقيقيّ.
    expect(AppRouter.instance.match(kNotificationPreferencesPath), isNotNull);
    expect(AppRouter.instance.ownerOf(kNotificationPreferencesPath), 'alerts');
    await tester.pumpWidget(
      app(
        screen(
          me: (_) async => const FakeReply(200, {}),
          router: AppRouter.instance,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('profile_notification_prefs')),
      200,
    );
    expect(find.text('القنوات وأنواع التنبيهات'), findsOneWidget);
    expect(find.text('غير متاحة بعد في هذا الإصدار.'), findsNothing);
  });

  testWidgets('الإصدار والخروج بتأكيد', (tester) async {
    var loggedOut = 0;
    await tester.pumpWidget(
      app(
        screen(
          me: (_) async => const FakeReply(200, {}),
          logout: () async => loggedOut++,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('profile_logout')),
      200,
    );
    expect(find.text('2.0.0 (42)'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('profile_logout')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('إلغاء'));
    await tester.pumpAndSettle();
    expect(loggedOut, 0);
    await tester.tap(find.byKey(const ValueKey('profile_logout')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('خروج'));
    await tester.pumpAndSettle();
    expect(loggedOut, 1);
  });
}
