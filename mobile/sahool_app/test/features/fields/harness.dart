// أدوات اختبار مشتركة لميزات الحقول/المزارع/الأقمار: عميل ApiClient حقيقيّ فوق
// FakeAdapter بردود حسب المسار، ومضيف MaterialApp عربيّ RTL بسمة التطبيق.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/theme/app_theme.dart';

import '../../core/fake_http.dart';

typedef Route = FutureOr<FakeReply> Function(RequestOptions o);

/// يردّ حسب المسار؛ غير المعرَّف ⇒ 404.
class Backend {
  Backend([Map<String, Route>? routes]) : routes = {...?routes};
  final Map<String, Route> routes;

  /// كلّ الطلبات بخياراتها الكاملة (المعاملات والترويسات).
  final List<RequestOptions> seen = [];
  late final FakeAdapter adapter = FakeAdapter((o) async {
    seen.add(o);
    final r = routes[o.path];
    if (r == null) return const FakeReply(404, {'detail': 'not found'});
    return await r(o);
  });
  late final ApiClient client = testClient(
    adapter,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  );

  List<RequestOptions> to(String path) =>
      seen.where((o) => o.path == path).toList();
}

FakeReply ok(Object body) => FakeReply(200, body);

Widget host(
  Widget child, {
  double textScale = 1.0,
  bool scaffold = false,
  Map<String, WidgetBuilder> routes = const {},
}) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar'), Locale('en')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  routes: routes,
  builder: (context, w) => MediaQuery(
    data: MediaQuery.of(
      context,
    ).copyWith(textScaler: TextScaler.linear(textScale)),
    child: w!,
  ),
  home: scaffold ? Scaffold(body: child) : child,
);
