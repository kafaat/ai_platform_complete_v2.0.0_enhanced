// خطّة الريّ الافتراضيّة: لا مدخلات مُختلَقة (ET₀/Kc/المطر مطلوبة صراحةً)،
// والنتيجة تُعرض بوحدات الخادم (مم، م³/هـ) وموسومة «غير معايَرة».
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/irrigation/presentation/plan/irrigation_plan_screen.dart';

import 'irrigation_test_helpers.dart';

void main() {
  test(
    'ET₀, Kc and rain are required — nothing is pre-filled for the user',
    () {
      expect(
        buildPlanRequest(days: '7', et0: '', kc: '1', rain: '0').error,
        contains('ET₀'),
      );
      expect(
        buildPlanRequest(days: '7', et0: '6', kc: '', rain: '0').error,
        contains('Kc'),
      );
      expect(
        buildPlanRequest(days: '7', et0: '6', kc: '1', rain: '').error,
        contains('المطر'),
      );
      expect(
        buildPlanRequest(days: '30', et0: '6', kc: '1', rain: '0').error,
        contains('14'),
      );
    },
  );

  test('Arabic digits build one forecast day per requested day', () {
    final r = buildPlanRequest(
      days: '٣',
      et0: '٥٫٥',
      kc: '١٫١',
      rain: '٠',
      texture: 'loam',
    );
    expect(r.error, isNull);
    final f = r.body!['forecast'] as List;
    expect(f, hasLength(3));
    expect(f.first, {'et0_mm': 5.5, 'kc': 1.1, 'rain_mm': 0});
    expect(r.body!['soil_texture'], 'loam');
    expect(r.body!.containsKey('root_depth_m'), isFalse);
  });

  testWidgets(
    'result renders server totals with units and the uncalibrated tag',
    (t) async {
      final h = IrrigationHarness(
        (o) async => const FakeReply(200, {
          'soil': {
            'warnings_ar': ['TAW غير معايَرة يمنيّاً'],
          },
          'taw_mm_used': 105.0,
          'quality': {
            'assumptions_ar': ['نموذج غير معايَر'],
          },
          'plan': {
            'policy': 'water_saving',
            'total_irrigation_mm': 42.0,
            'total_irrigation_m3_ha': 420.0,
            'n_events': 2,
            'stress_days': [],
            'final_depletion_mm': 20.0,
            'calibrated': false,
            'notes_ar': [],
            'days': [
              {
                'day_index': 0,
                'etc_mm': 6.0,
                'irrigation_mm': 21.0,
                'stressed': false,
              },
            ],
          },
        }),
      );
      await t.pumpWidget(host(IrrigationPlanScreen(api: h.api)));
      final fields = find.byType(TextField);
      await t.enterText(fields.at(1), '6');
      await t.enterText(fields.at(2), '1');
      await t.enterText(fields.at(3), '0');
      await t.tap(find.text('احسب الخطّة'));
      await t.pumpAndSettle();
      final post = h.posts('/api/v1/irrigation-plan').single;
      expect(post.headers[kIdempotencyHeader], isNotNull);
      expect((bodyOf(post)['forecast'] as List), hasLength(7));
      await t.scrollUntilVisible(
        find.text('420 م³/هـ'),
        200,
        scrollable: find
            .descendant(
              of: find.byType(ListView),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      expect(find.text('42 مم'), findsOneWidget);
      expect(find.text('غير معايَرة'), findsOneWidget);
    },
  );
}
