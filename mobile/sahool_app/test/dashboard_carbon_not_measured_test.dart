/// Exercise the real dashboard with the producer's payload, which has no carbon.
library;

import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/screens/dashboard_screen.dart';
import 'package:sahool_app/services/api_service.dart';

void main() {
  testWidgets('dashboard accepts producer payload without inventing carbon',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final stub = InterceptorsWrapper(onRequest: (options, handler) {
      expect(options.path, '/api/v1/indicators/dashboard');
      handler.resolve(Response<Map<String, dynamic>>(
        requestOptions: options,
        statusCode: 200,
        data: {
          'kpis': <dynamic>[],
          'alerts': <dynamic>[],
          'fields_summary': [
            {'field_id': 'f1', 'field_name': 'حقل', 'area_ha': 1.5},
          ],
          'note_ar': 'عدّادات حيّة',
        },
      ));
    });
    ApiService.instance.dio.interceptors.insert(0, stub);
    addTearDown(() => ApiService.instance.dio.interceptors.remove(stub));

    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: DashboardScreen()),
    ));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('الكربون غير مقيس'), findsOneWidget);
    final carbonCard = find.widgetWithText(Card, 'الكربون المخزّن');
    expect(carbonCard, findsOneWidget);
    final texts = tester
        .widgetList<Text>(find.descendant(of: carbonCard, matching: find.byType(Text)))
        .map((t) => t.data ?? '');
    expect(texts, contains('غير مقيس'));
    for (final text in texts) {
      expect(text.contains('null'), isFalse);
      expect(text.contains('كجم'), isFalse);
      expect(text.contains(r'$'), isFalse);
      expect(RegExp(r'\d').hasMatch(text), isFalse);
    }
  });

  test('dashboard never reads unproduced carbon payload values', () {
    final source = File('lib/screens/dashboard_screen.dart')
        .readAsLinesSync()
        .map((line) => line.replaceAll(RegExp(r'//.*$'), ''))
        .join('\n');
    for (final key in ["'carbon'", "'sequestered_kg'", "'credit_value_usd'"]) {
      expect(source.contains(key), isFalse, reason: 'unproduced key: $key');
    }
    expect(source.contains('CarbonNotMeasuredCard()'), isTrue);
  });
}
