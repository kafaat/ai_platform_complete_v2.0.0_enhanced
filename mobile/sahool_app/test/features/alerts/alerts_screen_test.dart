// شاشات التنبيهات على ApiClient الحقيقيّ: القائمة، الأدوار، الإقرار، الإدراج
// الحيّ، تفضيلات الإشعار (لا نموذج بلا قراءة)، والشارة.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/alerts/data/alerts_api.dart';
import 'package:sahool_app/features/alerts/data/alerts_unread.dart';
import 'package:sahool_app/features/alerts/presentation/alert_detail_screen.dart';
import 'package:sahool_app/features/alerts/presentation/alerts_badge.dart';
import 'package:sahool_app/features/alerts/presentation/alerts_screen.dart';
import 'package:sahool_app/features/alerts/presentation/notification_prefs_screen.dart';
import 'package:sahool_app/services/websocket_service.dart';

import '../../core/fake_http.dart';
import 'alerts_fakes.dart';

AlertsApi apiWith(FakeAdapter a) => AlertsApi(
  testClient(
    a,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  ),
);

void main() {
  late StreamController<WsEvent> ws;
  setUp(() => ws = StreamController<WsEvent>.broadcast());
  tearDown(() => ws.close());

  Future<FakeAdapter> pumpInbox(
    WidgetTester t,
    String role, {
    String? fieldId,
    Map<String, FakeReply Function(dynamic)>? extra,
  }) async {
    final a = routes({
      'GET /api/v1/alerts': (_) => FakeReply(200, [
        alertJson('a1', severity: 'critical', title: 'رطوبة حرجة'),
        alertJson('a2', severity: 'info', title: 'معلومة ريّ'),
        alertJson('a3', status: 'acknowledged', title: 'قديم مُقَرّ'),
      ]),
      'PATCH /api/v1/alerts/a1/acknowledge': (_) => FakeReply(
        200,
        alertJson('a1', severity: 'critical', status: 'acknowledged'),
      ),
      'GET /api/v1/fields/f1/alerts/derived': (_) =>
          const FakeReply(200, {'field_id': 'f1', 'alerts': []}),
      ...?extra,
    });
    final api = apiWith(a);
    await t.pumpWidget(
      arHost(
        AlertsScreen(
          api: api,
          fieldId: fieldId,
          events: ws.stream,
          counter: AlertsUnreadCounter(api: api, events: ws.stream),
          role: role,
        ),
      ),
    );
    await t.pumpAndSettle();
    return a;
  }

  testWidgets('inbox lists active alerts, filters by severity', (t) async {
    await pumpInbox(t, 'manager');
    expect(find.text('رطوبة حرجة'), findsOneWidget);
    expect(find.text('معلومة ريّ'), findsOneWidget);
    expect(find.text('قديم مُقَرّ'), findsNothing);
    await t.tap(find.text('حرج (1)'));
    await t.pumpAndSettle();
    expect(find.text('معلومة ريّ'), findsNothing);
    expect(find.text('رطوبة حرجة'), findsOneWidget);
  });

  testWidgets('manager acknowledges; the alert leaves the active list', (
    t,
  ) async {
    final a = await pumpInbox(t, 'manager');
    expect(find.text('إقرار'), findsNWidgets(2));
    await t.tap(find.text('إقرار').first);
    await t.pumpAndSettle();
    expect(a.to('/api/v1/alerts/a1/acknowledge'), hasLength(1));
    expect(find.text('رطوبة حرجة'), findsNothing);
    expect(find.text('تمّ إقرار التنبيه.'), findsOneWidget);
  });

  testWidgets('worker sees no acknowledge button (server needs FIELD_EDIT)', (
    t,
  ) async {
    await pumpInbox(t, 'worker');
    expect(find.text('رطوبة حرجة'), findsOneWidget);
    expect(find.text('إقرار'), findsNothing);
  });

  testWidgets('a live event appears without a reload', (t) async {
    final a = await pumpInbox(t, 'viewer');
    ws.add(
      WsEvent.fromJson({
        'event_type': 'heat_stress',
        'title': 'موجة حرّ',
        'data': {'alert_id': 'live9', 'severity': 'warning'},
      }),
    );
    await t.pumpAndSettle();
    expect(find.text('موجة حرّ'), findsOneWidget);
    expect(a.to('/api/v1/alerts'), hasLength(1), reason: 'no refetch');
  });

  testWidgets('503 shows the honest message and a retry', (t) async {
    final a = routes({
      'GET /api/v1/alerts': (_) => const FakeReply(503, {'detail': 'x'}),
    });
    final api = apiWith(a);
    await t.pumpWidget(
      arHost(
        AlertsScreen(
          api: api,
          events: ws.stream,
          counter: AlertsUnreadCounter(api: api, events: ws.stream),
          role: 'owner',
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(
      find.text('الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).'),
      findsOneWidget,
    );
    expect(find.text('إعادة المحاولة'), findsOneWidget);
  });

  testWidgets('field inbox: evaluate for managers, derived empty is honest', (
    t,
  ) async {
    final a = await pumpInbox(
      t,
      'owner',
      fieldId: 'f1',
      extra: {
        'POST /api/v1/fields/f1/alerts/evaluate': (_) =>
            const FakeReply(200, {'created': [], 'skipped_existing': 0}),
      },
    );
    expect(find.textContaining('لا تنبيهات مشتقّة'), findsOneWidget);
    await t.tap(find.text('تقييم الحقل الآن'));
    await t.pumpAndSettle();
    expect(a.to('/api/v1/fields/f1/alerts/evaluate'), hasLength(1));
    expect(
      find.textContaining('ظروف الحقل ضمن الحدود الطبيعيّة'),
      findsOneWidget,
    );
  });

  testWidgets('detail shows the server recommendation and acknowledges', (
    t,
  ) async {
    final a = routes({
      'GET /api/v1/alerts': (_) => FakeReply(200, [
        alertJson('a1', message: 'رُيّ الحقل عاجلاً لتفادي إجهاد المحصول.'),
      ]),
      'PATCH /api/v1/alerts/a1/acknowledge': (_) =>
          FakeReply(200, alertJson('a1', status: 'acknowledged')),
    });
    final api = apiWith(a);
    await t.pumpWidget(
      arHost(
        AlertDetailScreen(
          alertId: 'a1',
          api: api,
          canAct: true,
          counter: AlertsUnreadCounter(api: api, events: ws.stream),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('التفاصيل والإجراء الموصى به'), findsOneWidget);
    expect(
      find.text('رُيّ الحقل عاجلاً لتفادي إجهاد المحصول.'),
      findsOneWidget,
    );
    await t.ensureVisible(find.text('إقرار التنبيه'));
    await t.pumpAndSettle();
    await t.tap(find.text('إقرار التنبيه'));
    await t.pumpAndSettle();
    expect(find.text('مُقَرّ'), findsOneWidget);
    expect(
      a.to('/api/v1/alerts/a1/acknowledge').single.headers['Idempotency-Key'],
      isNotNull,
    );
  });

  testWidgets('detail deep link to an unknown id says not found', (t) async {
    final a = routes({'GET /api/v1/alerts': (_) => const FakeReply(200, [])});
    final api = apiWith(a);
    await t.pumpWidget(
      arHost(
        AlertDetailScreen(
          alertId: 'gone',
          api: api,
          canAct: true,
          counter: AlertsUnreadCounter(api: api, events: ws.stream),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('العنصر غير موجود.'), findsOneWidget);
  });

  group('notification preferences screen', () {
    testWidgets('failed read ⇒ error, no form, and nothing can be saved', (
      t,
    ) async {
      final a = routes({
        'GET /api/v1/notifications/preferences': (_) =>
            const FakeReply(503, {'detail': 'x'}),
      });
      await t.pumpWidget(
        arHost(NotificationPrefsScreen(api: apiWith(a), role: 'owner')),
      );
      await t.pumpAndSettle();
      expect(find.text('تعذّرت قراءة التفضيلات'), findsOneWidget);
      expect(find.text('حفظ التفضيلات'), findsNothing);
      expect(a.requests.where((r) => r.method == 'PUT'), isEmpty);
    });

    testWidgets('editing one channel keeps the others on the server', (
      t,
    ) async {
      final row = {
        'email_enabled': true,
        'email_address': 'a@b.org',
        'sms_enabled': false,
        'sms_number': null,
        'push_enabled': true,
        'push_token': 'tok',
        'whatsapp_enabled': true,
        'whatsapp_number': '+967711',
        'event_types': ['weather_alert'],
        'min_severity': null,
      };
      final a = routes({
        'GET /api/v1/notifications/preferences': (_) => FakeReply(200, row),
        'PUT /api/v1/notifications/preferences': (o) =>
            FakeReply(200, o.data as Map),
      });
      await t.pumpWidget(
        arHost(NotificationPrefsScreen(api: apiWith(a), role: 'manager')),
      );
      await t.pumpAndSettle();
      await t.tap(find.text('رسائل SMS'));
      await t.pump();
      await t.scrollUntilVisible(
        find.text('حفظ التفضيلات'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await t.pumpAndSettle();
      await t.tap(find.text('حفظ التفضيلات'));
      await t.pumpAndSettle();
      final put = a.requests.singleWhere((r) => r.method == 'PUT');
      final body = bodyOf(put);
      expect(body['sms_enabled'], isTrue);
      expect(body['email_enabled'], isTrue);
      expect(body['whatsapp_number'], '+967711');
      expect(body['push_token'], 'tok');
      expect(body['event_types'], ['weather_alert']);
      expect(put.headers['Idempotency-Key'], isNotNull);
      expect(
        a.requests.where((r) => r.method == 'GET'),
        hasLength(2),
        reason: 'read on open + re-read before write',
      );
    });

    testWidgets('non-managers see read-only preferences', (t) async {
      final a = routes({
        'GET /api/v1/notifications/preferences': (_) =>
            const FakeReply(200, {'email_enabled': false, 'event_types': []}),
      });
      await t.pumpWidget(
        arHost(NotificationPrefsScreen(api: apiWith(a), role: 'worker')),
      );
      await t.pumpAndSettle();
      expect(find.textContaining('للقراءة فقط'), findsOneWidget);
      expect(find.text('حفظ التفضيلات'), findsNothing);
    });
  });

  testWidgets('badge shows the unread count and nothing before measuring', (
    t,
  ) async {
    final gate = Completer<void>();
    final a = FakeAdapter((o) async {
      await gate.future;
      return FakeReply(200, [alertJson('a1'), alertJson('a2')]);
    });
    final api = apiWith(a);
    final counter = AlertsUnreadCounter(api: api, events: ws.stream);
    await t.pumpWidget(
      arHost(
        Scaffold(
          body: Center(
            child: AlertsBadge(
              counter: counter,
              child: const Icon(Icons.notifications),
            ),
          ),
        ),
      ),
    );
    await t.pump();
    expect(find.text('0'), findsNothing);
    gate.complete();
    await t.pumpAndSettle();
    expect(find.text('2'), findsOneWidget);
    ws.add(
      WsEvent.fromJson({
        'type': 'alert',
        'alert_id': 'a9',
        'severity': 'critical',
      }),
    );
    await t.pumpAndSettle();
    expect(find.text('3'), findsOneWidget);
  });
}
