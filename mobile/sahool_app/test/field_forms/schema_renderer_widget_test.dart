/// اختبارات widget للـrenderer الواحد (GAP-FIELD-FORMS-01 §15.3):
/// الأنواع الثمانية تتولّد من schema، unknown ⇒ fail-closed،
/// المخفيّ خارج payload، وV1/V2 بنفس الـrenderer بلا تعديل.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/field_forms/contract/form_schema.dart';
import 'package:sahool_app/features/field_forms/presentation/field_widget_registry.dart';
import 'package:sahool_app/features/field_forms/presentation/schema_form_renderer.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

Map<String, Object?> _schemaJson(List<Map<String, Object?>> fields) =>
    {'fields': fields};

Future<void> _pumpRenderer(
  WidgetTester tester, {
  required Map<String, Object?> schemaJson,
  Map<String, Object?>? logicJson,
  Map<String, Object?> initialAnswers = const {},
  PhotoPicker? photoPicker,
  void Function(Map<String, Object?>)? onValidSubmit,
}) async {
  await tester.pumpWidget(_wrap(SchemaFormRenderer(
    schema: FormSchema.fromJson(schemaJson),
    logicJson: logicJson,
    initialAnswers: initialAnswers,
    registry: FieldWidgetRegistry(photoPicker: photoPicker),
    onValidSubmit: onValidSubmit,
  )));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('text يتولّد من schema', (tester) async {
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {'key': 'notes', 'field_type': 'text'},
        ]));
    expect(find.byKey(const ValueKey('field_notes')), findsOneWidget);
    expect(find.byType(TextFormField), findsOneWidget);
  });

  testWidgets('number يتولّد من schema ويخزّن double', (tester) async {
    Map<String, Object?>? submitted;
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {'key': 'area', 'field_type': 'number'},
        ]),
        onValidSubmit: (a) => submitted = a);
    await tester.enterText(
        find.byKey(const ValueKey('field_area')), '3.5');
    await tester.tap(find.byKey(const ValueKey('schema_form_submit')));
    await tester.pumpAndSettle();
    expect(submitted, isNotNull);
    expect(submitted!['area'], isA<double>());
    expect(submitted!['area'], 3.5);
  });

  testWidgets('integer يتولّد ويخزّن int', (tester) async {
    Map<String, Object?>? submitted;
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {'key': 'count', 'field_type': 'integer'},
        ]),
        onValidSubmit: (a) => submitted = a);
    await tester.enterText(find.byKey(const ValueKey('field_count')), '3');
    await tester.tap(find.byKey(const ValueKey('schema_form_submit')));
    await tester.pumpAndSettle();
    expect(submitted!['count'], isA<int>());
    expect(submitted!['count'], 3);
  });

  testWidgets('select يتولّد من options', (tester) async {
    Map<String, Object?>? submitted;
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {
            'key': 'crop',
            'field_type': 'select',
            'options': ['wheat', 'barley'],
          },
        ]),
        onValidSubmit: (a) => submitted = a);
    await tester.tap(find.byKey(const ValueKey('field_crop')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('barley').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('schema_form_submit')));
    await tester.pumpAndSettle();
    expect(submitted!['crop'], 'barley');
  });

  testWidgets('multi_select يتولّد ويخزّن List<String>', (tester) async {
    Map<String, Object?>? submitted;
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {
            'key': 'pests',
            'field_type': 'multi_select',
            'options': ['aphid', 'thrips', 'mite'],
          },
        ]),
        onValidSubmit: (a) => submitted = a);
    await tester.tap(find.byKey(const ValueKey('field_pests_opt_thrips')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('field_pests_opt_aphid')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('schema_form_submit')));
    await tester.pumpAndSettle();
    expect(submitted!['pests'], isA<List>());
    expect(submitted!['pests'], ['aphid', 'thrips']); // بترتيب options
  });

  testWidgets('date يتولّد بصيغة YYYY-MM-DD', (tester) async {
    Map<String, Object?>? submitted;
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {'key': 'visit_date', 'field_type': 'date'},
        ]),
        initialAnswers: const {'visit_date': '2025-01-15'},
        onValidSubmit: (a) => submitted = a);
    expect(find.byKey(const ValueKey('field_visit_date')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('schema_form_submit')));
    await tester.pumpAndSettle();
    expect(submitted!['visit_date'], '2025-01-15');
    expect(
        RegExp(r'^\d{4}-\d{2}-\d{2}$')
            .hasMatch(submitted!['visit_date'] as String),
        isTrue);
  });

  testWidgets('gps يتولّد ويخزّن {lat,lng}', (tester) async {
    Map<String, Object?>? submitted;
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {'key': 'location', 'field_type': 'gps'},
        ]),
        onValidSubmit: (a) => submitted = a);
    await tester.enterText(
        find.byKey(const ValueKey('field_location_lat')), '24.7');
    await tester.enterText(
        find.byKey(const ValueKey('field_location_lng')), '46.7');
    await tester.tap(find.byKey(const ValueKey('schema_form_submit')));
    await tester.pumpAndSettle();
    expect(submitted!['location'], {'lat': 24.7, 'lng': 46.7});
  });

  testWidgets('photo يتولّد ويخزّن مرجع ملفّ لا Base64', (tester) async {
    Map<String, Object?>? submitted;
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {'key': 'evidence', 'field_type': 'photo'},
        ]),
        photoPicker: () async => '/tmp/pic_123.jpg',
        onValidSubmit: (a) => submitted = a);
    await tester.tap(find.byKey(const ValueKey('field_evidence_pick')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('schema_form_submit')));
    await tester.pumpAndSettle();
    expect(submitted!['evidence'], '/tmp/pic_123.jpg');
  });

  test('unknown field_type ⇒ UnsupportedFormSchemaException (fail-closed)',
      () {
    expect(
      () => FormSchema.fromJson(_schemaJson([
        {'key': 'mystery', 'field_type': 'hologram'},
      ])),
      throwsA(isA<UnsupportedFormSchemaException>()),
    );
  });

  testWidgets('الحقل المخفيّ ليس في payload', (tester) async {
    Map<String, Object?>? submitted;
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {'key': 'has_pest', 'field_type': 'select', 'options': ['yes', 'no']},
          {'key': 'pest_name', 'field_type': 'text'},
        ]),
        logicJson: const {
          'pest_name': {
            '==': [
              {'var': 'has_pest'},
              'yes',
            ],
          },
        },
        // pest_name له قيمة ابتدائيّة لكنّه مخفيّ (has_pest=no).
        initialAnswers: const {'has_pest': 'no', 'pest_name': 'aphid'},
        onValidSubmit: (a) => submitted = a);
    expect(find.byKey(const ValueKey('field_pest_name')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('schema_form_submit')));
    await tester.pumpAndSettle();
    expect(submitted, isNotNull);
    expect(submitted!.containsKey('pest_name'), isFalse,
        reason: 'قيمة الحقل المخفيّ تُزال من payload');
    expect(submitted!['has_pest'], 'no');
  });

  testWidgets('V1 وV2 بنفس الـrenderer بلا تعديل', (tester) async {
    // V1: حقلان.
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {'key': 'crop', 'field_type': 'select', 'options': ['wheat']},
          {'key': 'notes', 'field_type': 'text'},
        ]));
    expect(find.byKey(const ValueKey('field_crop')), findsOneWidget);
    expect(find.byKey(const ValueKey('field_notes')), findsOneWidget);

    // V2: حقل مضاف + ترتيب مغيَّر + options مغيَّرة + شرط مغيَّر — نفس الكود.
    await _pumpRenderer(tester,
        schemaJson: _schemaJson([
          {'key': 'notes', 'field_type': 'text'},
          {
            'key': 'crop',
            'field_type': 'select',
            'options': ['wheat', 'barley', 'maize'],
          },
          {'key': 'severity', 'field_type': 'integer'},
          {'key': 'pest_details', 'field_type': 'text'},
        ]),
        logicJson: const {
          'pest_details': {
            '>=': [
              {'var': 'severity'},
              3,
            ],
          },
        },
        initialAnswers: const {'severity': 4});
    expect(find.byKey(const ValueKey('field_severity')), findsOneWidget);
    expect(find.byKey(const ValueKey('field_pest_details')), findsOneWidget,
        reason: 'الشرط المغيَّر في V2 يعمل بنفس الـrenderer');
  });
}
