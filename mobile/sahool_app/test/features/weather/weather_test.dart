// الطقس: التنسيق والوحدات، حالات الأقسام المستقلّة، «لا بيانات طقس» الصادقة،
// التوقّعات عند textScale 1.3، وشريط الطقس العامّ.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/features/weather/data/weather_api.dart';
import 'package:sahool_app/features/weather/data/weather_models.dart';
import 'package:sahool_app/features/weather/presentation/weather_cubit.dart';
import 'package:sahool_app/features/weather/presentation/weather_format.dart';
import 'package:sahool_app/features/weather/presentation/weather_screen.dart';
import 'package:sahool_app/features/weather/presentation/weather_strip.dart';

import '../../core/fake_http.dart';
import '../alerts/alerts_fakes.dart';

WeatherApi apiWith(FakeAdapter a) => WeatherApi(
  testClient(
    a,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  ),
);

final _days = [
  for (var i = 0; i < 7; i++)
    {
      'date': DateTime(2026, 10, 26 + i).toIso8601String().substring(0, 10),
      'temp_max_c': 31.4 + i,
      'temp_min_c': 18.2,
      'precipitation_mm': i == 2 ? 12.5 : 0.0,
      'et0_mm': 5.1,
      'wind_max_ms': 5.0,
      'wind_max_kmh': 18.0,
      'weather_code': i == 2 ? 63 : 0,
    },
];

Map<String, FakeReply Function(dynamic)> fullField({Object? lat = 15.35}) => {
  'GET /api/v1/fields/f1': (_) => FakeReply(200, {
    'field_id': 'f1',
    'name_ar': 'حقل الوادي',
    'crop': 'tomato',
    'lat': lat,
    'lon': 44.2,
  }),
  'GET /api/v1/weather/current': (_) => const FakeReply(200, {
    'temperature_c': 29.6,
    'humidity_pct': 41,
    'wind_speed_10m_kmh': 14.4,
    'precipitation_mm': 0.0,
    'weather_code': 1,
    'quality_status': 'validated',
    'missing_fields': [],
  }),
  'GET /api/v1/weather/forecast': (_) =>
      FakeReply(200, {'days': _days, 'quality_status': 'validated'}),
  'GET /api/v1/weather/alerts': (_) => const FakeReply(200, {
    'alerts': [
      {
        'type': 'strong_wind',
        'severity': 'warning',
        'title_ar': 'رياح قويّة',
        'detail_ar': 'أجّل الرشّ',
      },
    ],
  }),
  'GET /api/v1/fields/f1/weather/operation-windows': (_) =>
      const FakeReply(200, {
        'field_id': 'f1',
        'windows': [
          {
            'operation': 'irrigation',
            'start_at': null,
            'start_offset_hours': 6,
            'suitability': 'acceptable',
            'score': 0.6,
            'limiting_factors': ['high_vpd_irrigation_need'],
            'advice_ar': 'أولوية ري مرتفعة',
            'recommended': true,
          },
          {
            'operation': 'spraying',
            'start_at': null,
            'start_offset_hours': 0,
            'suitability': 'unsafe',
            'score': 0.1,
            'limiting_factors': ['wind_speed_high'],
            'advice_ar': 'تأجيل الرش أفضل',
            'recommended': false,
          },
        ],
        'degraded': false,
      }),
  'GET /api/v1/fields/f1/weather/irrigation-advice': (_) =>
      const FakeReply(422, {
        'detail': {
          'code': 'FIELD_GROWTH_STAGE_UNAVAILABLE',
          'message_ar': 'يلزم موسم وتاريخ زراعة صالحان لحساب احتياج الري.',
        },
      }),
  'GET /api/v1/fields/f1/weather/disease-risk': (_) => const FakeReply(200, {
    'risk_level': 'moderate',
    'diseases_ar': ['البياض الدقيقيّ (Powdery mildew)'],
    'advice_ar': 'راقب الحقل',
    'temperature_c': 29.6,
    'humidity_pct': 41,
    'rain_mm_3d': 12.5,
  }),
  'GET /api/v1/fields/f1/weather/thermal-stress': (_) =>
      const FakeReply(200, {'status': 'insufficient_context', 'risk': null}),
  'GET /api/v1/fields/f1/weather/crop-stress': (_) =>
      const FakeReply(503, {'detail': 'تعذّر جلب منتجات إجهاد المحصول'}),
};

