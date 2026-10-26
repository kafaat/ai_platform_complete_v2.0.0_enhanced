// شاشة الأقمار: لا فيض للشبكة عند تكبير النصّ 1.3× على 360dp، مبدّل المؤشّر
// يطلب سلسلة المؤشّر الحقيقيّ، وغياب القيمة «غير مقيس».
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/satellite/data/satellite_api.dart';
import 'package:sahool_app/features/satellite/data/satellite_models.dart';
import 'package:sahool_app/features/satellite/presentation/field_indicators_panel.dart';
import 'package:sahool_app/features/satellite/presentation/satellite_screen.dart';

import '../../core/fake_http.dart';
import '../fields/harness.dart';

const _readings = [
  IndicatorReading(id: 'ndvi', value: 0.734),
  IndicatorReading(id: 'evi', value: 0.512),
  IndicatorReading(id: 'savi', value: 0.433),
  IndicatorReading(id: 'ndmi', value: -0.121),
  IndicatorReading(id: 'msi', value: 1.234),
  IndicatorReading(id: 'ndwi', value: -0.333),
  IndicatorReading(id: 'gndvi', value: 0.611),
  IndicatorReading(id: 'lai', value: 2.5, unit: 'م²/م²', estimated: true),
  IndicatorReading(id: 'water_stress', value: null),
];

Backend backend() => Backend({
  '/api/v1/fields': (_) => ok([
    {'field_id': 'f1', 'farm_id': '', 'name_ar': 'حقل البنّ', 'crop': 'بنّ'},
    {'field_id': 'f2', 'farm_id': '', 'name_ar': 'حقل الذرة', 'crop': 'ذرة'},
  ]),
  '/api/v1/indicators/catalog': (_) => ok({
    'indicators': [
      {'id': 'ndvi', 'name_ar': 'NDVI', 'renderable': true},
      {'id': 'ndwi', 'name_ar': 'NDWI', 'renderable': true},
    ],
  }),
  '/api/vegetation/v1/analyze': (_) => ok({
    'indices': {
      'ndvi': {'value': 0.62, 'unit': 'dimensionless'},
      'ndwi': {'value': null, 'unit': 'dimensionless'},
    },
    'health': {'status': 'fair', 'label_ar': 'مقبول'},
  }),
  '/api/raster/v1/fields/f1/timeseries': (o) => ok({
    'available': true,
    'points': [
      {'datetime': '2026-09-01', 'mean': 0.5},
      {'datetime': '2026-10-01', 'mean': 0.62},
    ],
  }),
});

void main() {
  testWidgets('indicator grid does not overflow at textScale 1.3 on 360dp', (
    t,
  ) async {
    t.view.physicalSize = const Size(360, 800);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.reset);
    await t.pumpWidget(
      host(
        const SingleChildScrollView(
          child: IndicatorTilesGrid(readings: _readings, options: []),
        ),
        textScale: 1.3,
        scaffold: true,
      ),
    );
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
    expect(find.text('غير مقيس'), findsOneWidget); // water_stress بلا قيمة
    expect(find.text('dimensionless'), findsNothing);
  });

  testWidgets('screen picks the first field, index chips come from the catalog '
      'and choosing NDWI requests its series', (t) async {
    final b = backend();
    await t.pumpWidget(
      host(
        SatelliteScreen(
          api: SatelliteApi(b.client),
          fieldsApi: FieldsApi(b.client),
          role: () => AppRole.viewer,
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('حقل البنّ'), findsOneWidget);
    expect(find.byKey(const ValueKey('index_ndwi')), findsOneWidget);
    expect(find.byKey(const ValueKey('health_chip')), findsOneWidget);
    // viewer لا يملك زرّ إطلاق تحديث الصور
    expect(find.byTooltip('تحديث صور الأقمار'), findsNothing);

    await t.tap(find.byKey(const ValueKey('index_ndwi')));
    await t.pumpAndSettle();
    final series = b.to('/api/raster/v1/fields/f1/timeseries');
    expect(series.map((o) => o.queryParameters['index']), ['ndvi', 'ndwi']);
    expect(find.byKey(const ValueKey('series_empty')), findsNothing);
    expect(t.takeException(), isNull);
  });

  testWidgets('field list failure shows the typed 503 message', (t) async {
    final b = Backend({
      '/api/v1/fields': (_) => const FakeReply(503, {'detail': 'db down'}),
    });
    await t.pumpWidget(
      host(
        SatelliteScreen(
          api: SatelliteApi(b.client),
          fieldsApi: FieldsApi(b.client),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.textContaining('الخدمة غير متاحة'), findsOneWidget);
  });
}
