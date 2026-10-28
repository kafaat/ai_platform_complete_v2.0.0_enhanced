// D2: فشل الشبكة أثناء تجديد الجلسة عند الإقلاع «غير معروف» لا رفض للهويّة.
// جلسة محفوظة برمز وصول منتهٍ ورمز تحديث، والشبكة مقطوعة (كلّ اتّصال يفشل فوراً
// بـSocketException): AuthGate الحقيقيّة تعرض الغلاف لا شاشة الدخول، ورمز التحديث
// يبقى على القرص (يُعاد فتح المخزن بعد تفكيك الشاشة). قبل الإصلاح كان أيّ فشل
// للتجديد يُنزل المستخدم إلى شاشة الدخول وكأنّ الخادم رفض هويّته.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/routing/app_shell.dart';
import 'package:sahool_app/features/auth/presentation/login_screen.dart';
import 'package:sahool_app/features/field_forms/data/form_package_store.dart';
import 'package:sahool_app/features/field_forms/data/submission_queue.dart';
import 'package:sahool_app/main.dart';
import 'package:sahool_app/services/auth_service.dart';
import 'package:sahool_app/services/websocket_service.dart';

import 'fake_http.dart';

/// عميل HTTP بلا شبكة: كلّ اتّصال يفشل فوراً كما يفشل بلا تغطية.
class _OfflineHttpClient implements HttpClient {
  final opened = <Uri>[];

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) {
    opened.add(url);
    return Future.error(const SocketException('network is unreachable'));
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _OfflineOverrides extends HttpOverrides {
  final client = _OfflineHttpClient();
  @override
  HttpClient createHttpClient(SecurityContext? context) => client;
}

void main() {
  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('auth_gate_unknown');
    Hive.init(dir.path);
    await Hive.openBox<dynamic>('settings');
    await Hive.openBox<dynamic>(FormPackageStore.boxName);
    await Hive.openBox<dynamic>(SubmissionQueue.boxName);
  });

  tearDown(() async {
    await WebSocketService.instance.dispose();
    await AuthService.instance.clearAuth();
    await Hive.close();
    await dir.delete(recursive: true);
  });

  testWidgets('offline refresh at startup keeps the shell and the refresh token',
      (t) async {
    FlutterSecureStorage.setMockInitialValues({
      'access_token': fakeJwt(const Duration(minutes: -5)),
      'refresh_token': 'r-keep',
      'user_id': 'u1',
      'user_profile': '{"user_id":"u1","role":"owner","tenant_id":"t1"}',
    });
    final overrides = _OfflineOverrides();
    await HttpOverrides.runZoned(() async {
      await t.pumpWidget(const SAHOOLApp());
      for (var i = 0; i < 20; i++) {
        await t.pump(const Duration(milliseconds: 100));
      }
    }, createHttpClient: overrides.createHttpClient);

    // التجديد حاول فعلاً وفشل على الشبكة.
    expect(overrides.client.opened.any((u) => u.path.endsWith('/auth/refresh')),
        isTrue);
    expect(AuthService.instance.isAuthenticated, isFalse);
    expect(find.byType(LoginScreen), findsNothing,
        reason: 'انقطاع الشبكة ليس رفضاً للهويّة');
    expect(find.byType(AppShell), findsOneWidget);

    await t.pumpWidget(const SizedBox.shrink());
    await t.pump(const Duration(minutes: 1));

    // أعِد فتح المخزن: رمز التحديث ما زال على القرص.
    await AuthService.instance.loadSaved();
    expect(AuthService.instance.refreshToken, 'r-keep');
    expect(AuthService.instance.canResumeSession, isTrue);
  });
}
