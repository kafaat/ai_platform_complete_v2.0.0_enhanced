// SAHOOL — features/satellite/satellite_routes.dart
// مسارات ميزة satellite. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/satellite_screen.dart';

abstract final class SatelliteRoutes {
  static const satellite = '/satellite';
}

final FeatureModule satelliteFeature = FeatureModule(
  id: 'satellite',
  routes: [
    AppRoute(
      path: SatelliteRoutes.satellite,
      titleAr: 'الأقمار الصناعيّة',
      icon: Icons.satellite_alt_outlined,
      
      menu: const MenuEntry(MenuSection.cropHealth, order: 10),
      builder: (_, _) => const SatelliteScreen(),
    ),
  ],
);
