// أدوات اختبار مشتركة لميزة التنبيهات: خادم مزيّف بمسارات حقيقيّة فوق
// FakeAdapter (ApiClient الحقيقيّ نفسه)، ومضيف ودجات عربيّ.
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:sahool_app/core/theme/app_theme.dart';

import '../../core/fake_http.dart';

Map<String, dynamic> alertJson(
  String id, {
  String severity = 'warning',
  String status = 'active',
  String? fieldId = 'f1',
  String? title,
  String? message,
  String type = 'low_moisture',
}) => {
  'alert_id': id,
  'field_id': fieldId,
  'alert_type': type,
  'severity': severity,
  'title_ar': title ?? 'تنبيه $id',
  'message_ar': message,
  'status': status,
  'created_at': '2026-10-26T08:00:00+00:00',
};

/// يحوّل جسم الطلب المسجَّل (نصّ JSON أو Map) إلى Map.
Map<String, dynamic> bodyOf(RecordedRequest r) {
  final d = r.data;
  if (d is Map) return d.cast<String, dynamic>();
  if (d is String) return (jsonDecode(d) as Map).cast<String, dynamic>();
  throw StateError('no body');
}

FakeAdapter routes(Map<String, FakeReply Function(RequestOptions)> table) =>
    FakeAdapter((o) async {
      final key = '${o.method} ${o.path}';
      final h = table[key];
      if (h == null) return const FakeReply(404, {'detail': 'no route'});
      return h(o);
    });

Widget arHost(Widget child, {double textScale = 1.0}) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar'), Locale('en')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  builder: (context, c) => MediaQuery(
    data: MediaQuery.of(
      context,
    ).copyWith(textScaler: TextScaler.linear(textScale)),
    child: c!,
  ),
  home: child,
);
