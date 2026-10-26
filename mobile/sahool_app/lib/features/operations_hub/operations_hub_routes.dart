// SAHOOL — features/operations_hub/operations_hub_routes.dart
// مركز العمليّات: يجمع مداخل قسم MenuSection.operations من ملفّات مسارات الميزات.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/operations_hub_screen.dart';

abstract final class OperationsHubRoutes {
  static const hub = '/operations';
}

final FeatureModule operationsHubFeature = FeatureModule(
  id: 'operations_hub',
  routes: [
    AppRoute(
      path: OperationsHubRoutes.hub,
      titleAr: 'مركز العمليّات',
      icon: Icons.grid_view_rounded,
      menu: const MenuEntry(MenuSection.operations, order: 0),
      builder: (_, _) => const OperationsHubScreen(),
    ),
  ],
);
