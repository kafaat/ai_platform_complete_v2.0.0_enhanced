// الحفظ عبر ApiClient الحقيقيّ ومحوّل HTTP مزيّف: الترويسات والجسم كما تُرسَل.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/maps/draw/field_create_api.dart';
import 'package:sahool_app/features/maps/draw/field_create_errors.dart';
import 'package:sahool_app/features/maps/draw/field_created_events.dart';
import 'package:sahool_app/features/maps/draw/field_save_cubit.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';

import '../../../core/fake_http.dart';
import '../../offline_sync/operation_test_support.dart';

const _geometry = {
  'type': 'Polygon',
  'coordinates': [
    [
      [44.2, 15.35],
      [44.21, 15.35],
      [44.21, 15.36],
      [44.2, 15.35],
    ],
  ],
};

const _created = {
  'field_id': 'fld_1',
  'name_ar': 'الحقل الشرقيّ',
  'area_ha': 59.9,
  'farm_id': 'farm_1',
};

FieldSaveCubit _cubit(FakeAdapter adapter, {ResponseCache? cache}) {
  final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
  final client = testClient(adapter, tokens);
  return FieldSaveCubit(
    createApi: FieldCreateApi(client),
    fieldsApi: FieldsApi(client),
    cache: cache ?? ResponseCache(),
    ledger: ledgerFor(tokens, MemoryOperationStore(), client: client),
  );
}

const _draft = FieldCreateDraft(
  name: 'الحقل الشرقيّ',
  geometry: _geometry,
  farmId: 'farm_1',
  crop: 'wheat',
  irrigationType: 'drip',
  boundarySource: 'manual',
);

