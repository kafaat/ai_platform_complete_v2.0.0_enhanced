// «المزيد»: مجمّعة بأقسام، مرشّحة بالدور، رأس حساب يفتح الإعدادات، وكلّ عنصر
// يفتح مساره.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/more/presentation/more_screen.dart';

AppRoute _r(
  String path,
  String title,
  MenuSection section, {
  Set<AppRole>? roles,
  int order = 10,
}) => AppRoute(
  path: path,
  titleAr: title,
  icon: Icons.circle,
  allowedRoles: roles,
  menu: MenuEntry(section, order: order),
  builder: (_, _) => Scaffold(body: Text('page:$path')),
);

final _router = AppRouter(
  features: [
    FeatureModule(
      id: 'x',
      routes: [
        _r('/account/profile', 'الحساب والإعدادات', MenuSection.account),
        _r('/farms', 'المزارع', MenuSection.farm),
        _r(
          '/master-data',
          'البيانات المرجعيّة',
          MenuSection.records,
          roles: RouteRoles.management,
        ),
        _r(
          '/documents',
          'الوثائق',
          MenuSection.records,
          roles: RouteRoles.management,
          order: 20,
        ),
      ],
    ),
  ],
);

Widget _app(AppRole role) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  onGenerateRoute: _router.onGenerateRoute,
  home: MoreScreen(
    router: _router,
    role: role,
    profile: const {'full_name': 'سالم'},
  ),
);

void main() {
  testWidgets('المالك يرى قسم السجلّات بترتيبه', (tester) async {
    await tester.pumpWidget(_app(AppRole.owner));
    expect(find.byKey(const ValueKey('more-section:records')), findsOneWidget);
    final md = tester.getTopLeft(find.text('البيانات المرجعيّة'));
    final docs = tester.getTopLeft(find.text('الوثائق'));
    expect(md.dy, lessThan(docs.dy));
    expect(find.text('مالك'), findsOneWidget);
  });

  testWidgets('المشاهد لا يرى عناصر الإدارة ولا قسمها', (tester) async {
    await tester.pumpWidget(_app(AppRole.viewer));
    expect(find.text('الوثائق'), findsNothing);
    expect(find.byKey(const ValueKey('more-section:records')), findsNothing);
    expect(find.text('المزارع'), findsOneWidget);
  });

  testWidgets('رأس الحساب يفتح الإعدادات والعنصر يفتح مساره', (tester) async {
    await tester.pumpWidget(_app(AppRole.worker));
    await tester.tap(find.byKey(const ValueKey('more:account-header')));
    await tester.pumpAndSettle();
    expect(find.text('page:/account/profile'), findsOneWidget);
    Navigator.of(tester.element(find.text('page:/account/profile'))).pop();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('more:/farms')));
    await tester.pumpAndSettle();
    expect(find.text('page:/farms'), findsOneWidget);
  });

  testWidgets('لا عناصر للدور ⇒ حالة فارغة صادقة', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: MoreScreen(
          router: AppRouter(features: const []),
          role: AppRole.viewer,
        ),
      ),
    );
    expect(find.text('لا وحدات إضافيّة متاحة لدورك.'), findsOneWidget);
  });
}
