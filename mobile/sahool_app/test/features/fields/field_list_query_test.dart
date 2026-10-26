// منطق قائمة الحقول: بحث بالأرقام العربيّة، تصفية بالمزرعة/المحصول/الحالة،
// ترتيب الحالة (الأحوج أوّلاً) والأولويّة (غير المقيس آخراً).
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/fields/data/field_list_query.dart';

final fields = <Map<String, dynamic>>[
  {
    'field_id': '1',
    'farm_id': 'A',
    'name_ar': 'حقل البنّ ٣',
    'crop': 'بنّ',
    'area_ha': 2.0,
    'quality_grade': 'READY',
  },
  {
    'field_id': '2',
    'farm_id': 'A',
    'name_ar': 'حقل الذرة',
    'crop': 'ذرة',
    'area_ha': 0.0,
    'quality_grade': 'BLOCKED',
  },
  {
    'field_id': '3',
    'farm_id': '',
    'name_ar': 'أرض جديدة',
    'crop': '—',
    'area_ha': 5.5,
    'quality_grade': 'PENDING_LAB',
    'field_code': 'F-7',
  },
  {
    'field_id': '4',
    'farm_id': 'B',
    'name_ar': 'حقل القمح',
    'crop': 'قمح',
    'area_ha': 1.0,
    'quality_grade': 'LIMITED',
  },
];

List<String> ids(List<Map<String, dynamic>> l) =>
    l.map((f) => '${f['field_id']}').toList();

void main() {
  test('search matches name/crop/code and normalises Arabic-Indic digits', () {
    expect(ids(applyFieldQuery(fields, const FieldQuery(text: '3'))), ['1']);
    expect(ids(applyFieldQuery(fields, const FieldQuery(text: 'ذرة'))), ['2']);
    expect(ids(applyFieldQuery(fields, const FieldQuery(text: 'f-7'))), ['3']);
  });

  test('filters: farm ("" = unassigned), crop ("" = none), status', () {
    expect(ids(applyFieldQuery(fields, const FieldQuery(farmId: 'A'))), [
      '1',
      '2',
    ]);
    expect(ids(applyFieldQuery(fields, const FieldQuery(farmId: ''))), ['3']);
    expect(ids(applyFieldQuery(fields, const FieldQuery(crop: ''))), ['3']);
    expect(ids(applyFieldQuery(fields, const FieldQuery(status: 'LIMITED'))), [
      '4',
    ]);
  });

  test(
    'status sort puts the neediest first; area sort puts unknown (0) last',
    () {
      expect(
        ids(applyFieldQuery(fields, const FieldQuery(sort: FieldSort.status))),
        ['2', '3', '4', '1'],
      );
      expect(
        ids(applyFieldQuery(fields, const FieldQuery(sort: FieldSort.area))),
        ['3', '1', '4', '2'],
      );
    },
  );

  test('priority sort: worst severity, then count; unmeasured fields last', () {
    final p = PriorityData.fromItems(
      [
        {'field_id': '4', 'severity': 'low'},
        {'field_id': '4', 'severity': 'low'},
        {'field_id': '1', 'severity': 'critical'},
        {'field_id': 'x', 'severity': 'critical'}, // حقل خارج القائمة يُهمل
      ],
      measured: ['1', '2', '4'],
    );
    expect(p.byField['2']!.count, 0);
    expect(p.byField.containsKey('3'), isFalse);
    final out = applyFieldQuery(
      fields,
      const FieldQuery(sort: FieldSort.priority),
      priority: p,
    );
    expect(ids(out), ['1', '4', '2', '3']);
  });
}
