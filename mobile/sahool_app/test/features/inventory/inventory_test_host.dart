// أدوات اختبار ميزة المخزون: عميل حقيقيّ فوق محوّل مزيّف، ومضيف MaterialApp
// عربيّ بالسمة الفاتحة ومندوبي التعريب (بدونهم يرمي كلّ TextField).
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../../core/fake_http.dart';

export '../../core/fake_http.dart';

ApiClient fakeClient(FakeAdapter adapter) => testClient(
  adapter,
  MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
);

/// يردّ حسب (الطريقة، المسار)؛ ما لا يطابق ⇒ 404.
FakeAdapter routeAdapter(
  Map<String, FutureOr<FakeReply> Function(RequestOptions o)> routes,
) => FakeAdapter((o) async {
  final h = routes['${o.method} ${o.path}'];
  if (h == null) return const FakeReply(404, {'detail': 'not routed'});
  return h(o);
});

Widget hostApp(Widget home, {ThemeData? theme, double textScale = 1}) =>
    MaterialApp(
      theme: theme ?? AppTheme.light,
      builder: (c, child) => MediaQuery(
        data: MediaQuery.of(
          c,
        ).copyWith(textScaler: TextScaler.linear(textScale)),
        child: child!,
      ),
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: home,
    );

/// يضخّ ثمّ يترك الطلبات المزيّفة تكتمل (لا pumpAndSettle: مؤشّر التحميل لا يستقرّ).
Future<void> settle(WidgetTester t, {int frames = 6}) async {
  for (var i = 0; i < frames; i++) {
    await t.pump(const Duration(milliseconds: 20));
  }
}

class FakeOutbox implements OfflineOutbox {
  FakeOutbox({this.accept = true});
  final bool accept;
  final List<OutboxOp> ops = [];

  @override
  Future<OutboxReceipt> enqueue(OutboxOp op) async {
    ops.add(op);
    return accept
        ? const OutboxReceipt.queued()
        : const OutboxReceipt.notQueued('test');
  }

  @override
  Stream<int> get pendingCount => Stream<int>.value(ops.length);
}
