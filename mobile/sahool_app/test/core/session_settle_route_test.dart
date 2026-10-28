// D2/UI-C3: المسار الخاصّ يحكم على الجلسة بعد حسمها لا قبله. رابط عميق يُولَّد
// أثناء استعادة الجلسة من القرص ينتظرها (كان يحكم على جلسة لم تُقرأ بعد فيعرض
// «سجّل الدخول» لجلسة قابلة للاستئناف). حالة التجديد الجاري في
// session_refresh_route_test.dart.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/routing/route_pages.dart';
import 'package:sahool_app/services/auth_service.dart';

import 'fake_http.dart';

AppRoute page(String path) => AppRoute(
      path: path,
      titleAr: path,
      icon: Icons.circle,
      builder: (_, _) => Text('page:$path'),
    );

Future<void> pumpFrames(WidgetTester t) async {
  for (var i = 0; i < 10; i++) {
    await t.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  group('deep link during restore (default AuthService check)', () {
    tearDown(() => AuthService.instance.clearAuth());

    Future<void> pushDuringRestore(WidgetTester t) async {
      final router = AppRouter(
        features: [FeatureModule(id: 's', routes: [page('/seasons')])],
        role: () => AppRole.viewer,
      );
      await t.pumpWidget(MaterialApp(
        onGenerateRoute: router.onGenerateRoute,
        home: const Text('root'),
      ));
      final nav = t.state<NavigatorState>(find.byType(Navigator));
      // الاستعادة بدأت ولم تنتهِ لحظة توليد المسار (ترتيب الإقلاع الحقيقيّ).
      final restoring = AuthService.instance.loadSaved();
      unawaited(nav.pushNamed('/seasons'));
      await t.pump();
      await t.runAsync(() => restoring);
      await pumpFrames(t);
    }

    testWidgets('a resumable session (expired access + refresh) opens the page',
        (t) async {
      FlutterSecureStorage.setMockInitialValues({
        'access_token': fakeJwt(const Duration(minutes: -5)),
        'refresh_token': 'r-1',
      });
      await pushDuringRestore(t);
      expect(find.byType(SignInRequiredPage), findsNothing);
      expect(find.text('page:/seasons'), findsOneWidget);
    });

    testWidgets('no saved session still fails closed after restore', (t) async {
      FlutterSecureStorage.setMockInitialValues({});
      await pushDuringRestore(t);
      expect(find.byType(SignInRequiredPage), findsOneWidget);
      expect(find.text('page:/seasons'), findsNothing);
    });
  });
}
