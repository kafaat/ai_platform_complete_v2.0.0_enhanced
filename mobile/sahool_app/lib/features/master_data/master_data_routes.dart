// SAHOOL — features/master_data/master_data_routes.dart
// مسارات ميزة master_data. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/master_data_screen.dart';

abstract final class MasterDataRoutes {
  static const masterData = '/master-data';
}

final FeatureModule masterDataFeature = FeatureModule(
  id: 'master_data',
  routes: [
    AppRoute(
      path: MasterDataRoutes.masterData,
      titleAr: 'البيانات المرجعيّة',
      icon: Icons.storage_outlined,
      allowedRoles: RouteRoles.management,
      menu: const MenuEntry(MenuSection.records, order: 10),
      builder: (_, __) => const MasterDataScreen(),
    ),
  ],
);
