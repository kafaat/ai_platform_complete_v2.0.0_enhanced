// SAHOOL — features/alerts/alerts_paths.dart
// المسارات القانونيّة لميزة التنبيهات (روابط عميقة). عامّة: يمكن لميزات أخرى
// فتحها بـcontext.openRoute(AlertsPaths.field(fieldId)).
abstract final class AlertsPaths {
  /// صندوق التنبيهات.
  static const inbox = '/alerts';

  /// تفاصيل تنبيه: `/alerts/detail?alert_id=<id>` (أو AlertItem في arguments).
  static const detail = '/alerts/detail';

  /// تنبيهات حقل: `/alerts/field?field_id=<id>`.
  static const fieldAlerts = '/alerts/field';

  /// تفضيلات الإشعار.
  static const preferences = '/alerts/preferences';

  static String field(String fieldId) =>
      '$fieldAlerts?field_id=${Uri.encodeQueryComponent(fieldId)}';

  static String detailOf(String alertId) =>
      '$detail?alert_id=${Uri.encodeQueryComponent(alertId)}';
}
