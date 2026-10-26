// الغلاف: وجهات حسب الدور، تبويب افتتاحيّ للعامل، تبويبات كسولة، لا تصادم Hero
// بين أزرار عائمة في تبويبات متزامنة، والرجوع إلى التبويب الافتتاحيّ.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/routing/app_shell.dart';
import 'package:sahool_app/core/routing/shell_destinations.dart';
import 'package:sahool_app/core/routing/shell_scope.dart';
import 'package:sahool_app/core/theme/app_theme.dart';

final built = <String>[];

AppRoute tab(String path, {bool fab = false}) => AppRoute(
      path: path,
      titleAr: path,
      builder: (context, _) {
        built.add(path);
        return Scaffold(
          body: Column(children: [
            Text('tab:$path'),
            TextButton(
              onPressed: () => ShellScope.maybeOf(context)?.select('fields'),
              child: Text('go-fields-from:$path'),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pushNamed('/detail'),
              child: Text('push-from:$path'),
            ),
          ]),
          // FAB بلا heroTag عمداً (كما في شاشات الحقول والمستشار).
          floatingActionButton:
              fab ? FloatingActionButton(onPressed: () {}, child: const Icon(Icons.add)) : null,
        );
      },
    );

AppRouter testRouter(AppRole role) => AppRouter(role: () => role, features: [
      FeatureModule(id: 'x', routes: [
        tab('/dashboard'),
        tab('/fields', fab: true),
        tab('/tasks'),
        tab('/advisor', fab: true),
        tab('/more'),
        AppRoute(
            path: '/detail',
            titleAr: 'detail',
            builder: (_, __) => const Scaffold(body: Text('detail'))),
      ]),
    ]);

Future<void> pumpShell(WidgetTester t, AppRole role) async {
  built.clear();
  final router = testRouter(role);
  await t.pumpWidget(MaterialApp(
    theme: AppTheme.light,
    locale: const Locale('ar'),
    supportedLocales: const [Locale('ar')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    onGenerateRoute: router.onGenerateRoute,
    home: AppShell(
      router: router,
      role: role,
      zeroFieldsCheck: () async => false,
      connectivity: ConnectivityStatus(),
      onResume: () async {},
    ),
  ));
  await t.pumpAndSettle();
}

List<String> navLabels(WidgetTester t) => t
    .widgetList<NavigationDestination>(find.byType(NavigationDestination))
    .map((d) => d.label)
    .toList();

void main() {
  test('destinations per role: viewer has no Tasks, at most five everywhere', () {
    for (final role in AppRole.values) {
      final ids = destinationsFor(role).map((d) => d.id).toList();
      expect(ids.length, lessThanOrEqualTo(5));
      expect(ids.first, 'home');
      expect(ids.last, 'more');
      expect(ids.contains('tasks'), role != AppRole.viewer, reason: role.name);
    }
    expect(initialDestinationFor(AppRole.worker), 'tasks');
    expect(initialDestinationFor(AppRole.owner), 'home');
  });

  testWidgets('owner sees five Arabic tabs and starts on Home', (t) async {
    await pumpShell(t, AppRole.owner);
    expect(navLabels(t), ['الرئيسية', 'الحقول', 'المهام', 'المستشار', 'المزيد']);
    expect(find.text('tab:/dashboard'), findsOneWidget);
  });

  testWidgets('viewer has no Tasks tab', (t) async {
    await pumpShell(t, AppRole.viewer);
    expect(navLabels(t), ['الرئيسية', 'الحقول', 'المستشار', 'المزيد']);
  });

  testWidgets('worker opens on Tasks', (t) async {
    await pumpShell(t, AppRole.worker);
    expect(find.text('tab:/tasks'), findsOneWidget);
    expect(built, ['/tasks']);
  });

  testWidgets('tabs are built lazily, once, on first visit', (t) async {
    await pumpShell(t, AppRole.owner);
    expect(built, ['/dashboard']);
    await t.tap(find.text('المستشار'));
    await t.pumpAndSettle();
    await t.tap(find.text('الرئيسية'));
    await t.pumpAndSettle();
    expect(built.where((p) => p == '/dashboard').length, 1);
    expect(built, contains('/advisor'));
    expect(built, isNot(contains('/fields')));
  });

  testWidgets('a tab can switch tabs through ShellScope', (t) async {
    await pumpShell(t, AppRole.owner);
    await t.tap(find.text('go-fields-from:/dashboard'));
    await t.pumpAndSettle();
    expect(find.text('tab:/fields'), findsOneWidget);
  });

  testWidgets('FABs without hero tags in two live tabs do not clash on push',
      (t) async {
    await pumpShell(t, AppRole.owner);
    await t.tap(find.text('الحقول'));
    await t.pumpAndSettle();
    await t.tap(find.text('المستشار'));
    await t.pumpAndSettle();
    await t.tap(find.text('push-from:/advisor'));
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
    expect(find.text('detail'), findsOneWidget);
  });

  testWidgets('back returns to the initial tab before leaving', (t) async {
    await pumpShell(t, AppRole.owner);
    await t.tap(find.text('المزيد'));
    await t.pumpAndSettle();
    final popped = await t.binding.handlePopRoute();
    await t.pumpAndSettle();
    expect(popped, isTrue);
    expect(find.text('tab:/dashboard'), findsOneWidget);
  });
}
