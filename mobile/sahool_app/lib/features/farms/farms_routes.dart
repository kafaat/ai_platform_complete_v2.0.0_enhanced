// SAHOOL — features/farms/farms_routes.dart
// مسارات ميزة farms. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/farms_screen.dart';

abstract final class FarmsRoutes {
  static const farms = '/farms';
}

final FeatureModule farmsFeature = FeatureModule(
  id: 'farms',
  routes: [
    AppRoute(
      path: FarmsRoutes.farms,
      titleAr: 'المزارع',
      icon: Icons.agriculture_outlined,

      menu: const MenuEntry(MenuSection.farm, order: 10),
      builder: (_, _) => const FarmsScreen(),
    ),
  ],
);
