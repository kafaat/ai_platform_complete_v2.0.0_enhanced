// DashboardApi: دمج الطلبات المتزامنة، الكاش مع وقت الجلب الفعليّ، والمسارات
// الحقيقيّة لطابور الأولويّات والطقس والإقرار (مع مفتاح idempotency).
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import 'today_fixtures.dart';

void main() {
  test(
    'concurrent dashboard reads share one request and fill the cache',
    () async {
      final h = TodayHarness(
        fakeBackend(delay: const Duration(milliseconds: 5)),
      );
      final results = await Future.wait([
        h.api.getDashboard(),
        h.api.getDashboard(),
        h.api.fetchDashboard().then((f) => f.data),
      ]);
      expect(h.adapter.to('/api/v1/indicators/dashboard'), hasLength(1));
      expect(results[0]['kpis'], isA<List<dynamic>>());

      // الشاشة بعد الغلاف: من الكاش، بوقت الجلب الأصليّ لا وقت القراءة.
      final first = await h.api.fetchDashboard();
      await Future<void>.delayed(const Duration(milliseconds: 5));
      final again = await h.api.fetchDashboard();
      expect(h.adapter.to('/api/v1/indicators/dashboard'), hasLength(1));
      expect(again.fetchedAt, first.fetchedAt);

      await h.api.fetchDashboard(forceRefresh: true);
      expect(h.adapter.to('/api/v1/indicators/dashboard'), hasLength(2));
    },
  );

  test('farm reads hit the real producer paths', () async {
    final h = TodayHarness(fakeBackend());
    final q = await h.api.getFarmPriorityQueue('farm1');
    expect(q['items'], hasLength(2));
    final fields = await h.api.listFarmFields('farm1');
    expect(fields.map((f) => f['field_id']), ['f1', 'f2', 'f3']);
    final w = await h.api.getWeatherSummary(15.35, 44.2);
    expect(w['sample'], isA<Map<String, dynamic>>());
    final req = h.adapter.requests.last;
    expect(req.path, '/api/v1/weather/field-weather-summary');
  });

  test('acknowledge sends PATCH with the caller idempotency key', () async {
    final h = TodayHarness(fakeBackend());
    const key = IdempotencyKey('0190f0e0-0000-7000-8000-000000000001');
    await h.api.acknowledgeAlert('alr_frost', idempotencyKey: key);
    final r = h.adapter.to('/api/v1/alerts/alr_frost/acknowledge').single;
    expect(r.method, 'PATCH');
    expect(r.headers[kIdempotencyHeader], key.value);
  });
}
