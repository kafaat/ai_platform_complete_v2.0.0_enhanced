// «حقولي»: الاسم من name_ar (كان يُقرأ name فيظهر «حقل 1»)، البحث، الحالة
// الفارغة بزرّ الإضافة للمحرّرين فقط، الترتيب بالأولويّة من الطوابير الحقيقيّة،
// ومبدّل الخريطة يقول بصدق إن لم تُسجَّل ميزة الخرائط.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/fields/presentation/common/cross_feature_routes.dart';
import 'package:sahool_app/features/fields/presentation/fields_screen.dart';

import 'harness.dart';

final _fields = [
  {
    'field_id': 'f1',
    'farm_id': 'frm_1',
    'name_ar': 'حقل البنّ الشماليّ',
    'crop': 'بنّ',
    'area_ha': 2.5,
    'quality_grade': 'READY',
  },
  {
    'field_id': 'f2',
    'farm_id': 'frm_1',
    'name_ar': 'حقل الذرة',
    'crop': 'ذرة',
    'area_ha': 0.0,
    'quality_grade': 'BLOCKED',
  },
  {
    'field_id': 'f3',
    'farm_id': '',
    'name_ar': 'أرض بلا مزرعة',
    'crop': '—',
    'area_ha': 1.0,
    'quality_grade': 'LIMITED',
  },
];

Backend backend({List<Map<String, dynamic>>? fields}) => Backend({
  '/api/v1/fields': (_) => ok(fields ?? _fields),
  '/api/v1/farms': (_) => ok([
    {'farm_id': 'frm_1', 'name': 'مزرعة الوادي'},
  ]),
  '/api/v1/farms/frm_1/priority-queue': (_) => ok({
    'items': [
      {'field_id': 'f2', 'severity': 'critical', 'type': 'alert'},
    ],
    'degraded': false,
  }),
  '/api/v1/fields/f3/priority-queue': (_) =>
      ok({'items': [], 'degraded': false}),
});

Widget screen(Backend b, {AppRole role = AppRole.worker}) => host(
  FieldsScreen(
    key: UniqueKey(),
    fieldsApi: FieldsApi(b.client),
    farmsApi: FarmsApi(b.client),
    role: () => role,
  ),
  routes: {'/fields/new': (_) => const Scaffold(body: Text('wizard'))},
);

void main() {
  final original = routeExists;
  tearDown(() => routeExists = original);

  testWidgets(
    'cards show name_ar, crop, formatted area; zero area is not 0 هـ',
    (t) async {
      await t.pumpWidget(screen(backend()));
      await t.pumpAndSettle();
      expect(find.text('حقل البنّ الشماليّ'), findsOneWidget);
      expect(find.textContaining('2.5 هـ'), findsOneWidget);
      expect(find.textContaining('0 هـ'), findsNothing);
      expect(find.textContaining('بلا محصول'), findsOneWidget);
      expect(find.textContaining('مزرعة الوادي'), findsWidgets);
    },
  );

  testWidgets('search narrows the list and offers to clear filters', (t) async {
    await t.pumpWidget(screen(backend()));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const ValueKey('fields_search')), 'ذرة');
    await t.pumpAndSettle();
    expect(find.byKey(const ValueKey('field_f2')), findsOneWidget);
    expect(find.byKey(const ValueKey('field_f1')), findsNothing);
    await t.enterText(find.byKey(const ValueKey('fields_search')), 'لا يوجد');
    await t.pumpAndSettle();
    expect(find.byKey(const ValueKey('fields_no_match')), findsOneWidget);
    await t.tap(find.text('مسح الفلاتر'));
    await t.pumpAndSettle();
    expect(find.byKey(const ValueKey('field_f1')), findsOneWidget);
  });

  testWidgets('empty: editors get an "add field" CTA to the wizard route; '
      'viewers do not', (t) async {
    await t.pumpWidget(screen(backend(fields: [])));
    await t.pumpAndSettle();
    expect(find.byKey(const ValueKey('fields_empty')), findsOneWidget);
    await t.tap(find.text('إضافة حقل'));
    await t.pumpAndSettle();
    expect(find.text('wizard'), findsOneWidget);

    await t.pumpWidget(screen(backend(fields: []), role: AppRole.viewer));
    await t.pumpAndSettle();
    expect(find.text('إضافة حقل'), findsNothing);
  });

  testWidgets('priority sort uses farm and per-field queues', (t) async {
    final b = backend();
    await t.pumpWidget(screen(b));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const ValueKey('fields_sort')));
    await t.pumpAndSettle();
    await t.tap(find.text('الأولويّة (تنبيهات ومهامّ)'));
    await t.pumpAndSettle();
    expect(b.to('/api/v1/farms/frm_1/priority-queue'), hasLength(1));
    expect(b.to('/api/v1/fields/f3/priority-queue'), hasLength(1));
    final y2 = t.getTopLeft(find.byKey(const ValueKey('field_f2'))).dy;
    final y1 = t.getTopLeft(find.byKey(const ValueKey('field_f1'))).dy;
    expect(y2, lessThan(y1), reason: 'الحقل ذو التنبيه الحرج أوّلاً');
    expect(find.textContaining('1 بنود مفتوحة · حرج'), findsOneWidget);
  });

  testWidgets('map toggle: unregistered maps route says so honestly', (
    t,
  ) async {
    routeExists = (p) => false;
    await t.pumpWidget(screen(backend()));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const ValueKey('fields_map_toggle')));
    await t.pump();
    expect(find.text(kFeatureNotAvailableAr), findsOneWidget);
  });

  testWidgets('a long field name wraps without overflow at 360dp / 1.3x', (
    t,
  ) async {
    t.view.physicalSize = const Size(360, 800);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.reset);
    await t.pumpWidget(
      host(
        FieldsScreen(
          fieldsApi: FieldsApi(
            backend(
              fields: [
                {
                  'field_id': 'L',
                  'farm_id': '',
                  'name_ar': 'حقل ' * 60,
                  'crop': 'بنّ',
                  'area_ha': 1.0,
                  'quality_grade': 'PENDING_LAB',
                },
              ],
            ).client,
          ),
          farmsApi: FarmsApi(Backend().client),
          role: () => AppRole.owner,
        ),
        textScale: 1.3,
      ),
    );
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
  });
}
