// SAHOOL — features/alerts/presentation/alert_visuals.dart
// تمثيل الخطورة بصريّاً: لون + أيقونة + نصّ معاً (لا معنى باللون وحده).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/alert_models.dart';

StatusTone severityTone(AlertSeverity s) => switch (s) {
  AlertSeverity.critical => StatusTone.danger,
  AlertSeverity.warning => StatusTone.warning,
  AlertSeverity.info => StatusTone.info,
  AlertSeverity.unknown => StatusTone.neutral,
};

IconData severityIcon(AlertSeverity s) => switch (s) {
  AlertSeverity.critical => Icons.report_rounded,
  AlertSeverity.warning => Icons.warning_amber_rounded,
  AlertSeverity.info => Icons.info_outline_rounded,
  AlertSeverity.unknown => Icons.notifications_none_rounded,
};

StatusChip severityChip(AlertSeverity s) =>
    StatusChip(label: s.labelAr, tone: severityTone(s), icon: severityIcon(s));

StatusChip alertStatusChip(AlertItem a) => StatusChip(
  label: a.statusLabelAr,
  tone: a.isActive ? StatusTone.warning : StatusTone.success,
  icon: a.isActive
      ? Icons.notifications_active_outlined
      : Icons.check_circle_outline_rounded,
);

/// الإقرار والتقييم يتطلّبان FIELD_EDIT على الخادم، وهي في مصفوفة الأدوار
/// (core/authorization.py) لدى owner/manager فقط — فلا نعرض زرّاً سيُرفض 403.
bool canActOnAlerts([String? role]) => canManage(role ?? currentRole());

/// حفظ تفضيلات الإشعار (PUT) يتطلّب FIELD_EDIT أيضاً.
bool canEditNotificationPrefs([String? role]) =>
    canManage(role ?? currentRole());
