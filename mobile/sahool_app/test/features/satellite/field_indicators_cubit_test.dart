// سباق التبديل السريع بين الحقول/المؤشّرات: الردّ المتأخّر لحقل سابق لا يكتب
// فوق الحقل المختار الآن. + تحليل السلسلة الزمنيّة والكتالوج من الشكل الحقيقيّ.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/fields/presentation/common/load_cubit.dart';
import 'package:sahool_app/features/satellite/data/satellite_api.dart';
import 'package:sahool_app/features/satellite/data/satellite_models.dart';
import 'package:sahool_app/features/satellite/presentation/field_indicators_cubit.dart';

import '../fields/harness.dart';

Map<String, dynamic> analyze(double ndvi) => {
  'indices': {
    'ndvi': {
      'value': ndvi,
      'unit': 'dimensionless',
      'source': 'raster-service',
    },
  },
  'health': {'status': 'good', 'label_ar': 'جيد'},
};

Map<String, dynamic> series(double mean) => {
  'available': true,
  'points': [
    {'datetime': '2026-10-01', 'mean': mean, 'cloud_pct': 12.0},
  ],
};

double? ndviOf(FieldIndicatorsState s) => switch (s.snapshot) {
  LoadLoaded(:final data) => data.reading('ndvi')?.value,
  _ => null,
};

double? seriesOf(FieldIndicatorsState s) => switch (s.series) {
  LoadLoaded(:final data) => data.latest?.mean,
  _ => null,
};

void main() {
  test('a slow response for field A never overwrites field B', () async {
    final gates = <String, Completer<void>>{
      'A': Completer<void>(),
      'B': Completer<void>(),
    };
    final b = Backend({
      '/api/vegetation/v1/analyze': (o) async {
        final id = o.queryParameters['field_id'] as String;
        await gates[id]!.future;
        return ok(analyze(id == 'A' ? 0.11 : 0.77));
      },
      '/api/raster/v1/fields/A/timeseries': (_) async {
        await gates['A']!.future;
        return ok(series(0.1));
      },
      '/api/raster/v1/fields/B/timeseries': (_) async {
        await gates['B']!.future;
        return ok(series(0.7));
      },
    });
    final cubit = FieldIndicatorsCubit(SatelliteApi(b.client));
    final a = cubit.selectField('A');
    await Future<void>.delayed(Duration.zero);
    final bb = cubit.selectField('B');
    gates['B']!.complete();
    await bb;
    expect(cubit.state.fieldId, 'B');
    expect(ndviOf(cubit.state), 0.77);
    gates['A']!.complete(); // A يصل متأخّراً
    await a;
    expect(cubit.state.fieldId, 'B');
    expect(ndviOf(cubit.state), 0.77, reason: 'ردّ A المتأخّر يُهمَل');
    expect(seriesOf(cubit.state), 0.7);
    await cubit.close();
  });

  test(
    'switching index ignores the late series of the previous index',
    () async {
      final ndviGate = Completer<void>();
      final b = Backend({
        '/api/vegetation/v1/analyze': (_) => ok(analyze(0.5)),
        '/api/raster/v1/fields/F/timeseries': (o) async {
          if (o.queryParameters['index'] == 'ndvi') {
            await ndviGate.future;
            return ok(series(0.5));
          }
          return ok(series(0.2));
        },
      });
      final cubit = FieldIndicatorsCubit(SatelliteApi(b.client));
      final first = cubit.selectField('F');
      await Future<void>.delayed(Duration.zero);
      await cubit.selectIndex('ndwi');
      expect(seriesOf(cubit.state), 0.2);
      ndviGate.complete();
      await first;
      expect(cubit.state.index, 'ndwi');
      expect(seriesOf(cubit.state), 0.2, reason: 'سلسلة NDVI المتأخّرة تُهمَل');
      await cubit.close();
    },
  );

  test(
    'catalog keeps only renderable indices; failure keeps the fallback',
    () async {
      final b = Backend({
        '/api/v1/indicators/catalog': (_) => ok({
          'indicators': [
            {'id': 'ndvi', 'name_ar': 'NDVI', 'renderable': true},
            {'id': 'ndwi', 'name_ar': 'NDWI', 'renderable': true},
            {'id': 'et0', 'name_ar': 'ET₀', 'renderable': false},
          ],
        }),
      });
      final cubit = FieldIndicatorsCubit(SatelliteApi(b.client));
      await cubit.loadCatalog();
      expect(cubit.state.options.map((o) => o.id), ['ndvi', 'ndwi']);
      expect(cubit.state.optionsFromCatalog, isTrue);
      await cubit.close();

      final down = FieldIndicatorsCubit(SatelliteApi(Backend().client));
      await down.loadCatalog();
      expect(down.state.options, kFallbackIndexOptions);
      expect(down.state.optionsFromCatalog, isFalse);
      await down.close();
    },
  );

  test(
    'timeseries reads raster cloud_pct and drops points without a mean',
    () async {
      final b = Backend({
        '/api/raster/v1/fields/F/timeseries': (_) => ok({
          'available': true,
          'points': [
            {'datetime': '2026-10-05', 'mean': 0.4, 'cloud_pct': 70.0},
            {'datetime': '2026-09-01', 'mean': 0.3},
            {'datetime': '2026-09-15', 'mean': null},
          ],
        }),
      });
      final s = await SatelliteApi(
        b.client,
      ).getFieldIndexTimeseries('F', 'ndmi');
      expect(
        b.to('/api/raster/v1/fields/F/timeseries').single.queryParameters,
        {'index': 'ndmi'},
      );
      expect(s.points.length, 2);
      expect(s.points.first.date, DateTime.parse('2026-09-01'));
      expect(s.latest!.cloudPct, 70.0);

      final legacy = await SatelliteApi(b.client).getFieldNdviTimeseries('F');
      expect(
        legacy.first['cloudy_pct'],
        70.0,
        reason: 'كان المفتاح cloudy_pct فقط فيتعطّل فلتر الغيوم دائماً',
      );
    },
  );

  test(
    'unavailable series carries the server note, no invented points',
    () async {
      final b = Backend({
        '/api/raster/v1/fields/F/timeseries': (_) => ok({
          'available': false,
          'points': [],
          'note': 'لا COG مقصوص للحقل',
        }),
      });
      final s = await SatelliteApi(
        b.client,
      ).getFieldIndexTimeseries('F', 'ndvi');
      expect(s.available, isFalse);
      expect(s.points, isEmpty);
      expect(s.noteAr, 'لا COG مقصوص للحقل');
    },
  );
}
