// SAHOOL — features/alerts/data/alerts_api.dart
// نقاط ميزة التنبيهات وتفضيلات الإشعار. يملكه وكيل ميزة التنبيهات.
//
// العقود (services/sahool-platform/api):
//   GET   /api/v1/alerts?status&severity&limit&offset   routers/alerts.py:50
//         ⇒ list[AlertSummary] (alert_models.py: alert_id, field_id, alert_type,
//           severity ∈ info|warning|critical, title_ar, message_ar,
//           status ∈ active|acknowledged|resolved, created_at). FIELD_VIEW.
//   PATCH /api/v1/alerts/{id}/acknowledge                 routers/alerts.py:204
//         ⇒ AlertSummary. FIELD_EDIT (owner/manager في مصفوفة الأدوار).
//   GET   /api/v1/fields/{id}/alerts/derived              routers/fields.py:4031
//         ⇒ {field_id, alerts: [{alert_type, severity, title_ar, message_ar, source}]}
//   POST  /api/v1/fields/{id}/alerts/evaluate             routers/fields.py:3426
//         ⇒ {created: [AlertSummary], skipped_existing}. FIELD_EDIT.
//   GET/PUT /api/v1/notifications/preferences             routers/notifications.py:54/84
//         ⇒ NotificationPreferences (api_models.py:174). PUT يستبدل الصفّ كاملاً
//           (upsert)، لذا لا يُرسَل إلّا فوق قراءةٍ ناجحة (notification_prefs.dart).
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'alert_models.dart';

class AlertsApi {
  AlertsApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final AlertsApi instance = AlertsApi();
  final ApiClient _client;

  /// حجم الصفحة الذي نطلبه (سقف الخادم الافتراضيّ 100).
  static const int pageSize = 100;

  /// أحدث تنبيهات المستأجِر (الأحدث أوّلاً).
  Future<List<AlertItem>> listAlerts({
    String? status,
    String? severity,
    int? limit,
    int? offset,
  }) async {
    final r = await _client.get(
      '/api/v1/alerts',
      query: {
        if (status != null) 'status': status,
        if (severity != null) 'severity': severity,
        if (limit != null) 'limit': limit,
        if (offset != null) 'offset': offset,
      },
    );
    return asJsonList(r).map(AlertItem.fromJson).toList();
  }

  /// يُقِرّ تنبيهاً. [idempotencyKey] ثابت لنيّة إقرار هذا التنبيه.
  Future<AlertItem> acknowledgeAlert(
    String alertId, {
    IdempotencyKey? idempotencyKey,
  }) async {
    final r = await _client.patch(
      '/api/v1/alerts/${Uri.encodeComponent(alertId)}/acknowledge',
      idempotencyKey: idempotencyKey,
    );
    return AlertItem.fromJson(asJsonMap(r));
  }

  /// تنبيهات الحقل المشتقّة من حالته القانونيّة (للعرض فقط، لا تُخزَّن).
  Future<List<DerivedAlert>> fieldDerivedAlerts(String fieldId) async {
    final r = await _client.get(
      '/api/v1/fields/${Uri.encodeComponent(fieldId)}/alerts/derived',
    );
    return asWrappedJsonList(asJsonMap(r), const [
      'alerts',
    ]).map(DerivedAlert.fromJson).toList();
  }

  /// يقيّم ظروف الحقل الآن وينشئ تنبيهات مخزّنة (owner/manager).
  Future<EvaluateResult> evaluateFieldAlerts(
    String fieldId, {
    IdempotencyKey? idempotencyKey,
  }) async {
    final r = await _client.post(
      '/api/v1/fields/${Uri.encodeComponent(fieldId)}/alerts/evaluate',
      idempotencyKey: idempotencyKey,
    );
    return EvaluateResult.fromJson(asJsonMap(r));
  }

  /// تفضيلات الإشعار كما يحفظها الخادم (كلّ المفاتيح، بما فيها المجهولة لنا).
  Future<Map<String, dynamic>> getNotificationPreferences() async =>
      asJsonMap(await _client.get('/api/v1/notifications/preferences'));

  /// يستبدل التفضيلات كاملةً. لا تستدعِها من واجهة مباشرةً: استعمل
  /// `NotificationPrefsRepository.save` التي تقرأ قبل أن تكتب.
  Future<Map<String, dynamic>> putNotificationPreferences(
    Map<String, dynamic> body, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.put(
      '/api/v1/notifications/preferences',
      data: body,
      idempotencyKey: idempotencyKey,
    ),
  );
}
