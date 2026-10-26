// SAHOOL — features/equipment/equipment_routes.dart
// مسارات ميزة equipment. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/route_pages.dart';

import 'data/equipment_models.dart';
import 'presentation/equipment_detail_screen.dart';
import 'presentation/equipment_screen.dart';

abstract final class EquipmentRoutes {
  static const equipment = '/equipment';

  /// رابط عميق: `/equipment/detail?equipment_id=eqp_…`.
  static const detail = '/equipment/detail';
}

final FeatureModule equipmentFeature = FeatureModule(
  id: 'equipment',
  routes: [
    AppRoute(
      path: EquipmentRoutes.equipment,
      titleAr: 'المعدّات',
      icon: Icons.precision_manufacturing_outlined,
      menu: const MenuEntry(MenuSection.operations, order: 50),
      builder: (_, _) => const EquipmentScreen(),
    ),
    AppRoute(
      path: EquipmentRoutes.detail,
      titleAr: 'تفاصيل المعدّة',
      icon: Icons.precision_manufacturing_outlined,
      builder: (_, args) {
        final id = args['equipment_id'];
        if (id == null || id.isEmpty) {
          return const MissingRouteParamPage(param: 'equipment_id');
        }
        final extra = args.extra;
        return EquipmentDetailScreen(
          equipmentId: id,
          initial: extra is Map && extra['equipment'] is Equipment
              ? extra['equipment'] as Equipment
              : null,
        );
      },
    ),
  ],
);