void main() {
  test(
    'a timeout leaves the outcome unknown; saving the same draft recovers '
    'with the same Idempotency-Key',
    () async {
      var calls = 0;
      final adapter = FakeAdapter((o) async {
        if (o.path == '/api/v1/fields') {
          calls++;
          return calls == 1
              ? const FakeReply.fail(DioExceptionType.receiveTimeout)
              : const FakeReply(201, _created);
        }
        return const FakeReply(404, {'detail': 'x'});
      });
      final cubit = _cubit(adapter);

      await cubit.save(_draft);
      final u = cubit.state as FieldSaveUnconfirmed;
      expect(u.outcome.messageAr, kOperationUnknownAr);

      await cubit.save(_draft);
      expect(cubit.state, isA<FieldSaveDone>());
      expect((cubit.state as FieldSaveDone).fieldId, 'fld_1');

      final posts = adapter.to('/api/v1/fields');
      expect(posts, hasLength(2));
      final k1 = posts[0].headers['Idempotency-Key'];
      final k2 = posts[1].headers['Idempotency-Key'];
      expect(k1, isA<String>());
      expect(k1, isNotEmpty);
      expect(k2, k1, reason: 'المفتاح ثابت للنيّة كي يعيد الخادم الحقل نفسه');
      await cubit.close();
    },
  );

  test(
    'UI-M3 (D1): an edited draft after an unknown outcome is NOT sent and '
    'does NOT mint a new key; recovery returns the committed field and '
    'shows the edit',
    () async {
      // دلالة `_idempotent` لـfield.create: مفتاح معروف ⇒ النتيجة المخزّنة.
      final committed = <String, Map<String, dynamic>>{};
      var calls = 0;
      final adapter = FakeAdapter((o) async {
        if (o.path != '/api/v1/fields') {
          return const FakeReply(404, {'detail': 'x'});
        }
        calls++;
        final key = o.headers['Idempotency-Key'] as String;
        final body = o.data as Map;
        final result = committed.putIfAbsent(
          key,
          () => {'field_id': 'fld_${committed.length + 1}', 'name_ar': body['name']},
        );
        // أوّل محاولة: التزم الخادم لكن ضاع الردّ (نتيجة مجهولة).
        return calls == 1
            ? const FakeReply.fail(DioExceptionType.receiveTimeout)
            : FakeReply(201, result);
      });
      final cubit = _cubit(adapter);

      await cubit.save(_draft);
      expect(cubit.state, isA<FieldSaveUnconfirmed>());
      // عدّل المستخدم الاسم ثمّ أعاد الحفظ ⇒ مسودّة فقط، لا طلب، لا مفتاح جديد.
      const edited = FieldCreateDraft(
        name: 'الحقل الغربيّ',
        geometry: _geometry,
        farmId: 'farm_1',
        crop: 'wheat',
        irrigationType: 'drip',
        boundarySource: 'manual',
      );
      await cubit.save(edited);
      expect(adapter.to('/api/v1/fields'), hasLength(1));
      expect(cubit.state, isA<FieldSaveUnconfirmed>());

      await cubit.recover(draft: edited);
      final keys = adapter
          .to('/api/v1/fields')
          .map((r) => r.headers['Idempotency-Key'])
          .toSet();
      expect(keys, hasLength(1), reason: 'لا مفتاح جديد');
      expect(committed, hasLength(1), reason: 'حقل واحد على الخادم');
      final done = cubit.state as FieldSaveDone;
      expect(done.field['name_ar'], 'الحقل الشرقيّ');
      expect(done.pendingEdits.single.key, 'name');
      expect(done.pendingEdits.single.after, 'الحقل الغربيّ');
      await cubit.close();
    },
  );

  test(
    'create body carries farm_id, irrigation_type and boundary metadata',
    () async {
      final adapter = FakeAdapter(
        (o) async => o.path == '/api/v1/fields'
            ? const FakeReply(201, _created)
            : const FakeReply(201, {}),
      );
      final cubit = _cubit(adapter);
      await cubit.save(_draft);
      final body = adapter.to('/api/v1/fields').single.data as Map;
      expect(body['farm_id'], 'farm_1');
      expect(body['irrigation_type'], 'drip');
      expect(body['crop'], 'wheat');
      expect(body['geometry'], _geometry);
      expect(body['boundary_metadata'], {'source': 'manual', 'mode': 'mobile'});
      expect(body.containsKey('pivot'), isFalse);
      // لا PATCH ثانٍ لنوع الريّ.
      expect(adapter.requests.where((r) => r.method == 'PATCH'), isEmpty);
      await cubit.close();
    },
  );

  test('pivot forces irrigation_type=pivot so the server canonicalises it', () {
    const draft = FieldCreateDraft(
      name: 'محور',
      geometry: _geometry,
      irrigationType: 'drip',
      pivot: {
        'center': {'lon': 44.2, 'lat': 15.35},
        'radius_m': 400.0,
      },
    );
    final j = draft.toJson();
    expect(j['irrigation_type'], 'pivot');
    expect(j['pivot'], isA<Map>());
  });

  test('a double tap sends one request', () async {
    final adapter = FakeAdapter((o) async {
      await Future<void>.delayed(const Duration(milliseconds: 20));
      return const FakeReply(201, _created);
    });
    final cubit = _cubit(adapter);
    await Future.wait([cubit.save(_draft), cubit.save(_draft)]);
    expect(adapter.to('/api/v1/fields'), hasLength(1));
    await cubit.close();
  });

  test(
    '409 duplicate name shows the server message and points to step 1',
    () async {
      final adapter = FakeAdapter(
        (o) async => const FakeReply(409, {
          'detail': {
            'message_ar':
                'يوجد حقل بالاسم نفسه «الحقل الشرقيّ» في هذه المزرعة.',
            'code': 'duplicate_field_name',
          },
        }),
      );
      final cubit = _cubit(adapter);
      await cubit.save(_draft);
      final s = cubit.state as FieldSaveFailed;
      expect(s.view.fixStep, FixStep.basics);
      expect(s.view.messageAr, contains('بالاسم نفسه'));
      expect(s.view.retrySafe, isFalse);
      await cubit.close();
    },
  );

  test(
    '409 overlap lists the overlapping fields and points to the boundary',
    () {
      final v = describeCreateError(
        DioException(
          requestOptions: RequestOptions(path: '/api/v1/fields'),
          type: DioExceptionType.badResponse,
          response: Response(
            requestOptions: RequestOptions(path: '/api/v1/fields'),
            statusCode: 409,
            data: {
              'detail': {
                'message_ar':
                    'حدود الحقل تتداخل مع «أ» (~120 م²). صحّح الحدود.',
                'code': 'field_geometry_overlap',
                'overlaps': [
                  {'field_id': 'x', 'name': 'أ', 'overlap_m2': 120.0},
                ],
              },
            },
          ),
        ),
      );
      expect(v.fixStep, FixStep.boundary);
      expect(v.messageAr, contains('«أ» (~120.0 م²)'));
    },
  );

  test(
    'after creation: cache cleared, listeners told, season created',
    () async {
      final cache = ResponseCache()..set('dashboard:t:u', {'fields': 0});
      final events = <Map<String, dynamic>>[];
      final sub = FieldCreatedEvents.instance.stream.listen(events.add);
      final adapter = FakeAdapter((o) async {
        if (o.path == '/api/v1/fields') return const FakeReply(201, _created);
        if (o.path.endsWith('/seasons')) {
          return const FakeReply(201, {'season_id': 's'});
        }
        return const FakeReply(200, {'field_id': 'fld_1', 'warnings': []});
      });
      final cubit = _cubit(adapter, cache: cache);
      await cubit.save(_draft, seasonCrop: 'wheat', sowingDate: '2026-11-01');
      await Future<void>.delayed(Duration.zero);

      expect(cache.get('dashboard:t:u'), isNull);
      expect(events.single['field_id'], 'fld_1');
      final season = adapter.to('/api/v1/fields/fld_1/seasons').single;
      expect((season.data as Map)['crops'], ['wheat']);
      expect((season.data as Map)['sowing_date'], '2026-11-01');
      expect(season.headers['Idempotency-Key'], isNotNull);
      final done = cubit.state as FieldSaveDone;
      // الخادم لم يردّ رقماً ⇒ لا خطوة تقدير.
      expect(done.yieldEstimate, isNull);
      expect(done.seasonWarning, isNull);
      await sub.cancel();
      await cubit.close();
    },
  );

  test(
    'yield estimate is kept only when the server returns a number',
    () async {
      final adapter = FakeAdapter((o) async {
        if (o.path == '/api/v1/fields') return const FakeReply(201, _created);
        if (o.path.endsWith('/seasons')) return const FakeReply(201, {});
        return const FakeReply(200, {
          'estimated_yield_kg_ha': 2850.0,
          'confidence': 'low',
        });
      });
      final cubit = _cubit(adapter);
      await cubit.save(_draft, seasonCrop: 'wheat');
      final done = cubit.state as FieldSaveDone;
      expect(done.yieldEstimate!['estimated_yield_kg_ha'], 2850.0);
      await cubit.close();
    },
  );

  test('a failed season does not recreate the field and is reported', () async {
    final adapter = FakeAdapter((o) async {
      if (o.path == '/api/v1/fields') return const FakeReply(201, _created);
      if (o.path.endsWith('/seasons')) {
        return const FakeReply(503, {'detail': 'db down'});
      }
      return const FakeReply(503, {'detail': 'db down'});
    });
    final cubit = _cubit(adapter);
    await cubit.save(_draft, seasonCrop: 'wheat');
    final done = cubit.state as FieldSaveDone;
    expect(done.seasonWarning, contains('تعذّر إنشاء الموسم'));
    expect(adapter.to('/api/v1/fields'), hasLength(1));
    await cubit.close();
  });
}
