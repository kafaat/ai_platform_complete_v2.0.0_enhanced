// الموجِّه: تجميع مسارات كلّ الميزات، تفرّد المسارات، الروابط العميقة، الأدوار،
// وقائمة «المزيد» المبنيّة من ملفّات المسارات.
import 'dart:async';

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/routing/route_pages.dart';
import 'package:sahool_app/core/routing/shell_destinations.dart';
import 'package:sahool_app/core/session/session_scope.dart';
import 'package:sahool_app/features/more/presentation/more_screen.dart';

AppRoute page(String path, {Set<AppRole>? roles, MenuEntry? menu}) => AppRoute(
      path: path,
      titleAr: path,
      icon: Icons.circle,
      allowedRoles: roles,
      menu: menu,
      builder: (_, args) => Text('page:$path:${args['field_id'] ?? ''}'),
    );

void main() {
  group('aggregation of the real feature modules', () {
    final router = AppRouter(features: allFeatures, role: () => AppRole.owner);

    test('every feature folder exports exactly one module that is registered',
        () {
      final folders = Directory('lib/features')
          .listSync()
          .whereType<Directory>()
          .map((d) => d.uri.pathSegments.where((s) => s.isNotEmpty).last)
          .toSet();
      final registered = allFeatures.map((f) => f.id).toSet();
      expect(registered, folders,
          reason: 'كلّ مجلّد ميزة له <x>_routes.dart مسجَّل في allFeatures');
      for (final id in folders) {
        expect(File('lib/features/$id/${id}_routes.dart').existsSync(), isTrue,
            reason: 'features/$id/${id}_routes.dart');
      }
      expect(allFeatures.length, registered.length, reason: 'لا معرّف مكرّر');
    });

    test('every feature has its own data/<x>_api.dart (realtime keeps its own)',
        () {
      for (final f in allFeatures) {
        final dataApi = File('lib/features/${f.id}/data/${f.id}_api.dart');
        final flatApi = File('lib/features/${f.id}/${f.id}_api.dart');
        expect(dataApi.existsSync() || flatApi.existsSync(), isTrue,
            reason: '${f.id} needs its own API file');
      }
    });

    test('shell destinations point at real routes', () {
      for (final d in kShellDestinations) {
        expect(router.match(d.routePath), isNotNull, reason: d.routePath);
      }
    });

    test('legacy name field_workspace still resolves, owned by fields', () {
      expect(router.match('field_workspace')?.path, '/fields/workspace');
      expect(router.ownerOf('field_workspace'), 'fields');
    });

    test('feature cleanups register with the session scope', () {
      final scope = SessionScope();
      router.registerSessionCleanups(scope);
      expect(scope.owners, containsAll(['advisor', 'field_forms']));
    });
  });

  test('duplicate paths across features fail fast', () {
    expect(
      () => AppRouter(features: [
        FeatureModule(id: 'a', routes: [page('/x')]),
        FeatureModule(id: 'b', routes: [page('/x/')]),
      ]),
      throwsStateError,
    );
  });

  testWidgets('deep link query parameters reach the builder', (t) async {
    final router = AppRouter(
      features: [FeatureModule(id: 'f', routes: [page('/fields/workspace')])],
      role: () => AppRole.viewer,
    );
    await t.pumpWidget(MaterialApp(
      onGenerateRoute: router.onGenerateRoute,
      onUnknownRoute: router.onUnknownRoute,
      initialRoute: '/fields/workspace?field_id=f-42',
    ));
    await t.pumpAndSettle();
    expect(find.text('page:/fields/workspace:f-42'), findsOneWidget);
  });

  testWidgets('a role outside allowedRoles gets an honest access-denied page',
      (t) async {
    final router = AppRouter(
      features: [
        FeatureModule(id: 'm', routes: [
          page('/master-data', roles: RouteRoles.management),
        ]),
      ],
      role: () => AppRole.worker,
    );
    await t.pumpWidget(MaterialApp(
      onGenerateRoute: router.onGenerateRoute,
      initialRoute: '/master-data',
    ));
    await t.pumpAndSettle();
    expect(find.byType(AccessDeniedPage), findsOneWidget);
    expect(find.textContaining('page:'), findsNothing);
  });

  testWidgets('unknown routes show a not-found page, not a blank screen',
      (t) async {
    final router = AppRouter(features: const [], role: () => AppRole.owner);
    await t.pumpWidget(MaterialApp(
      onGenerateRoute: router.onGenerateRoute,
      onUnknownRoute: router.onUnknownRoute,
      home: const Text('root'),
    ));
    unawaited(t.state<NavigatorState>(find.byType(Navigator)).pushNamed('/nope'));
    await t.pumpAndSettle();
    expect(find.byType(RouteNotFoundPage), findsOneWidget);
  });

  group('More menu is built from route files and filtered by role', () {
    final router = AppRouter(features: allFeatures, role: () => AppRole.owner);

    test('management-only screens are hidden from worker and viewer', () {
      final owner = moreRoutesFor(router, AppRole.owner).map((r) => r.path);
      final worker = moreRoutesFor(router, AppRole.worker).map((r) => r.path);
      final viewer = moreRoutesFor(router, AppRole.viewer).map((r) => r.path);
      expect(owner, containsAll(['/master-data', '/documents']));
      for (final paths in [worker, viewer]) {
        expect(paths, isNot(contains('/master-data')));
        expect(paths, isNot(contains('/documents')));
      }
      // ما كان في «المزيد» قبل إعادة الهيكلة يبقى قابلاً للوصول.
      expect(owner, containsAll([
        '/operations', '/tasks', '/farms', '/satellite', '/inventory',
        '/equipment', '/devices', '/account/profile', '/account/mfa',
        '/irrigation/ops',
      ]));
    });

    test('sections are ordered and items sorted by MenuEntry.order', () {
      final menu = router.menuFor(AppRole.owner);
      final sections = menu.keys.toList();
      final indices = sections.map((s) => s.index).toList();
      expect(indices, [...indices]..sort());
      final ops = menu[MenuSection.operations]!.map((r) => r.path).toList();
      expect(ops.first, '/operations');
      expect(ops[1], '/tasks');
    });
  });
}
