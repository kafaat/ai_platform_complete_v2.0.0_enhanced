/// اختبار تكافؤ corpus الـ26 (GAP-FIELD-FORMS-01 §15.3) — يجب 26/26.
///
/// - expect true/false ⇒ evaluateCondition يعيد تلك القيمة.
/// - expect "error" ⇒ التقييم يرفع ConditionTypeException.
/// - expect "invalid" ⇒ validateCondition يرفع ConditionException.
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/field_forms/contract/condition_v1.dart';

import 'condition_corpus_data.dart';

void main() {
  final cases =
      (jsonDecode(kConditionCorpusJson) as List).cast<Map<String, Object?>>();

  test('corpus يحتوي 26 حالة بالضبط', () {
    expect(cases.length, 26);
  });

  for (final testCase in cases) {
    final name = testCase['name'] as String;
    final condition = testCase['condition'];
    final answers =
        Map<String, Object?>.from(testCase['answers'] as Map? ?? {});
    final expect_ = testCase['expect'];

    test('corpus: $name', () {
      if (expect_ == 'invalid') {
        expect(() => validateCondition(condition),
            throwsA(isA<ConditionException>()));
      } else if (expect_ == 'error') {
        validateCondition(condition); // بنيويًّا سليم
        expect(() => evaluateCondition(condition, answers),
            throwsA(isA<ConditionTypeException>()));
      } else {
        validateCondition(condition);
        expect(evaluateCondition(condition, answers), expect_);
      }
    });
  }
}
