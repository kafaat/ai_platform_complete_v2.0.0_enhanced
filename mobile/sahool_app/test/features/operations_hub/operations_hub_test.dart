// مركز العمليّات: مبنيّ من مداخل القوائم، مجمّع بالأقسام (العمليّات أوّلاً)، مُرشَّح
// بالدور، يحمل سهم رجوع حين يُدفَع، ولا يفيض بخطّ كبير.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/operations_hub/operations_hub_routes.dart';
import 'package:sahool_app/features/operations_hub/presentation/operations_hub_screen.dart';

AppRoute page(
  String path,
  MenuSection section,
  int order, {
  Set<AppRole>? roles,
}) => AppRoute(
  path: path,
  titleAr: 'وجهة $path',
  icon: Icons.circle_outlined,
  allowedRoles: roles,
  menu: MenuEntry(section, order: order),
  builder: (_, _) => Scaffold(body: Text('page:$path')),
);

AppRouter fakeRouter(AppRole role) => AppRouter(
  role: () => role,
  features: [
    operationsHubFeature,
    FeatureModule(
      id: 'a',
      routes: [
        page('/ops-b', MenuSection.operations, 20),
        page('/ops-a', MenuSection.operations, 10),
        page('/farm-x', MenuSection.farm, 10),
        page(
          '/records-x',
          MenuSection.records,
          10,
          roles: RouteRoles.management,
        ),
        page('/account-x', MenuSection.account, 10),
      ],
    ),
  ],
);

Widget app(
  AppRouter router,
  AppRole role, {
  bool pushed = false,
  double textScale = 1,
}) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  builder: (c, child) => MediaQuery(
    data: MediaQuery.of(c).copyWith(textScaler: TextScaler.linear(textScale)),
    child: child!,
  ),
  onGenerateRoute: (s) => s.name == OperationsHubRoutes.hub
      ? MaterialPageRoute<void>(
          settings: s,
          builder: (_) => OperationsHubScreen(router: router, role: role),
        )
      : router.onGenerateRoute(s),
  home: pushed
      ? Builder(
          builder: (c) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () =>
                    Navigator.of(c).pushNamed(OperationsHubRoutes.hub),
                child: const Text('افتح المركز'),
              ),
            ),
          ),
        )
      : OperationsHubScreen(router: router, role: role),
);

void main() {
  test('groups: operations first, ordered, hub and account excluded', () {
    final groups = hubGroupsFor(fakeRouter(AppRole.owner), AppRole.owner);
    expect(groups.map((g) => g.key).toList(), [
      MenuSection.operations,
      MenuSection.farm,
      MenuSection.records,
    ]);
    expect(groups.first.value.map((r) => r.path), ['/ops-a', '/ops-b']);
    final all = groups.expand((g) => g.value).map((r) => r.path);
    expect(all, isNot(contains(OperationsHubRoutes.hub)));
    expect(all, isNot(contains('/account-x')));
  });

  test('role-aware: management-only destinations hidden from a worker', () {
    final worker = hubGroupsFor(
      fakeRouter(AppRole.worker),
      AppRole.worker,
    ).expand((g) => g.value).map((r) => r.path);
    expect(worker, isNot(contains('/records-x')));
    expect(worker, contains('/ops-a'));
  });

  test('the real app lists inventory, equipment and devices in the hub', () {
    final paths = hubGroupsFor(
      AppRouter.instance,
      AppRole.owner,
    ).first.value.map((r) => r.path);
    expect(paths, containsAll(['/inventory', '/equipment', '/devices']));
  });

  testWidgets('section headers and icon tiles render', (t) async {
    await t.pumpWidget(app(fakeRouter(AppRole.owner), AppRole.owner));
    expect(find.text(MenuSection.operations.labelAr), findsOneWidget);
    expect(find.text(MenuSection.farm.labelAr), findsOneWidget);
    expect(find.text('وجهة /ops-a'), findsOneWidget);
    expect(find.byIcon(Icons.circle_outlined), findsWidgets);
  });

  testWidgets('pushed from More, the hub has a back arrow that works', (
    t,
  ) async {
    await t.pumpWidget(
      app(fakeRouter(AppRole.owner), AppRole.owner, pushed: true),
    );
    await t.tap(find.text('افتح المركز'));
    await t.pumpAndSettle();
    expect(find.byType(OperationsHubScreen), findsOneWidget);
    expect(find.byType(BackButton), findsOneWidget);
    await t.tap(find.byType(BackButton));
    await t.pumpAndSettle();
    expect(find.byType(OperationsHubScreen), findsNothing);
    expect(find.text('افتح المركز'), findsOneWidget);
  });

  testWidgets('tapping a tile opens its route', (t) async {
    await t.pumpWidget(app(fakeRouter(AppRole.owner), AppRole.owner));
    await t.tap(find.text('وجهة /farm-x'));
    await t.pumpAndSettle();
    expect(find.text('page:/farm-x'), findsOneWidget);
  });

  testWidgets('no destinations for a role ⇒ honest empty state', (t) async {
    final router = AppRouter(
      role: () => AppRole.viewer,
      features: [operationsHubFeature],
    );
    await t.pumpWidget(app(router, AppRole.viewer));
    expect(find.text('لا وحدات تشغيليّة متاحة لدورك.'), findsOneWidget);
  });

  for (final scale in [1.3, 2.0]) {
    testWidgets('no overflow at 360dp and text scale $scale', (t) async {
      t.view.physicalSize = const Size(360, 780);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.reset);
      await t.pumpWidget(
        app(AppRouter.instance, AppRole.owner, textScale: scale),
      );
      await t.pump();
      expect(t.takeException(), isNull);
    });
  }
}
