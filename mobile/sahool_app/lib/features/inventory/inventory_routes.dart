// SAHOOL — features/inventory/inventory_routes.dart
// مسارات ميزة inventory. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/route_pages.dart';

import 'data/inventory_models.dart';
import 'presentation/inventory_item_screen.dart';
import 'presentation/inventory_screen.dart';

abstract final class InventoryRoutes {
  static const inventory = '/inventory';

  /// رابط عميق: `/inventory/item?item_id=inv_…`.
  static const item = '/inventory/item';
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
    AppRoute(
      path: InventoryRoutes.item,
      titleAr: 'عنصر المخزون',
      icon: Icons.inventory_2_outlined,
      builder: (_, args) {
        final id = args['item_id'];
        if (id == null || id.isEmpty) {
          return const MissingRouteParamPage(param: 'item_id');
        }
        final extra = args.extra;
        return InventoryItemScreen(
          itemId: id,
          initial: extra is Map && extra['item'] is InventoryItem
              ? extra['item'] as InventoryItem
              : null,
        );
      },
    ),
  ],
);
