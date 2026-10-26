// صندوق التنبيهات: التحميل، الإقرار بمفتاح ثابت، والإدراج الحيّ من القناة.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/alerts/data/alert_live_events.dart';
import 'package:sahool_app/features/alerts/data/alert_models.dart';
import 'package:sahool_app/features/alerts/data/alerts_api.dart';
import 'package:sahool_app/features/alerts/data/alerts_unread.dart';
import 'package:sahool_app/features/alerts/presentation/alerts_cubit.dart';
import 'package:sahool_app/services/websocket_service.dart';

import '../../core/fake_http.dart';
import 'alerts_fakes.dart';

AlertsApi apiWith(FakeAdapter a) => AlertsApi(
  testClient(
    a,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  ),
);

Future<void> settle() => Future<void>.delayed(const Duration(milliseconds: 20));

void main() {
  late StreamController<WsEvent> ws;
  setUp(() => ws = StreamController<WsEvent>.broadcast());
  tearDown(() => ws.close());

  AlertsCubit cubitWith(FakeAdapter a, {String? fieldId}) {
    final api = apiWith(a);
    return AlertsCubit(
      api,
      fieldId: fieldId,
      events: ws.stream,
      counter: AlertsUnreadCounter(api: api, events: ws.stream),
    );
  }

  test('loads alerts and hides acknowledged ones by default', () async {
    final a = routes({
      'GET /api/v1/alerts': (_) => FakeReply(200, [
        alertJson('a1', severity: 'critical'),
        alertJson('a2', status: 'acknowledged'),
        alertJson('a3', severity: 'info'),
      ]),
    });
    final c = cubitWith(a);
    await c.load();
    expect(c.state.status, AlertsStatus.ready);
    expect(c.state.visible.map((x) => x.alertId), ['a1', 'a3']);
    c.setSeverity(AlertSeverity.critical);
    expect(c.state.visible.map((x) => x.alertId), ['a1']);
    c.setSeverity(null);
    c.setShowAcknowledged(true);
    expect(c.state.visible, hasLength(3));
    expect(c.state.activeCount(AlertSeverity.info), 1);
    await c.close();
  });

  test('a 503 load is a failed state with the honest wording', () async {
    final a = routes({
      'GET /api/v1/alerts': (_) => const FakeReply(503, {'detail': 'x'}),
    });
    final c = cubitWith(a);
    await c.load();
    expect(c.state.status, AlertsStatus.failed);
    expect(
      c.state.error!.messageAr,
      'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).',
    );
    await c.close();
  });

  test(
    'acknowledge reuses one Idempotency-Key across a failed attempt',
    () async {
      var acks = 0;
      final a = routes({
        'GET /api/v1/alerts': (_) => FakeReply(200, [alertJson('a1')]),
        'PATCH /api/v1/alerts/a1/acknowledge': (_) {
          acks++;
          return acks == 1
              ? const FakeReply(400, {'detail': 'مؤقّت'})
              : FakeReply(200, alertJson('a1', status: 'acknowledged'));
        },
      });
      final c = cubitWith(a);
      await c.load();
      expect(await c.acknowledge('a1'), isFalse);
      expect(c.state.message, startsWith('تعذّر الإقرار'));
      expect(c.state.alerts.single.isActive, isTrue);
      expect(await c.acknowledge('a1'), isTrue);
      expect(c.state.alerts.single.isAcknowledged, isTrue);
      expect(c.state.visible, isEmpty);
      final keys = a
          .to('/api/v1/alerts/a1/acknowledge')
          .map((r) => r.headers[kIdempotencyHeader])
          .toList();
      expect(keys, hasLength(2));
      expect(keys.first, isNotNull);
      expect(keys.first, keys.last, reason: 'same intent ⇒ same key');
      await c.close();
    },
  );

  test('double tap sends one acknowledge', () async {
    final gate = Completer<void>();
    final a = FakeAdapter((o) async {
      if (o.method == 'GET') return FakeReply(200, [alertJson('a1')]);
      await gate.future;
      return FakeReply(200, alertJson('a1', status: 'acknowledged'));
    });
    final c = cubitWith(a);
    await c.load();
    final first = c.acknowledge('a1');
    expect(await c.acknowledge('a1'), isFalse);
    gate.complete();
    await first;
    expect(a.to('/api/v1/alerts/a1/acknowledge'), hasLength(1));
    await c.close();
  });

  test(
    'a live alert frame (server shape: event_type) is inserted on top',
    () async {
      final a = routes({
        'GET /api/v1/alerts': (_) => FakeReply(200, [alertJson('a1')]),
      });
      final c = cubitWith(a);
      await c.load();
      // الشكل الذي يبثّه agents/notification/agent.py: لا مفتاح type.
      ws.add(
        WsEvent.fromJson({
          'event_type': 'weather_alert',
          'title': 'رياح قويّة',
          'message': 'أجّل الرشّ',
          'tenant_id': 't1',
          'data': {
            'alert_id': 'live1',
            'severity': 'critical',
            'field_id': 'f1',
          },
        }),
      );
      await settle();
      expect(c.state.alerts.first.alertId, 'live1');
      expect(c.state.alerts.first.displayTitle, 'رياح قويّة');
      expect(c.state.alerts.first.severity, AlertSeverity.critical);
      expect(c.state.message, 'تنبيه جديد: رياح قويّة');
      // نفس الحدث مرّتين لا يُكرَّر.
      ws.add(
        WsEvent.fromJson({
          'event_type': 'weather_alert',
          'data': {'alert_id': 'live1'},
        }),
      );
      await settle();
      expect(c.state.alerts.where((x) => x.alertId == 'live1'), hasLength(1));
      await c.close();
    },
  );

  test('a live frame for another field is ignored in a field inbox', () async {
    final a = routes({
      'GET /api/v1/alerts': (_) =>
          FakeReply(200, [alertJson('a1', fieldId: 'f1')]),
    });
    final c = cubitWith(a, fieldId: 'f1');
    await c.load();
    ws.add(
      WsEvent.fromJson({
        'type': 'alert',
        'alert_id': 'x',
        'field_id': 'f2',
        'severity': 'info',
      }),
    );
    await settle();
    expect(c.state.alerts.map((x) => x.alertId), ['a1']);
    await c.close();
  });

  test('parseLiveAlert: no alert_id ⇒ refresh hint, never a made-up row', () {
    final s = parseLiveAlert(
      WsEvent.fromJson({
        'event_type': 'pest_alert',
        'title': 'آفة',
        'data': {},
      }),
    );
    expect(s!.kind, LiveAlertKind.refresh);
    expect(s.item, isNull);
    expect(parseLiveAlert(WsEvent.fromJson({'type': 'subscribed'})), isNull);
    expect(
      parseLiveAlert(WsEvent.fromJson({'event_type': 'task_assigned'})),
      isNull,
    );
  });

  test('unread counter: server count, live +1, acknowledge −1', () async {
    final a = routes({
      'GET /api/v1/alerts': (_) =>
          FakeReply(200, [alertJson('a1'), alertJson('a2')]),
    });
    final counter = AlertsUnreadCounter(api: apiWith(a), events: ws.stream);
    expect(counter.badgeText, isNull, reason: 'not measured yet');
    counter.ensureStarted();
    await settle();
    expect(counter.count, 2);
    expect(a.requests.single.path, '/api/v1/alerts');
    ws.add(
      WsEvent.fromJson({
        'type': 'alert_created',
        'alert_id': 'a3',
        'severity': 'warning',
      }),
    );
    await settle();
    expect(counter.badgeText, '3');
    counter.markAcknowledged('a1');
    expect(counter.count, 2);
    await counter.reset();
    expect(counter.count, isNull);
  });
}