void main() {
  group('formatting', () {
    test('Arabic day names, today/tomorrow', () {
      final now = DateTime(2026, 10, 26, 9); // Monday
      expect(arabicWeekday(DateTime(2026, 10, 26)), 'الاثنين');
      expect(arabicWeekday(DateTime(2026, 11, 1)), 'الأحد');
      expect(fmtDayName(DateTime(2026, 10, 26), now: now), 'اليوم');
      expect(fmtDayName(DateTime(2026, 10, 27), now: now), 'غداً');
      expect(fmtDayName(DateTime(2026, 10, 30), now: now), 'الجمعة');
      expect(fmtDayName(null), '—');
    });

    test('units °م / مم / كم/س / س, null is «غير مقيس»', () {
      expect(fmtTempC(31.4), '31 °م');
      expect(fmtMm(12.5), '12.5 مم');
      expect(fmtKmh(14.4), '14 كم/س');
      expect(fmtHoursShort(6), '6 س');
      expect(fmtKmh(null), kNotMeasured);
      expect(fmtWindowStart(null, 0), 'الآن');
      expect(fmtWindowStart(null, 6), 'بعد 6 س');
      expect(fmtWindowStart(null, null), 'الموعد غير متاح');
    });

    test('wind falls back from m/s ×3.6 and zero rain stays zero', () {
      final d = ForecastDay.fromJson({
        'wind_max_ms': 5.0,
        'precipitation_mm': 0.0,
        'temp_max_c': null,
      });
      expect(d.windMaxKmh, closeTo(18.0, 1e-9));
      expect(d.precipitationMm, 0.0);
      expect(d.tempMaxC, isNull);
      expect(fmtTempC(d.tempMaxC), kNotMeasured);
    });
  });

  group('cubit', () {
    test('sections fail independently; 422 detail map is readable', () async {
      final a = routes(fullField());
      final c = WeatherCubit(apiWith(a), 'f1');
      await c.load();
      final s = c.state;
      expect(s.current.data!.temperatureC, 29.6);
      expect(s.forecast.data!.days, hasLength(7));
      expect(s.windows.data!.of('spraying')!.suitability, 'unsafe');
      expect(s.irrigation.status, SectionStatus.failed);
      expect(
        weatherErrorText(s.irrigation.error!),
        'يلزم موسم وتاريخ زراعة صالحان لحساب احتياج الري.',
      );
      expect(s.cropStress.status, SectionStatus.failed);
      expect(s.disease.data!.riskLevel, 'moderate');
      // نقاط lat/lon تُستدعى بإحداثيّات الحقل نفسه.
      expect(a.to('/api/v1/weather/current'), hasLength(1));
      await c.close();
    });

    test(
      'field without coordinates ⇒ no weather requests by lat/lon',
      () async {
        final a = routes(fullField(lat: null));
        final c = WeatherCubit(apiWith(a), 'f1');
        await c.load();
        expect(c.state.noCoordinates, isTrue);
        expect(c.state.current.status, SectionStatus.unavailable);
        expect(a.to('/api/v1/weather/current'), isEmpty);
        expect(a.to('/api/v1/weather/forecast'), isEmpty);
        await c.close();
      },
    );

    test(
      'a current reading with no values is «unavailable», not zeros',
      () async {
        final table = fullField()
          ..['GET /api/v1/weather/current'] = (_) => const FakeReply(200, {
            'temperature_c': null,
            'missing_fields': ['temperature_c'],
          });
        final c = WeatherCubit(apiWith(routes(table)), 'f1');
        await c.load();
        expect(c.state.current.status, SectionStatus.unavailable);
        await c.close();
      },
    );
  });

  group('screen', () {
    testWidgets('field weather renders units, windows, honest failures', (
      t,
    ) async {
      final a = routes(fullField());
      await t.pumpWidget(arHost(WeatherScreen(fieldId: 'f1', api: apiWith(a))));
      await t.pumpAndSettle();
      expect(find.text('طقس حقل الوادي'), findsOneWidget);
      expect(find.text('الطقس الآن'), findsOneWidget);
      expect(find.text('°م'), findsWidgets);
      expect(find.text('كم/س'), findsOneWidget);
      expect(find.text('رياح قويّة'), findsOneWidget);
      await t.scrollUntilVisible(
        find.text('الرشّ'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('غير آمنة'), findsOneWidget);
      expect(find.text('العوائق: رياح قويّة'), findsOneWidget);
      await t.scrollUntilVisible(
        find.text('يلزم موسم وتاريخ زراعة صالحان لحساب احتياج الري.'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await t.scrollUntilVisible(
        find.textContaining('يلزم محصول ومرحلة نموّ'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
    });

    testWidgets('no coordinates ⇒ «لا بيانات طقس لهذا الحقل»', (t) async {
      final a = routes(fullField(lat: null));
      await t.pumpWidget(arHost(WeatherScreen(fieldId: 'f1', api: apiWith(a))));
      await t.pumpAndSettle();
      expect(find.text('لا بيانات طقس لهذا الحقل'), findsOneWidget);
      expect(find.text(kNoCoordinatesReason), findsOneWidget);
    });

    testWidgets('unknown field ⇒ 404 wording, no retry', (t) async {
      final a = routes({});
      await t.pumpWidget(arHost(WeatherScreen(fieldId: 'f1', api: apiWith(a))));
      await t.pumpAndSettle();
      expect(find.text('العنصر غير موجود.'), findsOneWidget);
      expect(find.text('إعادة المحاولة'), findsNothing);
    });

    testWidgets('forecast rows survive textScale 1.3 on a narrow phone', (
      t,
    ) async {
      t.view.physicalSize = const Size(360, 640);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.reset);
      final days = WeatherForecast.fromJson({'days': _days}).days;
      await t.pumpWidget(
        arHost(
          Scaffold(
            body: ListView(
              children: [
                for (final d in days)
                  ForecastDayRow(day: d, now: DateTime(2026, 10, 26)),
              ],
            ),
          ),
          textScale: 1.3,
        ),
      );
      await t.pumpAndSettle();
      expect(t.takeException(), isNull, reason: 'no RenderFlex overflow');
      expect(find.text('اليوم'), findsOneWidget);
      expect(find.text('غداً'), findsOneWidget);
      expect(find.text('الأربعاء'), findsOneWidget);
      expect(find.text('مطر 12.5 مم'), findsOneWidget);
      expect(find.text('رياح 18 كم/س'), findsWidgets);
      expect(find.text('العظمى 31 °م'), findsOneWidget);
    });

    testWidgets('field picker marks fields without coordinates', (t) async {
      await t.pumpWidget(
        arHost(
          WeatherScreen(
            api: apiWith(routes({})),
            loadFields: () async => [
              {'field_id': 'f1', 'name_ar': 'حقل أ', 'lat': 15.0, 'lon': 44.0},
              {'field_id': 'f2', 'name_ar': 'حقل ب', 'lat': null, 'lon': null},
            ],
          ),
        ),
      );
      await t.pumpAndSettle();
      expect(find.text('حقل أ'), findsOneWidget);
      expect(find.text('لا بيانات طقس لهذا الحقل'), findsOneWidget);
    });
  });

  group('WeatherStrip (public)', () {
    testWidgets('compact readings with units', (t) async {
      final a = routes(fullField());
      await t.pumpWidget(
        arHost(
          Scaffold(
            body: WeatherStrip(fieldId: 'f1', api: apiWith(a), onTap: () {}),
          ),
        ),
      );
      await t.pumpAndSettle();
      expect(find.text('30 °م'), findsOneWidget);
      expect(find.text('41٪'), findsOneWidget);
      expect(find.text('14 كم/س'), findsOneWidget);
      expect(find.text('0 مم'), findsOneWidget);
      expect(find.text('31 °م / 18 °م'), findsOneWidget);
    });

    testWidgets('no coordinates ⇒ honest text, no numbers', (t) async {
      final a = routes(fullField(lat: null));
      await t.pumpWidget(
        arHost(
          Scaffold(
            body: WeatherStrip(fieldId: 'f1', api: apiWith(a), onTap: () {}),
          ),
        ),
      );
      await t.pumpAndSettle();
      expect(find.text('لا بيانات طقس لهذا الحقل'), findsOneWidget);
      expect(find.textContaining('°م'), findsNothing);
    });

    testWidgets('503 ⇒ error wording with retry', (t) async {
      final table = fullField()
        ..['GET /api/v1/weather/current'] = (_) =>
            const FakeReply(503, {'detail': 'x'});
      await t.pumpWidget(
        arHost(
          Scaffold(
            body: WeatherStrip(
              fieldId: 'f1',
              api: apiWith(routes(table)),
              onTap: () {},
            ),
          ),
        ),
      );
      await t.pumpAndSettle();
      expect(find.textContaining('تعذّر جلب الطقس'), findsOneWidget);
      expect(find.byTooltip('إعادة المحاولة'), findsOneWidget);
    });
  });
}
