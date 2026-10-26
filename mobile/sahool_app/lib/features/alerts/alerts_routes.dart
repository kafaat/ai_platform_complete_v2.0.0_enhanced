// SAHOOL — features/alerts/alerts_routes.dart
// مسارات ميزة «التنبيهات»: الصندوق، التفاصيل، تنبيهات حقل، تفضيلات الإشعار.
// يملكها وكيل الميزة.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'alerts_paths.dart';
import 'data/alert_models.dart';
import 'data/alerts_unread.dart';
import 'presentation/alert_detail_screen.dart';
import 'presentation/alerts_screen.dart';
import 'presentation/notification_prefs_screen.dart';

final FeatureModule alertsFeature = FeatureModule(
  id: 'alerts',
  // عدد التنبيهات واشتراكه الحيّ يخصّان المستخدم المنتهية جلسته.
  onSessionEnd: (_) => AlertsUnreadCounter.instance.reset(),
  routes: [
    AppRoute(
      path: AlertsPaths.inbox,
      titleAr: 'التنبيهات',
      icon: Icons.notifications_outlined,
      menu: const MenuEntry(MenuSection.cropHealth, order: 10),
      builder: (_, _) => const AlertsScreen(),
    ),
    AppRoute(
      path: AlertsPaths.fieldAlerts,
      titleAr: 'تنبيهات الحقل',
      icon: Icons.notification_important_outlined,
      builder: (_, args) {
        final fieldId = args['field_id'];
        return fieldId == null || fieldId.isEmpty
            ? const AlertsScreen()
            : AlertsScreen(fieldId: fieldId);
      },
    ),
    AppRoute(
      path: AlertsPaths.detail,
      titleAr: 'تفاصيل التنبيه',
      icon: Icons.notifications_active_outlined,
      builder: (_, args) {
        final extra = args.extra;
        final initial = extra is AlertItem ? extra : null;
        final id = initial?.alertId ?? args['alert_id'] ?? '';
        return AlertDetailScreen(alertId: id, initial: initial);
      },
    ),
    AppRoute(
      path: AlertsPaths.preferences,
      titleAr: 'تفضيلات الإشعار',
      icon: Icons.tune_rounded,
      menu: const MenuEntry(MenuSection.account, order: 40),
      builder: (_, _) => const NotificationPrefsScreen(),
    ),
  ],
);
