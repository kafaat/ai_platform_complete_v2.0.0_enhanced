// شكل طلبات الاستيراد/المعاينة/الالتزام وترويسة Idempotency على الطلبات الحقيقيّة
// (ApiClient الحقيقيّ عبر FakeAdapter).
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/maps/io/data/maps_io_api.dart';

import '../../../core/fake_http.dart';

void main() {
  late FakeAdapter adapter;
  late MapsIoApi api;
  var replies = <FakeReply>[];

  setUp(() {
    replies = [];
    adapter = FakeAdapter(
      (_) async => replies.isNotEmpty
          ? replies.removeAt(0)
          : const FakeReply(201, {'field_id': 'fld_1'}),
    );
    api = MapsIoApi(
      testClient(
        adapter,
        MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
      ),
    );
  });

  test(
    'gps import: format, [lon,lat] points, name, farm, metadata, key',
    () async {
      final key = IdempotencyKey.generate();
      final r = await api.importBoundary(
        format: 'gps',
        points: [
          [44.2, 15.35],
          [44.201, 15.35],
          [44.201, 15.351],
        ],
        name: 'حقل المشي',
        farmId: 'farm_9',
        idempotencyKey: key,
        boundaryMetadata: {'source': 'gps_walk'},
      );
      expect(r['field_id'], 'fld_1');
      final req = adapter.requests.single;
      expect(req.method, 'POST');
      expect(req.path, '/api/v1/fields/import');
      expect(req.headers['Idempotency-Key'], key.value);
      expect(req.data, {
        'format': 'gps',
        'name': 'حقل المشي',
        'points': [
          [44.2, 15.35],
          [44.201, 15.35],
          [44.201, 15.351],
        ],
        'farm_id': 'farm_9',
        'boundary_metadata': {'source': 'gps_walk'},
      });
    },
  );

  test(
    'a 503 on import is retried with the SAME key (no duplicate field)',
    () async {
      replies = [
        const FakeReply(503, {'detail': 'db'}),
      ];
      final key = IdempotencyKey.generate();
      await api.importBoundary(
        format: 'geojson',
        content: '{}',
        name: 'x',
        idempotencyKey: key,
      );
      expect(adapter.requests, hasLength(2));
      expect(
        adapter.requests.map((r) => r.headers['Idempotency-Key']).toSet(),
        {key.value},
      );
    },
  );

  test(
    'previews are dry-run bodies without a key; 404 surfaces as notFound',
    () async {
      replies = [
        const FakeReply(200, {'operation': 'union', 'result': {}}),
        const FakeReply(404, {'detail': 'نواة GIS غير مُفعَّلة'}),
      ];
      await api.previewUnion('a', 'b');
      expect(adapter.requests.last.path, '/api/v1/gis/union');
      expect(adapter.requests.last.data, {
        'field_id_a': 'a',
        'field_id_b': 'b',
      });
      expect(
        adapter.requests.last.headers.containsKey('Idempotency-Key'),
        isFalse,
      );
      await expectLater(
        api.previewSplit('a', {
          'type': 'LineString',
          'coordinates': [
            [44, 15],
            [44.1, 15],
          ],
        }),
        throwsA(
          isA<ApiException>().having(
            (e) => e.kind,
            'kind',
            ApiErrorKind.notFound,
          ),
        ),
      );
      expect(
        (adapter.requests.last.data as Map)['blade']['type'],
        'LineString',
      );
    },
  );

  test(
    'merge and split commit bodies match FieldMergeRequest/FieldSplitRequest',
    () async {
      replies = [
        const FakeReply(201, {'field_id': 'm'}),
        const FakeReply(201, [
          {'field_id': 'c1'},
          {'field_id': 'c2'},
        ]),
      ];
      final g = {'type': 'Polygon', 'coordinates': []};
      final k1 = IdempotencyKey.generate();
      await api.mergeFields(
        sourceFieldIds: ['a', 'b'],
        name: 'م',
        geometry: g,
        farmId: 'f',
        idempotencyKey: k1,
      );
      expect(adapter.requests.last.path, '/api/v1/fields/merge');
      expect(adapter.requests.last.data, {
        'source_field_ids': ['a', 'b'],
        'name': 'م',
        'geometry': g,
        'farm_id': 'f',
      });
      expect(adapter.requests.last.headers['Idempotency-Key'], k1.value);

      final k2 = IdempotencyKey.generate();
      final out = await api.splitField(
        sourceFieldId: 'a',
        children: [(name: '1', geometry: g), (name: '2', geometry: g)],
        idempotencyKey: k2,
        inheritCrop: 'coffee',
      );
      expect(out, hasLength(2));
      expect(adapter.requests.last.path, '/api/v1/fields/split');
      expect(adapter.requests.last.data, {
        'source_field_id': 'a',
        'children': [
          {'name': '1', 'geometry': g, 'crop': 'coffee'},
          {'name': '2', 'geometry': g, 'crop': 'coffee'},
        ],
      });
      expect(adapter.requests.last.headers['Idempotency-Key'], k2.value);
    },
  );
}
