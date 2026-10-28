// المُشاهِد لا يرى دفتر المزرعة: لا في «المزيد» ولا عبر الرابط العميق.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/routing/route_pages.dart';
import 'package:sahool_app/features/farm_book/farm_book_routes.dart';
import 'package:sahool_app/features/farm_book/presentation/farm_book_screen.dart';
import 'package:sahool_app/features/more/presentation/more_screen.dart';

void main() {
  final router = AppRouter(features: allFeatures, role: () => AppRole.owner);

  test('the farm book is in «المزيد» for every role except viewer', () {
    for (final role in AppRole.values) {
      final paths = moreRoutesFor(router, role).map((r) => r.path);
      if (role == AppRole.viewer) {
        expect(paths, isNot(contains(FarmBookRoutes.book)));
      } else {
        expect(paths, contains(FarmBookRoutes.book), reason: role.name);
      }
    }
  });

  testWidgets('a viewer deep-linking to /farm-book gets access denied', (
    t,
  ) async {
    final viewerRouter = AppRouter(
      features: [farmBookFeature],
      role: () => AppRole.viewer,
      isAuthenticated: () => true,
    );
    await t.pumpWidget(
      MaterialApp(
        onGenerateRoute: viewerRouter.onGenerateRoute,
        initialRoute: FarmBookRoutes.book,
      ),
    );
    await t.pumpAndSettle();
    expect(find.byType(AccessDeniedPage), findsOneWidget);
    expect(find.byType(FarmBookScreen), findsNothing);
  });

  test('the legacy name farm_book resolves to the canonical route', () {
    expect(router.match('farm_book')?.path, FarmBookRoutes.book);
    expect(router.ownerOf(FarmBookRoutes.book), 'farm_book');
  });
}
