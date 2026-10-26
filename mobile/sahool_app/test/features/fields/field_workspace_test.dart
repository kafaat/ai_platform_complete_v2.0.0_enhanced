// مساحة عمل الحقل: خمسة تبويبات (كانت تسعة) والنظرة العامّة أوّلاً، اسم طويل
// بلا فيض (كان 722px)، أوقات السجلّ محلّيّة لا UTC، «غير مقيس» بدل 0/0٪ مختلقة،
// والجلب بالمعرّف عبر GET /api/v1/fields/{id} لا لوحة المؤشّرات.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/fields/presentation/common/cross_feature_routes.dart';
import 'package:sahool_app/features/fields/presentation/workspace/workspace_sections.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/satellite/data/satellite_api.dart';
import 'package:sahool_app/screens/field_workspace_screen.dart';

import 'harness.dart';

const _id = 'fld_1';
final _field = <String, dynamic>{
  'field_id': _id,
  'farm_id': 'frm_1',
  'name_ar': 'حقل البنّ',
  'crop': 'بنّ',
  'area_ha': 3.0,
  'quality_grade': 'LIMITED',
};

Backend backend({Map<String, dynamic>? seasonWorkspace}) => Backend({
  '/api/v1/fields/$_id': (_) => ok(_field),
  '/api/v1/fields/$_id/season-workspace': (_) => ok(
    seasonWorkspace ??
        {
          'field': {..._field, 'soil_ph': 7.2},
          'active_season': {
            'crops': ['بنّ'],
            'status': 'active',
            'sowing_date': '2026-03-01',
            'target_yield_kg_ha': 1200,
          },
          'readiness': {
            'score': 62,
            'label_ar': 'بيانات متوفرة جزئياً',
            'missing': [],
          },
          'canonical_state': null,
          'next_actions': [
            {
              'type': 'data_gap',
              'title_ar': 'أضف فحص تربة',
              'action_ar': 'سجّل نتيجة المختبر',
            },
          ],
          'soil_tests': [],
          'gaps': [],
        },
  ),
  '/api/v1/fields/$_id/priority-queue': (_) =>
      ok({'items': [], 'degraded': false}),
  '/api/vegetation/v1/analyze': (_) => ok({
    'indices': {
      'ndvi': {'value': 0.58, 'unit': 'dimensionless'},
    },
    'health': {'status': 'fair', 'label_ar': 'مقبول'},
  }),
  '/api/v1/fields/$_id/weather/disease-risk': (_) =>
      ok({'temperature_c': 24.0, 'humidity_pct': 60, 'risk_level': 'low'}),
  '/api/v1/fields/$_id/weather/irrigation-advice': (_) =>
      ok({'urgency': 'moderate', 'recommended_mm': 12.5}),
  '/api/v1/fields/$_id/activities': (_) => ok([]),
  '/api/v1/fields/$_id/unified-timeline': (_) => ok({
    'events': [
      {
        'timestamp': '2026-10-20T21:30:00Z',
        'summary_ar': 'ريّ',
        'category': 'operation',
      },
    ],
  }),
});

WorkspaceDeps deps(Backend b) => WorkspaceDeps(
  fields: FieldsApi(b.client),
  satellite: SatelliteApi(b.client),
  irrigation: IrrigationApi(b.client),
);

/// قائمة تبويب النظرة العامّة (لا TabBarView ولا الشرائح الأفقيّة).
Finder get overviewList => find
    .descendant(
      of: find.byType(WOverviewSection),
      matching: find.byType(Scrollable),
    )
    .first;

