// SAHOOL — features/equipment/equipment_routes.dart
// مسارات ميزة equipment. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/equipment_screen.dart';

abstract final class EquipmentRoutes {
  static const equipment = '/equipment';
}

final FeatureModule equipmentFeature = FeatureModule(
  id: 'equipment',
  routes: [
    AppRoute(
      path: EquipmentRoutes.equipment,
      titleAr: 'المعدّات',
      icon: Icons.precision_manufacturing_outlined,
      
      menu: const MenuEntry(MenuSection.operations, order: 50),
      builder: (_, __) => const EquipmentScreen(),
    ),
  ],
);
