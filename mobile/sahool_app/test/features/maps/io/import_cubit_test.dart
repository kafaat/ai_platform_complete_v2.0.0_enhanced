// تدفّق الاستيراد: مضلّع لكلّ طلب، مفتاح ثابت لكلّ مضلّع، الثقوب لا تُرسَل، والفاشل
// يُعاد بمفتاحه ولا يُعاد الناجح.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/maps/draw/field_created_events.dart';
import 'package:sahool_app/features/maps/io/data/maps_io_api.dart';
import 'package:sahool_app/features/maps/io/presentation/import_cubit.dart';

import '../../../core/fake_http.dart';
import 'fixtures.dart';

void main() {
  late FakeAdapter adapter;
  late ImportCubit cubit;
  late FakeReply Function(int call) reply;
  var calls = 0;

  setUp(() {
    calls = 0;
    reply = (_) => const FakeReply(201, {'field_id': 'fld'});
    adapter = FakeAdapter((_) async => reply(calls++));
    cubit = ImportCubit(
      MapsIoApi(
        testClient(
          adapter,
          MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
        ),
      ),
      farmId: 'farm_1',
    );
  });

  tearDown(() => cubit.close());

  test(
    'one request per selected polygon, each with its own key; holes dropped',
    () async {
      cubit.parse(featureCollection());
      expect(cubit.state.rows, hasLength(3));
      expect(
        cubit.state.rows.first.issues.map((i) => i.code),
        contains('holes_dropped'),
      );
      cubit.toggle(2, false); // keep 2 of 3
      await cubit.submit();

      expect(adapter.requests, hasLength(2));
      final keys = adapter.requests
          .map((r) => r.headers['Idempotency-Key'])
          .toSet();
      expect(keys, hasLength(2));
      final body = adapter.requests.first.data as Map;
      expect(body['format'], 'geojson');
      expect(body['name'], 'حقل البنّ');
      expect(body['farm_id'], 'farm_1');
      expect(body['boundary_metadata']['source'], 'geojson_file');
      final sent = jsonDecode(body['content'] as String) as Map;
      expect(sent['type'], 'Polygon');
      expect((sent['coordinates'] as List), hasLength(1)); // outer ring only
      expect(cubit.state.createdCount, 2);
      expect(cubit.state.allDone, isTrue);
    },
  );

  test(
    'each created field is announced so a kept-alive list reloads',
    () async {
      final announced = <Map<String, dynamic>>[];
      final sub = FieldCreatedEvents.instance.stream.listen(announced.add);
      addTearDown(sub.cancel);
      cubit.parse(featureCollection());
      cubit.toggle(2, false);
      await cubit.submit();
      await Future<void>.delayed(Duration.zero);
      expect(announced, hasLength(2));
      expect(announced.first['field_id'], 'fld');
    },
  );

  test(
    'failed row is retried with the same key; created rows are not resent',
    () async {
      reply = (n) => n == 1
          ? const FakeReply(409, {
              'detail': {
                'message_ar': 'حدود الحقل تتداخل مع «أ»',
                'code': 'field_geometry_overlap',
              },
            })
          : const FakeReply(201, {'field_id': 'fld'});
      cubit.parse(featureCollection());
      cubit.toggle(2, false);
      await cubit.submit();
      expect(cubit.state.rows[1].status, RowStatus.failed);
      expect(cubit.state.rows[1].error, 'حدود الحقل تتداخل مع «أ»');
      final firstKey = adapter.requests[1].headers['Idempotency-Key'];

      await cubit.submit();
      expect(adapter.requests, hasLength(3)); // only the failed row
      expect(adapter.requests[2].headers['Idempotency-Key'], firstKey);
    },
  );

  test('renaming a failed row is a new intent with a new key', () async {
    reply = (n) => n == 0
        ? const FakeReply(409, {
            'detail': {
              'message_ar': 'اسم مكرّر',
              'code': 'duplicate_field_name',
            },
          })
        : const FakeReply(201, {'field_id': 'fld'});
    cubit.parse(polygonJson([square]));
    await cubit.submit();
    final k0 = adapter.requests[0].headers['Idempotency-Key'];
    cubit.rename(0, 'اسم آخر');
    await cubit.submit();
    expect(adapter.requests[1].headers['Idempotency-Key'], isNot(k0));
    expect((adapter.requests[1].data as Map)['name'], 'اسم آخر');
  });

  test(
    'duplicate or empty names block the submit without any request',
    () async {
      cubit.parse(featureCollection());
      cubit.rename(1, 'حقل البنّ');
      await cubit.submit();
      expect(cubit.state.formError, contains('مكرّر'));
      cubit.rename(1, '  ');
      await cubit.submit();
      expect(cubit.state.formError, contains('مطلوب'));
      expect(adapter.requests, isEmpty);
    },
  );

  test('a bow-tie is pre-deselected and cannot be selected', () async {
    cubit.parse(polygonJson([bowtie]));
    final row = cubit.state.rows.single;
    expect(row.blocked, isTrue);
    expect(row.selected, isFalse);
    cubit.toggle(0, true);
    expect(cubit.state.rows.single.selected, isFalse);
    await cubit.submit();
    expect(adapter.requests, isEmpty);
  });

  test('a parse error is shown, not thrown', () {
    cubit.parse('<kml></kml>');
    expect(cubit.state.parseError, isNotNull);
    expect(cubit.state.rows, isEmpty);
  });
}
