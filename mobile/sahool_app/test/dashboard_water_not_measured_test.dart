/// شاهد MOBILE-DASHBOARD-SAVINGS-PCT-HAS-NO-PRODUCER-01:
/// المُنتِج الوحيد للوحة (GET /api/v1/indicators/dashboard ⇒
/// services/sahool-platform/api/analytics_shapers.py `_shape_indicators_dashboard`)
/// يُعيد kpis/alerts/fields_summary/note_ar فقط — لا `water_usage`.
/// فبطاقة المياه يجب أن تُبنى بلا استثناء وتعرض «غير مقيس» بلا نسبة توفير ولا حجم،
/// ولوحة الجوّال يجب ألّا تقرأ `savings_pct`/`this_month_m3` أصلاً.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/widgets/water_usage_card.dart';

/// شكل حمولة المُنتِج الفعليّة (بلا `water_usage`).
final Map<String, dynamic> _producerPayload = <String, dynamic>{
  'kpis': <dynamic>[],
  'alerts': <dynamic>[],
  'fields_summary': <dynamic>[
    {'field_id': 'f1', 'field_name': 'حقل', 'area_ha': 1.5},
  ],
  'note_ar': 'عدّادات حيّة',
};

void main() {
  test('الحمولة الفعليّة بلا water_usage، والقراءة القديمة كانت تنهار', () {
    final data = _producerPayload;
    expect(data.containsKey('water_usage'), isFalse);
    // التعبير الذي كان في dashboard_screen.dart:172 قبل الإصلاح — شاهد أحمر.
    expect(() => '${data['water_usage']['savings_pct']}%',
        throwsA(isA<NoSuchMethodError>()));
  });

  testWidgets('بطاقة المياه تُبنى بلا استثناء وتعرض «غير مقيس» بلا نسبة توفير',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: Row(
          children: [
            Expanded(child: WaterUsageNotMeasuredCard()),
          ],
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text(kWaterNotMeasuredValue), findsOneWidget);
    expect(find.text(kWaterNotMeasuredNote), findsOneWidget);

    final texts = tester
        .widgetList<Text>(find.byType(Text))
        .map((t) => t.data ?? '')
        .toList();
    expect(texts, isNotEmpty);
    for (final t in texts) {
      expect(t.contains('%'), isFalse, reason: 'نسبة معروضة: $t');
      expect(t.contains('توفير'), isFalse, reason: 'ادّعاء توفير: $t');
      expect(t.contains('م³'), isFalse, reason: 'حجم بلا مُنتِج: $t');
      expect(t.contains('null'), isFalse, reason: 'مفتاح غائب معروض: $t');
    }
  });

  test('lib/screens/dashboard_screen.dart لا يقرأ savings_pct ولا this_month_m3',
      () {
    final src = File('lib/screens/dashboard_screen.dart');
    expect(src.existsSync(), isTrue,
        reason: 'يُشغَّل من جذر mobile/sahool_app');
    final violations = <String>[];
    final lines = src.readAsLinesSync();
    for (var i = 0; i < lines.length; i++) {
      // نتجاهل التعليقات التوثيقيّة التي تسمّي المفتاحين المحذوفين.
      final code = lines[i].replaceAll(RegExp(r'//.*$'), '');
      // المفتاح بين علامتي اقتباس (قراءة حمولة)، لا اسم ملف water_usage_card.dart.
      for (final key in ["'savings_pct'", "'this_month_m3'", "'water_usage'"]) {
        if (code.contains(key)) violations.add('${i + 1}: $key');
      }
    }
    expect(violations, isEmpty, reason: 'قراءة مفتاح بلا مُنتِج: $violations');
  });
}
