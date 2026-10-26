// DashboardCubit: تحميل واحد مُدمَج، لقطة دون اتّصال بعمرها، اختيار المزرعة بلا
// سباق، إقرار التنبيه بلا إرسال مزدوج وبمفتاح ثابت للنيّة.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_snapshot_store.dart';
import 'package:sahool_app/features/dashboard/presentation/dashboard_state.dart';

import '../../core/fake_http.dart';
import 'today_fixtures.dart';

void main() {
  test(
    'concurrent loads run once; farm scope, priority and weather follow',
    () async {
      final h = TodayHarness(
        fakeBackend(delay: const Duration(milliseconds: 2)),
      );
      final c = h.cubit();
      await Future.wait([c.load(), c.load(), c.load()]);
      expect(h.adapter.to('/api/v1/indicators/dashboard'), hasLength(1));
      expect(h.adapter.to('/api/v1/tasks'), hasLength(1));
      expect(h.adapter.to('/api/v1/farms'), hasLength(1));
      final s = c.state;
      expect(s.status, DashboardStatus.ready);
      expect(s.selectedFarmId, 'farm1', reason: 'single farm auto-selected');
      expect(s.farmFieldIds, {'f1', 'f2', 'f3'});
      expect(s.priority, isA<SectionReady<dynamic>>());
      expect(s.weather, isA<SectionReady<dynamic>>());
      expect(s.fieldsByPriority.map((r) => r.field.id), ['f2', 'f3', 'f1']);
      await c.close();
    },
  );

  test('offline launch shows the saved snapshot with its age', () async {
    final store = MemoryDashboardSnapshotStore();
    final online = TodayHarness(fakeBackend(), snapshots: store);
    final c1 = online.cubit();
    await c1.load();
    final savedAt = c1.state.fetchedAt!;
    await c1.close();

    final down = TodayHarness(
      fakeBackend(
        overrides: {
          '/api/v1/indicators/dashboard': offline,
          '/api/v1/tasks': offline,
          '/api/v1/farms': offline,
        },
      ),
      snapshots: store,
    );
    final c2 = down.cubit();
    await c2.load();
    final s = c2.state;
    expect(s.status, DashboardStatus.ready);
    expect(s.fromSnapshot, isTrue);
    expect(s.isStale, isTrue);
    expect(s.fetchedAt, savedAt);
    expect(s.refreshError?.kind, ApiErrorKind.network);
    expect(s.fields, hasLength(3));
    final tasks = s.tasks as SectionReady;
    expect(tasks.fromSnapshot, isTrue);
    await c2.close();
  });

  test(
    'offline with no snapshot fails honestly; 403 never shows a snapshot',
    () async {
      final h = TodayHarness(
        fakeBackend(overrides: {'/api/v1/indicators/dashboard': offline}),
      );
      final c = h.cubit();
      await c.load();
      expect(c.state.status, DashboardStatus.failed);
      expect(c.state.error?.kind, ApiErrorKind.network);
      await c.close();

      final store = MemoryDashboardSnapshotStore();
      await store.write('dashboard:tenant:user', {
        'dashboard': realDashboard(),
      }, kNow);
      final denied = TodayHarness(
        fakeBackend(
          overrides: {
            '/api/v1/indicators/dashboard': () =>
                const FakeReply(403, {'detail': 'forbidden'}),
          },
        ),
        snapshots: store,
      );
      final c2 = denied.cubit();
      await c2.load();
      expect(c2.state.status, DashboardStatus.failed);
      expect(c2.state.error?.kind, ApiErrorKind.forbidden);
      await c2.close();
    },
  );

  test('a failed refresh keeps what is shown and marks it stale', () async {
    var down = false;
    final h = TodayHarness(
      fakeBackend(
        overrides: {
          '/api/v1/indicators/dashboard': () =>
              down ? _offlineReply() : FakeReply(200, realDashboard()),
        },
      ),
    );
    final c = h.cubit();
    await c.load();
    down = true;
    await c.refresh();
    expect(c.state.status, DashboardStatus.ready);
    expect(c.state.fields, hasLength(3));
    expect(c.state.refreshError?.kind, ApiErrorKind.network);
    expect(c.state.fromSnapshot, isFalse);
    await c.close();
  });

  test(
    'a slow reply for a previous farm cannot overwrite the current one',
    () async {
      final slow = Completer<void>();
      final adapter = FakeAdapter((o) async {
        switch (o.path) {
          case '/api/v1/indicators/dashboard':
            return FakeReply(200, realDashboard());
          case '/api/v1/tasks':
            return FakeReply(200, realTasks());
          case '/api/v1/farms':
            return FakeReply(200, [
              ...realFarms(),
              {'farm_id': 'farm2', 'name': 'مزرعة الجبل'},
            ]);
          case '/api/v1/farms/farm1/fields':
            await slow.future;
            return const FakeReply(200, [
              {'field_id': 'f1'},
            ]);
          case '/api/v1/farms/farm1/priority-queue':
            await slow.future;
            return FakeReply(200, realPriorityQueue());
          case '/api/v1/farms/farm2/fields':
            return const FakeReply(200, [
              {'field_id': 'f3'},
            ]);
          case '/api/v1/farms/farm2/priority-queue':
            return const FakeReply(200, {'items': <dynamic>[]});
          default:
            return const FakeReply(404, {'detail': 'x'});
        }
      });
      final h = TodayHarness(adapter);
      final c = h.cubit();
      await c.load();
      expect(c.state.selectedFarmId, isNull, reason: 'two farms: all farms');
      final first = c.selectFarm('farm1');
      await c.selectFarm('farm2');
      slow.complete();
      await first;
      expect(c.state.selectedFarmId, 'farm2');
      expect(c.state.farmFieldIds, {'f3'});
      expect(c.state.visibleAlerts, isEmpty);
      await c.close();
    },
  );

  test('acknowledge: one request while busy, same key on retry', () async {
    var fail = true;
    final h = TodayHarness(
      fakeBackend(
        delay: const Duration(milliseconds: 2),
        overrides: {
          '/api/v1/alerts/alr_frost/acknowledge': () => fail
              ? const FakeReply(503, {'detail': 'db down'})
              : const FakeReply(200, {}),
        },
      ),
    );
    final c = h.cubit();
    await c.load();
    final r = await Future.wait([
      c.acknowledge('alr_frost'),
      c.acknowledge('alr_frost'),
    ]);
    expect(r.first?.kind, ApiErrorKind.unavailable);
    expect(r.last, isNull, reason: 'second tap ignored while busy');
    final firstKeys = h.adapter
        .to('/api/v1/alerts/alr_frost/acknowledge')
        .map((x) => x.headers[kIdempotencyHeader])
        .toSet();
    expect(firstKeys, hasLength(1));

    fail = false;
    expect(await c.acknowledge('alr_frost'), isNull);
    final keys = h.adapter
        .to('/api/v1/alerts/alr_frost/acknowledge')
        .map((x) => x.headers[kIdempotencyHeader])
        .toSet();
    expect(keys, firstKeys, reason: 'same intent, same key');
    expect(c.state.alerts.any((a) => a.id == 'alr_frost'), isFalse);
    await c.close();
  });

  test('a realtime alert event triggers one forced refresh', () async {
    final events = StreamController<Object?>();
    final h = TodayHarness(fakeBackend());
    final c = h.cubit(events: events.stream);
    await c.load();
    events
      ..add('alert')
      ..add('alert');
    await Future<void>.delayed(const Duration(milliseconds: 60));
    expect(h.adapter.to('/api/v1/indicators/dashboard'), hasLength(2));
    await c.close();
    await events.close();
  });
}

FakeReply _offlineReply() =>
    const FakeReply.fail(DioExceptionType.connectionError);
