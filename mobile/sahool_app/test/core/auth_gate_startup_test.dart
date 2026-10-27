// بوّابة الجلسة عند الإقلاع (UI-C1): جلسة محفوظة صالحة + مصافحة WebSocket لا
// تكتمل أبداً ⇒ يظهر الغلاف (REST صالح) ولا يبقى المستخدم خلف شاشة التحميل. الزمن
// الحقيقيّ مقيس بالمؤقّت الوهميّ: لا مهلة تطبيق صريحة على الـWS قبل الإصلاح.
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/routing/app_shell.dart';
import 'package:sahool_app/core/widgets/app_states.dart';
import 'package:sahool_app/features/field_forms/data/form_package_store.dart';
import 'package:sahool_app/features/field_forms/data/submission_queue.dart';
import 'package:sahool_app/main.dart';
import 'package:sahool_app/services/auth_service.dart';
import 'package:sahool_app/services/websocket_service.dart';

import 'fake_http.dart';

/// عميل HTTP لا يُكمل أيّ اتّصال (نقطة WS «ثقب أسود»).
class _BlackholeHttpClient implements HttpClient {
  int opened = 0;

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) {
    opened++;
    return Completer<HttpClientRequest>().future;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _BlackholeOverrides extends HttpOverrides {
  final client = _BlackholeHttpClient();
  @override
  HttpClient createHttpClient(SecurityContext? context) => client;
}

void main() {
  late Directory dir;

  // صناديق Hive التي يفتحها الإقلاع (main وFieldFormsCoordinator) تُفتَح هنا خارج
  // الزمن الوهميّ، فيعيدها openBox داخل الاختبار فوراً.
  setUp(() async {
    dir = await Directory.systemTemp.createTemp('auth_gate');
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

  testWidgets('a saved session shows the shell while the WS handshake hangs',
      (t) async {
    FlutterSecureStorage.setMockInitialValues({
      'access_token': fakeJwt(const Duration(hours: 1)),
      'user_id': 'u1',
      'user_profile': '{"user_id":"u1","role":"owner"}',
    });
    final overrides = _BlackholeOverrides();
    await HttpOverrides.runZoned(() async {
      await t.pumpWidget(const SAHOOLApp());
      for (var i = 0; i < 20; i++) {
        await t.pump(const Duration(milliseconds: 100));
      }
    }, createHttpClient: overrides.createHttpClient);
    // المصافحة بدأت فعلاً ولم تكتمل.
    expect(overrides.client.opened, greaterThan(0));
    expect(WebSocketService.instance.isConnected, isFalse);
    expect(find.byType(LoadingState), findsNothing);
    expect(find.byType(AppShell), findsOneWidget);
    // تفكيك الشجرة وتصريف مؤقّتات الغلاف قبل نهاية الاختبار.
    await t.pumpWidget(const SizedBox.shrink());
    await t.pump(const Duration(minutes: 1));
  });
}
