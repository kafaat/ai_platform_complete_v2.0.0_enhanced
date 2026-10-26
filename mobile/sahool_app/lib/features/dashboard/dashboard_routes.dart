// SAHOOL — features/dashboard/dashboard_routes.dart
// مسارات لوحة المعلومات (تبويب «الرئيسية» في الغلاف). يملكها وكيل لوحة المعلومات.
//
// الشاشة نفسها في lib/screens/dashboard_screen.dart — مسار مُثبَّت تقرؤه اختبارات
// CI خارج التطبيق بالمسار (انظر ARCHITECTURE.md «المسارات المُثبَّتة»).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/shell_scope.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_snapshot_store.dart';
import 'package:sahool_app/screens/dashboard_screen.dart';

abstract final class DashboardRoutes {
  static const home = '/dashboard';
}

final FeatureModule dashboardFeature = FeatureModule(
  id: 'dashboard',
  routes: [
    AppRoute(
      path: DashboardRoutes.home,
      titleAr: 'الرئيسية',
      icon: Icons.home_outlined,
      builder: (context, _) => DashboardScreen(
        // «أنشئ أوّل حقل»: داخل الغلاف ننتقل إلى تبويب الحقول، وخارجه نفتح المسار.
        onCreateField: () {
          final shell = ShellScope.maybeOf(context);
          if (shell != null) {
            shell.select('fields');
          } else {
            context.openRoute<void>('/fields');
          }
        },
      ),
    ),
  ],
  // لقطة «اليوم» المحفوظة تخصّ الحساب: تُمسَح عند الخروج (المفتاح مُنطَّق
  // بالمستأجِر+المستخدم أصلاً، والمسح يمنع بقاءها على جهاز مشترك).
  onSessionEnd: (_) => HiveDashboardSnapshotStore.instance.clear(),
);