Future<void> settle(WidgetTester t) async {
  for (var i = 0; i < 10; i++) {
    await t.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  final original = routeExists;
  tearDown(() => routeExists = original);

  testWidgets('five tabs, Overview first; key metrics from the server', (
    t,
  ) async {
    final b = backend();
    await t.pumpWidget(
      host(
        FieldWorkspaceScreen(
          field: _field,
          deps: deps(b),
          role: AppRole.worker,
        ),
      ),
    );
    await settle(t);
    final tabs = t.widget<TabBar>(find.byKey(const ValueKey('workspace_tabs')));
    expect(tabs.tabs.length, 5);
    expect(kWorkspaceTabs.first, 'نظرة عامّة');
    expect(find.text('نظرة عامّة'), findsOneWidget);
    expect(find.text('الخطّ الزمنيّ'), findsNothing);
    expect(find.text('0.58'), findsOneWidget);
    await t.scrollUntilVisible(
      find.textContaining('أضف فحص تربة'),
      300,
      scrollable: overviewList,
    );
    // الحالة الموحّدة غائبة ⇒ «غير مقيس» لا «بيانات ناقصة» مُختلَقة.
    await t.scrollUntilVisible(
      find.textContaining('لم تُحسب الحالة'),
      300,
      scrollable: overviewList,
    );
    expect(find.textContaining(kNotMeasured), findsWidgets);
    expect(b.to('/api/v1/fields/$_id/season-workspace'), hasLength(1));
  });

  testWidgets('missing readiness shows "غير مقيس", never 0٪', (t) async {
    final b = backend(seasonWorkspace: {'field': _field, 'readiness': {}});
    await t.pumpWidget(
      host(FieldWorkspaceScreen(field: _field, deps: deps(b))),
    );
    await settle(t);
    final tile = find.byKey(const ValueKey('metric_readiness'));
    expect(
      find.descendant(of: tile, matching: find.text(kNotMeasured)),
      findsOneWidget,
    );
    expect(find.text('0٪'), findsNothing);
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('metric_days')),
        matching: find.text('لا موسم نشط'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('a very long field name does not overflow at 360dp', (t) async {
    t.view.physicalSize = const Size(360, 780);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.reset);
    final longName = {..._field, 'name_ar': 'حقل البنّ الكبير في الوادي ' * 30};
    await t.pumpWidget(
      host(
        FieldWorkspaceScreen(field: longName, deps: deps(backend())),
        textScale: 1.3,
      ),
    );
    await settle(t);
    expect(t.takeException(), isNull);
    expect(find.byKey(const ValueKey('workspace_header')), findsOneWidget);
  });

  testWidgets('id only: fetches GET /api/v1/fields/{id}, not the dashboard', (
    t,
  ) async {
    final b = backend();
    await t.pumpWidget(host(FieldWorkspaceScreen(fieldId: _id, deps: deps(b))));
    await settle(t);
    expect(b.to('/api/v1/fields/$_id'), hasLength(1));
    expect(b.to('/api/v1/indicators/dashboard'), isEmpty);
    expect(find.text('حقل البنّ'), findsWidgets);
  });

  testWidgets('unknown field id shows the typed 404 message', (t) async {
    final b = Backend();
    await t.pumpWidget(
      host(FieldWorkspaceScreen(fieldId: 'nope', deps: deps(b))),
    );
    await settle(t);
    expect(find.text('العنصر غير موجود.'), findsOneWidget);
    expect(find.byKey(const ValueKey('workspace_tabs')), findsNothing);
  });

  testWidgets('Operations → السجلّ shows local time, not UTC', (t) async {
    final b = backend();
    await t.pumpWidget(
      host(FieldWorkspaceScreen(field: _field, deps: deps(b))),
    );
    await settle(t);
    await t.tap(find.text('العمليّات'));
    await settle(t);
    await t.tap(find.text('السجلّ'));
    await settle(t);
    final expected = fmtDateTime(DateTime.parse('2026-10-20T21:30:00Z'));
    expect(find.text(expected), findsOneWidget);
    expect(
      expected,
      contains(
        DateTime.parse(
          '2026-10-20T21:30:00Z',
        ).toLocal().hour.toString().padLeft(2, '0'),
      ),
    );
  });

  testWidgets('quick actions: unregistered feature routes are reported, '
      'log activity falls back to the in-workspace sheet', (t) async {
    routeExists = (p) => false;
    final b = backend();
    await t.pumpWidget(
      host(
        FieldWorkspaceScreen(
          field: _field,
          deps: deps(b),
          role: AppRole.worker,
        ),
      ),
    );
    await settle(t);
    await t.scrollUntilVisible(
      find.byKey(const ValueKey('qa_scout')),
      200,
      scrollable: overviewList,
    );
    await t.tap(find.byKey(const ValueKey('qa_scout')));
    await t.pump();
    expect(find.text(kFeatureNotAvailableAr), findsOneWidget);
    await t.tap(find.byKey(const ValueKey('qa_activity')));
    await settle(t);
    expect(find.text('تسجيل نشاط'), findsWidgets);
    expect(find.text('حفظ في السجلّ'), findsOneWidget);
  });

  testWidgets('viewer gets no write quick actions', (t) async {
    await t.pumpWidget(
      host(
        FieldWorkspaceScreen(
          field: _field,
          deps: deps(backend()),
          role: AppRole.viewer,
        ),
      ),
    );
    await settle(t);
    await t.scrollUntilVisible(
      find.byKey(const ValueKey('qa_advisor')),
      200,
      scrollable: overviewList,
    );
    expect(find.byKey(const ValueKey('qa_scout')), findsNothing);
    expect(find.byKey(const ValueKey('qa_activity')), findsNothing);
  });
}
