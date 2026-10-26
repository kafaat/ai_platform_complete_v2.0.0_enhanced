// IrrigationApi: المسارات والأجسام والترويسات الحقيقيّة عبر ApiClient نفسه.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import 'irrigation_test_helpers.dart';

void main() {
  test(
    'recommendation is a POST with an empty body and no idempotency key',
    () async {
      final h = IrrigationHarness(
        (_) async => const FakeReply(200, {'status': 'insufficient_data'}),
      );
      final r = await h.api.getFieldRecommendation('f1');
      expect(r['status'], 'insufficient_data');
      final req = h.posts('/api/v1/fields/f1/irrigation-recommendation').single;
      expect(bodyOf(req), isEmpty);
      expect(req.headers.containsKey(kIdempotencyHeader), isFalse);
    },
  );

  test(
    'water ledger upsert carries the intent key; list passes the date window',
    () async {
      final h = IrrigationHarness((o) async {
        if (o.method == 'GET') {
          expect(o.queryParameters, {'from': '2026-10-01', 'to': '2026-10-26'});
          return const FakeReply(200, {
            'field_id': 'f1',
            'entries': [],
            'total': 0,
          });
        }
        return const FakeReply(200, {
          'field_id': 'f1',
          'ledger_date': '2026-10-26',
          'persisted': true,
        });
      });
      await h.api.listWaterLedger('f1', from: '2026-10-01', to: '2026-10-26');
      const key = IdempotencyKey('0190f0c8-0000-7000-8000-000000000001');
      await h.api.upsertWaterLedger('f1', {
        'ledger_date': '2026-10-26',
        'irrigation_mm': 12,
      }, idempotencyKey: key);
      final post = h.posts('/api/v1/fields/f1/water-ledger').single;
      expect(post.headers[kIdempotencyHeader], key.value);
      expect(bodyOf(post)['irrigation_mm'], 12);
    },
  );

  test(
    'existing public methods keep their shape (fields reads listSchedules)',
    () async {
      final h = IrrigationHarness((o) async {
        expect(o.queryParameters, {'field_id': 'f9'});
        return const FakeReply(200, [
          {'schedule_id': 's1', 'name': 'صباح'},
        ]);
      });
      final list = await h.api.listSchedules(fieldId: 'f9');
      expect(list.single['schedule_id'], 's1');
    },
  );

  test('valve state and schedule delete send the given key', () async {
    final h = IrrigationHarness(
      (o) async => const FakeReply(200, {'valve_id': 'v1', 'status': 'open'}),
    );
    const key = IdempotencyKey('0190f0c8-0000-7000-8000-000000000002');
    await h.api.setValveState('v1', 'open', idempotencyKey: key);
    await h.api.deleteSchedule('s1', idempotencyKey: key);
    expect(h.adapter.requests.map((r) => r.headers[kIdempotencyHeader]), [
      key.value,
      key.value,
    ]);
  });
}
