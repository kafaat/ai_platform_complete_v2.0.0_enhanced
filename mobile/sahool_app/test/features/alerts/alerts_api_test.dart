// نقاط التنبيهات وتفضيلات الإشعار على ApiClient الحقيقيّ (FakeAdapter).
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/alerts/data/alert_models.dart';
import 'package:sahool_app/features/alerts/data/alerts_api.dart';
import 'package:sahool_app/features/alerts/data/notification_prefs.dart';

import '../../core/fake_http.dart';
import 'alerts_fakes.dart';

AlertsApi apiWith(FakeAdapter a) => AlertsApi(
  testClient(
    a,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  ),
);

void main() {
  group('alerts endpoints', () {
    test(
      'list sends the filters the server knows and parses AlertSummary',
      () async {
        final a = routes({
          'GET /api/v1/alerts': (_) => FakeReply(200, [
            alertJson('alr_1', severity: 'critical', message: 'رُيّ عاجلاً'),
          ]),
        });
        final list = await apiWith(
          a,
        ).listAlerts(severity: 'critical', limit: 100);
        final q = a.requests.single;
        expect(q.path, '/api/v1/alerts');
        expect(list.single.alertId, 'alr_1');
        expect(list.single.severity, AlertSeverity.critical);
        expect(list.single.messageAr, 'رُيّ عاجلاً');
        expect(list.single.isActive, isTrue);
      },
    );

    test('a non-list body is an error, never an empty inbox', () async {
      final a = routes({
        'GET /api/v1/alerts': (_) => const FakeReply(200, {'html': true}),
      });
      expect(apiWith(a).listAlerts(), throwsA(isA<FormatException>()));
    });

    test('acknowledge PATCHes the alert with the Idempotency-Key', () async {
      final a = routes({
        'PATCH /api/v1/alerts/alr_1/acknowledge': (_) =>
            FakeReply(200, alertJson('alr_1', status: 'acknowledged')),
      });
      final r = await apiWith(a).acknowledgeAlert(
        'alr_1',
        idempotencyKey: const IdempotencyKey('k-ack-1'),
      );
      expect(r.isAcknowledged, isTrue);
      expect(a.requests.single.headers[kIdempotencyHeader], 'k-ack-1');
    });

    test('derived alerts and evaluate read the real envelopes', () async {
      final a = routes({
        'GET /api/v1/fields/f1/alerts/derived': (_) => const FakeReply(200, {
          'field_id': 'f1',
          'alerts': [
            {
              'alert_type': 'salinity_critical',
              'severity': 'critical',
              'title_ar': 'ملوحة تربة حرجة',
              'message_ar': 'غسيل',
              'source': 'canonical_field_state',
            },
          ],
        }),
        'POST /api/v1/fields/f1/alerts/evaluate': (_) => FakeReply(200, {
          'created': [alertJson('alr_9')],
          'skipped_existing': 2,
        }),
      });
      final api = apiWith(a);
      final d = await api.fieldDerivedAlerts('f1');
      expect(d.single.displayTitle, 'ملوحة تربة حرجة');
      final e = await api.evaluateFieldAlerts(
        'f1',
        idempotencyKey: const IdempotencyKey('k-eval'),
      );
      expect(e.created.single.alertId, 'alr_9');
      expect(e.summaryAr, contains('مع تجاوز 2'));
      expect(
        a
            .to('/api/v1/fields/f1/alerts/evaluate')
            .single
            .headers[kIdempotencyHeader],
        'k-eval',
      );
    });
  });

  group('notification preferences: read before write', () {
    final server = <String, dynamic>{
      'email_enabled': true,
      'email_address': 'farmer@example.org',
      'sms_enabled': true,
      'sms_number': '+967700000001',
      'push_enabled': true,
      'push_token': 'device-token',
      'whatsapp_enabled': true,
      'whatsapp_number': '+967700000002',
      'event_types': ['weather_alert', 'future_type_x'],
      'min_severity': 'warning',
      'unknown_server_key': 42,
    };

    test('a failed re-read sends no PUT (the wipe the audit found)', () async {
      var gets = 0;
      final a = routes({
        'GET /api/v1/notifications/preferences': (_) {
          gets++;
          return gets == 1
              ? FakeReply(200, server)
              : const FakeReply(503, {'detail': 'db down'});
        },
        'PUT /api/v1/notifications/preferences': (_) =>
            const FakeReply(200, {}),
      });
      final repo = NotificationPrefsRepository(apiWith(a));
      await repo.load();
      final draft = const PrefsDraft().setField('sms_enabled', false);
      await expectLater(repo.save(draft), throwsA(isA<ApiException>()));
      expect(
        a
            .to('/api/v1/notifications/preferences')
            .where((r) => r.method == 'PUT'),
        isEmpty,
      );
    });

    test('save writes only the user edits over the fresh server row', () async {
      // الخادم تغيّر بين الفتح والحفظ (جهاز آخر سجّل رمز دفع جديداً).
      final fresh = {...server, 'push_token': 'newer-token'};
      final a = routes({
        'GET /api/v1/notifications/preferences': (_) => FakeReply(200, fresh),
        'PUT /api/v1/notifications/preferences': (o) =>
            FakeReply(200, o.data as Map),
      });
      final draft = const PrefsDraft()
          .setField('sms_number', '٧٧٧ ١٢٣ ٤٥٦')
          .toggleEvent('pest_alert', on: true)
          .toggleEvent('weather_alert', on: false);
      await NotificationPrefsRepository(
        apiWith(a),
      ).save(draft, idempotencyKey: const IdempotencyKey('k-prefs'));
      final put = a.requests.firstWhere((r) => r.method == 'PUT');
      final body = bodyOf(put);
      expect(body['email_enabled'], isTrue);
      expect(body['email_address'], 'farmer@example.org');
      expect(body['whatsapp_enabled'], isTrue);
      expect(body['whatsapp_number'], '+967700000002');
      expect(body['push_token'], 'newer-token');
      expect(body['unknown_server_key'], 42);
      expect(body['min_severity'], 'warning');
      expect(body['sms_number'], '777123456');
      expect(body['event_types'], ['future_type_x', 'pest_alert']);
      expect(put.headers[kIdempotencyHeader], 'k-prefs');
      // القراءة سبقت الكتابة.
      expect(a.requests.first.method, 'GET');
    });

    test('a missing server value is reported unknown, not false', () {
      const p = NotificationPrefs({'email_enabled': true});
      expect(p.enabled(NotifChannel.email), isTrue);
      expect(p.enabled(NotifChannel.sms), isNull);
    });
  });
}
