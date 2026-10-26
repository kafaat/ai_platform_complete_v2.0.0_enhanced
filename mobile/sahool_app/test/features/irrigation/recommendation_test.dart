// «هل أروي اليوم؟»: الكرت يعرض ما أعاده الخادم فقط. insufficient_data (بعد
// تغييرات الخادم: depletion_upper_bound_mm + irrigation_known) لا يُظهر أيّ كمّيّة ريّ.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_models.dart';
import 'package:sahool_app/features/irrigation/presentation/today/irrigation_today_screen.dart';
import 'package:sahool_app/features/irrigation/presentation/today/recommendation_card.dart';
import 'package:sahool_app/features/irrigation/presentation/today/recommendation_cubit.dart';

import 'irrigation_test_helpers.dart';

/// استجابة insufficient_data كما يبنيها irrigation_recommendation.py حين يكون
/// الريّ المضاف مجهولاً (depletion_is_upper_bound).
Map<String, dynamic> insufficientUpperBound() => {
  'status': 'insufficient_data',
  'field_id': 'f1',
  'season_id': 's1',
  'inputs': {
    'depletion_mm': null,
    'taw_mm': 120.0,
    'raw_fraction': 0.5,
    'depletion_fraction': null,
    'taw_source': 'texture_fallback',
    'ledger_age_hours': 3.2,
    'applied_water_status': 'unrecorded',
    'irrigation_known': false,
    'depletion_upper_bound_mm': 42.5,
    'crop': 'wheat',
    'stage': 'mid',
  },
  'recommendation': null,
  'ownership': 'recommendation_candidate → decision-service',
  'confidence': null,
  'evidence_ids': ['field-context:f1'],
  'limitations': [
    'applied_water_unknown_depletion_is_upper_bound',
    'applied_water_unrecorded — لا سجلَّ ريٍّ لهذا الحقل في يوم القيد: الريُّ في الميزان مجهولٌ لا صفر.',
  ],
  'calibrated': false,
};

Map<String, dynamic> ready({
  bool? should = true,
  bool hold = false,
  num? target = 18.5,
}) => {
  'status': 'recommendation_ready',
  'field_id': 'f1',
  'generated_on': '2026-10-26',
  'inputs': {'depletion_mm': 37.0, 'taw_mm': 120.0, 'irrigation_known': true},
  'recommendation': {
    'should_irrigate': should,
    'trigger_reason': 'depletion_at_or_above_trigger',
    'net_irrigation_mm': 21.0,
    'target_refill_mm': target,
    'water_stress_class': 'watch',
    'urgency': 'moderate',
    'timing_ar': 'اروِ صباحاً',
    'rationale_ar': 'الاستنزاف بلغ العتبة',
    'forecast_hold': hold,
    'policy_knobs': {},
  },
  'approval_state': 'not_submitted',
  'confidence': 0.55,
  'limitations': ['taw_uncalibrated'],
  'calibrated': false,
};

Widget card(Map<String, dynamic> json, {num? areaHa, VoidCallback? onLog}) =>
    host(
      Scaffold(
        body: SingleChildScrollView(
          child: RecommendationCard(
            recommendation: IrrigationRecommendation.fromJson(json),
            areaHa: areaHa,
            onLogWater: onLog,
          ),
        ),
      ),
    );

