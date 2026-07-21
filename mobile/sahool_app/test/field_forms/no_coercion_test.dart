/// لا coercion إطلاقًا (GAP-FIELD-FORMS-01 §8):
/// السلسلة "3" لا تُحوَّل إلى number/integer أبدًا، وinteger لا يقبل 3.5.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/field_forms/contract/form_schema.dart';

FormSchema _schema(List<Map<String, Object?>> fields) =>
    FormSchema.fromJson({'fields': fields});

void main() {
  test('نصّ "3" لحقل number يُرفض ولا يصبح عددًا', () {
    final schema = _schema([
      {'key': 'area', 'field_type': 'number'},
    ]);
    final visible = {'area'};
    final errors = validateAnswers(
      schema: schema,
      visibleKeys: visible,
      answers: const {'area': '3'}, // String — يجب أن يبقى مرفوضًا
    );
    expect(errors.containsKey('area'), isTrue,
        reason: 'لا coercion من String إلى number');
  });

  test('number يقبل int وdouble ويخزّنهما كما هما', () {
    final schema = _schema([
      {'key': 'a', 'field_type': 'number'},
      {'key': 'b', 'field_type': 'number'},
    ]);
    final errors = validateAnswers(
      schema: schema,
      visibleKeys: const {'a', 'b'},
      answers: const {'a': 3, 'b': 3.5},
    );
    expect(errors, isEmpty);
  });

  test('integer يبقى int: يقبل 3 ويرفض 3.5 ويرفض "3"', () {
    final schema = _schema([
      {'key': 'count', 'field_type': 'integer'},
    ]);
    const visible = {'count'};

    expect(
      validateAnswers(
          schema: schema, visibleKeys: visible, answers: const {'count': 3}),
      isEmpty,
    );
    expect(
      validateAnswers(
          schema: schema, visibleKeys: visible, answers: const {'count': 3.5}),
      contains('count'),
      reason: 'double 3.5 لا يُقتطع إلى int',
    );
    expect(
      validateAnswers(
          schema: schema, visibleKeys: visible, answers: const {'count': '3'}),
      contains('count'),
      reason: 'السلسلة "3" لا تُحوَّل إلى integer',
    );
  });

  test('bool لا يُقبل عددًا (bool ليس num في الدلالات)', () {
    final schema = _schema([
      {'key': 'flag_num', 'field_type': 'number'},
    ]);
    expect(
      validateAnswers(
          schema: schema,
          visibleKeys: const {'flag_num'},
          answers: const {'flag_num': true}),
      contains('flag_num'),
    );
  });

  test('select يقبل قيمة من options فقط — بلا تحويل', () {
    final schema = _schema([
      {
        'key': 'crop',
        'field_type': 'select',
        'options': ['wheat', 'barley'],
      },
    ]);
    expect(
      validateAnswers(
          schema: schema,
          visibleKeys: const {'crop'},
          answers: const {'crop': 'wheat'}),
      isEmpty,
    );
    expect(
      validateAnswers(
          schema: schema,
          visibleKeys: const {'crop'},
          answers: const {'crop': 'rice'}),
      contains('crop'),
    );
  });

  test('مفتاح خارج schema يُمنع من الإرسال', () {
    final schema = _schema([
      {'key': 'notes', 'field_type': 'text'},
    ]);
    final errors = validateAnswers(
      schema: schema,
      visibleKeys: const {'notes'},
      answers: const {'notes': 'ok', 'injected': 'x'},
    );
    expect(errors, contains('injected'));
    // وpayload النهائيّ لا يحمله أصلًا
    final payload = buildSubmissionAnswers(
      schema: schema,
      visibleKeys: const {'notes'},
      answers: const {'notes': 'ok', 'injected': 'x'},
    );
    expect(payload.containsKey('injected'), isFalse);
  });
}
