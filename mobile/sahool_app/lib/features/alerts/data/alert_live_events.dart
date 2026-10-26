// SAHOOL — features/alerts/data/alert_live_events.dart
// ترجمة أحداث قناة الإشعارات الحيّة (WebSocketService.events) إلى إشارات
// تنبيه. أوّل مشترك في هذه القناة داخل التطبيق.
//
// شكل الإطار كما يبثّه الخادم فعلاً (agents/notification/agent.py dispatch):
//   {event_type, title, message, data: {...}, tenant_id, user_id}
// أي أنّ النوع في `event_type` لا في `type` — و`WsEvent.fromJson` في core يقرأ
// `type`/`event` فقط، فـ`on('alert')` لا يطابق شيئاً من هذا المنتِج. لذا نشترك في
// `events` كلّها ونقرأ النوع من الحقلين هنا.
//
// صدق: لا نبني تنبيهاً في القائمة إلّا إن حمل الإطار `alert_id` حقيقيّاً. إطار
// تنبيهٍ بلا معرّف ⇒ إشارة «أعِد التحميل» فقط (لا صفّ مُختلَق).
import 'package:flutter/foundation.dart';
import 'package:sahool_app/services/websocket_service.dart';

import 'alert_models.dart';

enum LiveAlertKind { created, acknowledged, refresh }

@immutable
class LiveAlertSignal {
  const LiveAlertSignal(this.kind, {this.item, this.alertId, this.titleAr});
  final LiveAlertKind kind;

  /// التنبيه الكامل إن حمل الإطار معرّفه.
  final AlertItem? item;
  final String? alertId;

  /// نصّ قصير لإعلام المستخدم (عنوان الإطار) حين لا يكون تنبيهاً كاملاً.
  final String? titleAr;
}

const _createdTypes = {
  'alert',
  'alert_created',
  'alert.created',
  'new_alert',
  'weather_alert',
  'pest_alert',
};
const _ackTypes = {'alert_acknowledged', 'alert.acknowledged'};

String _eventType(WsEvent e) {
  if (e.type.isNotEmpty) return e.type;
  final et = e.data['event_type'];
  return et == null ? '' : et.toString();
}

bool _isAlertType(String t) {
  final lower = t.toLowerCase();
  return _createdTypes.contains(lower) ||
      kAlertTypeLabelsAr.containsKey(lower) ||
      lower.startsWith('weather_');
}

Iterable<Map<String, dynamic>> _candidates(Map<String, dynamic> root) sync* {
  yield root;
  for (final k in const ['alert', 'data', 'payload']) {
    final v = root[k];
    if (v is Map) yield v.cast<String, dynamic>();
  }
}

/// null ⇒ الإطار لا يخصّ التنبيهات.
LiveAlertSignal? parseLiveAlert(WsEvent e) {
  final type = _eventType(e).toLowerCase();
  if (type.isEmpty) return null;
  final root = e.data;
  String? alertId;
  Map<String, dynamic>? source;
  for (final c in _candidates(root)) {
    final id =
        c['alert_id'] ??
        (c['aggregate_type'] == 'alert' ? c['aggregate_id'] : null);
    if (id != null && id.toString().isNotEmpty) {
      alertId = id.toString();
      source = c;
      break;
    }
  }
  final title = (root['title_ar'] ?? root['title'])?.toString();

  if (_ackTypes.contains(type)) {
    return alertId == null
        ? const LiveAlertSignal(LiveAlertKind.refresh)
        : LiveAlertSignal(LiveAlertKind.acknowledged, alertId: alertId);
  }
  if (!_isAlertType(type)) return null;
  if (alertId == null || source == null) {
    return LiveAlertSignal(LiveAlertKind.refresh, titleAr: title);
  }
  String? pick(String k, [String? alt]) {
    for (final c in [source!, root]) {
      final v = c[k] ?? (alt == null ? null : c[alt]);
      if (v != null && v.toString().isNotEmpty) return v.toString();
    }
    return null;
  }

  final rawType =
      pick('alert_type') ??
      (kAlertTypeLabelsAr.containsKey(type) || type.startsWith('weather_')
          ? type
          : 'other');
  final created = pick('created_at');
  final item = AlertItem(
    alertId: alertId,
    fieldId: pick('field_id'),
    alertType: rawType,
    severityRaw: pick('severity') ?? '',
    titleAr: pick('title_ar', 'title'),
    messageAr: pick('message_ar', 'message'),
    status: pick('status') ?? 'active',
    createdAt: created == null ? DateTime.now() : DateTime.tryParse(created),
  );
  return LiveAlertSignal(
    LiveAlertKind.created,
    item: item,
    alertId: alertId,
    titleAr: item.displayTitle,
  );
}

/// تدفّق إشارات التنبيه من تدفّق أحداث القناة.
Stream<LiveAlertSignal> liveAlertSignals(Stream<WsEvent> events) =>
    events.map(parseLiveAlert).where((s) => s != null).cast<LiveAlertSignal>();

/// المصدر الافتراضيّ: قناة الإشعارات المشتركة.
Stream<WsEvent> defaultAlertEventSource() => WebSocketService.instance.events;
