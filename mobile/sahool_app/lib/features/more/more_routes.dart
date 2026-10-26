// SAHOOL — features/more/more_routes.dart
// مسار «المزيد» (تبويب الغلاف). محتواه يُبنى من مداخل MenuEntry في ملفّات مسارات
// الميزات، فلا تحتاج ميزة جديدة إلى تعديل شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/more_screen.dart';

abstract final class MoreRoutes {
  static const more = '/more';
}

final FeatureModule moreFeature = FeatureModule(
  id: 'more',
  routes: [
    AppRoute(
      path: MoreRoutes.more,
      titleAr: 'المزيد',
      icon: Icons.menu_rounded,
      builder: (_, __) => const MoreScreen(),
    ),
  ],
);
