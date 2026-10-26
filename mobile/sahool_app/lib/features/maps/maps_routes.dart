// SAHOOL — features/maps/maps_routes.dart
// مسارات ميزة الخرائط: «خريطة حقولي» وإدارة «خرائط بلا اتّصال». يملكها وكيل
// الخرائط. المكوّنات المشتركة (SahoolMap، الطبقات، محوّل GeoJSON) تحت
// presentation/ و geo/ تستوردها الميزات الأخرى.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/farm_map_screen.dart';
import 'presentation/offline_packs_screen.dart';

abstract final class MapsRoutes {
  static const farmMap = FarmMapScreen.routePath;
  static const offlinePacks = OfflinePacksScreen.routePath;
}

final FeatureModule mapsFeature = FeatureModule(
  id: 'maps',
  routes: [
    AppRoute(
      path: MapsRoutes.farmMap,
      titleAr: 'خريطة حقولي',
      icon: Icons.map_outlined,
      menu: const MenuEntry(MenuSection.farm, order: 15),
      builder: (_, _) => const FarmMapScreen(),
    ),
    AppRoute(
      path: MapsRoutes.offlinePacks,
      titleAr: 'خرائط بلا اتّصال',
      icon: Icons.download_for_offline_outlined,
      menu: const MenuEntry(MenuSection.farm, order: 90),
      builder: (_, _) => const OfflinePacksScreen(),
    ),
  ],
);
