// D2/UI-C3: المسار الخاصّ يحكم على الجلسة بعد حسمها لا قبله.
//   • رابط عميق يُولَّد أثناء استعادة الجلسة من القرص ينتظرها (كان يحكم على جلسة
//     لم تُقرأ بعد فيعرض «سجّل الدخول» لجلسة قابلة للاستئناف).
//   • أثناء تجديد جارٍ: فشل الشبكة «غير معروف» فتُفتح الصفحة؛ رفض الخادم الصريح
//     يمسح الجلسة فتُطلب إعادة الدخول.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
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

  group('deep link during a refresh', () {
    Future<void> pushDuringRefresh(WidgetTester t, FakeReply verdict) async {
      final tokens = MemoryTokenStore(
          accessToken: fakeJwt(const Duration(minutes: -5)),
          refreshToken: 'r-1',
          owner: 'A');
      final gate = Completer<FakeReply>();
      final client = ApiClient(
        baseUrl: 'https://api.test.invalid',
        tokens: tokens,
        adapter: FakeAdapter((o) => gate.future),
        retryBaseDelay: const Duration(milliseconds: 1),
        retryJitterMs: 0,
      );
      final router = AppRouter(
        features: [FeatureModule(id: 's', routes: [page('/seasons')])],
        role: () => AppRole.viewer,
        isAuthenticated: () => tokens.refreshToken != null,
        sessionPending: () => client.pendingRefresh,
      );
      await t.pumpWidget(MaterialApp(
        onGenerateRoute: router.onGenerateRoute,
        home: const Text('root'),
      ));
      unawaited(client.refreshAccessToken());
      unawaited(
          t.state<NavigatorState>(find.byType(Navigator)).pushNamed('/seasons'));
      await pumpFrames(t);
      // التجديد معلّق: لا حكم بعد.
      expect(find.byType(SessionPendingPage), findsOneWidget);
      expect(find.text('page:/seasons'), findsNothing);
      expect(find.byType(SignInRequiredPage), findsNothing);
      gate.complete(verdict);
      await pumpFrames(t);
    }

    testWidgets('a network failure is unknown: the page opens', (t) async {
      await pushDuringRefresh(
          t, const FakeReply.fail(DioExceptionType.connectionError));
      expect(find.text('page:/seasons'), findsOneWidget);
      expect(find.byType(SignInRequiredPage), findsNothing);
    });

    testWidgets('an explicit server rejection asks to sign in', (t) async {
      await pushDuringRefresh(t, const FakeReply(401, {'detail': 'revoked'}));
      expect(find.byType(SignInRequiredPage), findsOneWidget);
      expect(find.text('page:/seasons'), findsNothing);
    });
  });
}
