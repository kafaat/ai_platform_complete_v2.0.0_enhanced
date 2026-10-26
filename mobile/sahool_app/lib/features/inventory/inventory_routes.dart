// SAHOOL — features/inventory/inventory_routes.dart
// مسارات ميزة inventory. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/inventory_screen.dart';

abstract final class InventoryRoutes {
  static const inventory = '/inventory';
}

final FeatureModule inventoryFeature = FeatureModule(
  id: 'inventory',
  routes: [
    AppRoute(
      path: InventoryRoutes.inventory,
      titleAr: 'المخزون',
      icon: Icons.inventory_2_outlined,

      menu: const MenuEntry(MenuSection.operations, order: 40),
      builder: (_, _) => const InventoryScreen(),
    ),
  ],
);