void main() {
  testWidgets(
    'insufficient_data shows the upper bound by name and never a quantity',
    (t) async {
      var logged = 0;
      await t.pumpWidget(
        card(insufficientUpperBound(), areaHa: 2, onLog: () => logged++),
      );
      expect(find.text('لا تكفي البيانات لقرار ريّ اليوم'), findsOneWidget);
      expect(
        find.text('حدّ أعلى للاستنزاف (ليس قياساً ولا كمّيّة ريّ)'),
        findsOneWidget,
      );
      expect(find.text('42.5'), findsOneWidget);
      // الريّ المضاف «غير مسجَّل» لا «صفر»، والسبب مترجَم.
      expect(find.text('غير مسجَّل'), findsOneWidget);
      expect(
        find.text(
          'الريّ المضاف غير مسجَّل، فالاستنزاف المحسوب حدٌّ أعلى لا قياس.',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('لا سجلَّ ريٍّ لهذا الحقل'), findsOneWidget);
      // لا كمّيّة ريّ ولا تحويل م³ من رقم لم يُعطه الخادم.
      expect(find.text('كمّيّة الملء المقترحة'), findsNothing);
      expect(find.textContaining('الاحتياج الصافي'), findsNothing);
      expect(find.textContaining('م³'), findsNothing);
      expect(
        find.text('مرشَّح — لم يُقدَّم للاعتماد'),
        findsNothing,
      ); // لا approval_state في هذا الردّ
      expect(find.text('مرشَّح — غير معتمَد'), findsOneWidget);
      await t.tap(find.text('سجّل ماء الريّ المضاف'));
      expect(logged, 1);
    },
  );

  testWidgets('irrigation_known=null is "not declared", not recorded', (
    t,
  ) async {
    final j = insufficientUpperBound();
    (j['inputs'] as Map)['irrigation_known'] = null;
    (j['inputs'] as Map)['depletion_upper_bound_mm'] = null;
    await t.pumpWidget(card(j));
    expect(find.text('غير معلَن'), findsOneWidget);
    expect(find.textContaining('حدّ أعلى للاستنزاف'), findsNothing);
  });

  testWidgets(
    'ready + should_irrigate shows the server quantity and its m³ equivalent',
    (t) async {
      await t.pumpWidget(card(ready(), areaHa: 2));
      expect(find.text('نعم — يُقترَح الريّ اليوم'), findsOneWidget);
      expect(find.text('18.5'), findsOneWidget);
      expect(find.text('≈ 370 م³ لمساحة الحقل'), findsOneWidget);
      expect(find.text('اروِ صباحاً'), findsOneWidget);
      expect(find.text('مرشَّح — لم يُقدَّم للاعتماد'), findsOneWidget);
      expect(find.text('غير معايَر ميدانيّاً'), findsOneWidget);
    },
  );

  testWidgets('forecast hold: no decision and no refill quantity', (t) async {
    await t.pumpWidget(card(ready(should: null, hold: true, target: null)));
    expect(
      find.text('مؤجَّل — مطر متوقَّع، أعِد التقييم بعده'),
      findsOneWidget,
    );
    expect(find.text('كمّيّة الملء المقترحة'), findsNothing);
  });

  testWidgets('dependency_unavailable shows no number', (t) async {
    await t.pumpWidget(
      card({
        'status': 'dependency_unavailable',
        'inputs': {'depletion_mm': 30.0},
        'recommendation': null,
        'limitations': [
          'weather-engine ET0 unavailable — fail-closed (no local ET0 fallback)',
        ],
        'calibrated': false,
      }),
    );
    expect(
      find.text('تعذّر الحصول على الطقس أو ET₀ — لا توصية الآن'),
      findsOneWidget,
    );
    expect(find.text('30'), findsNothing);
  });

  test('a response without status is a shape error, not an empty answer', () {
    expect(
      () => IrrigationRecommendation.fromJson({'recommendation': null}),
      throwsFormatException,
    );
  });

  test(
    'a slow answer for the previous field never overwrites the current one',
    () async {
      final slow = <String, Future<FakeReply>>{};
      final h = IrrigationHarness((o) => slow[o.path]!);
      final c = RecommendationCubit(h.api);
      final a = Future<FakeReply>.delayed(
        const Duration(milliseconds: 30),
        () => FakeReply(200, ready()),
      );
      slow['/api/v1/fields/fa/irrigation-recommendation'] = a;
      slow['/api/v1/fields/fb/irrigation-recommendation'] = Future.value(
        FakeReply(200, insufficientUpperBound()),
      );
      final first = c.load('fa');
      await c.load('fb');
      await first;
      final s = c.state as RecommendationLoaded;
      expect(s.fieldId, 'fb');
      expect(s.recommendation.status, 'insufficient_data');
      await c.close();
    },
  );

  testWidgets('today screen: picks the field and renders the server answer', (
    t,
  ) async {
    final h = IrrigationHarness(
      (_) async => FakeReply(200, insufficientUpperBound()),
    );
    await t.pumpWidget(
      host(
        IrrigationTodayScreen(
          api: h.api,
          role: 'worker',
          fieldsLoader: () async => [
            {'field_id': 'f1', 'name': 'حقل البُنّ', 'area_ha': 1.5},
          ],
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(
      h.posts('/api/v1/fields/f1/irrigation-recommendation'),
      hasLength(1),
    );
    expect(find.text('لا تكفي البيانات لقرار ريّ اليوم'), findsOneWidget);
    // العامل لا يملك field:edit ⇒ لا زرّ تسجيل.
    expect(find.text('سجّل ماء الريّ المضاف'), findsNothing);
  });

  testWidgets('today screen: 503 shows the honest outage message', (t) async {
    final h = IrrigationHarness(
      (_) async => const FakeReply(503, {'detail': 'x'}),
    );
    await t.pumpWidget(
      host(
        IrrigationTodayScreen(
          api: h.api,
          role: 'owner',
          fieldsLoader: () async => [
            {'field_id': 'f1', 'name': 'حقل'},
          ],
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(
      find.text('الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).'),
      findsOneWidget,
    );
  });
}
