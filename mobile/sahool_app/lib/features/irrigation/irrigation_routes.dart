// SAHOOL — features/irrigation/irrigation_routes.dart
// مسارات ميزة irrigation. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/irrigation_ops_screen.dart';

abstract final class IrrigationRoutes {
  static const ops = '/irrigation/ops';
}

final FeatureModule irrigationFeature = FeatureModule(
  id: 'irrigation',
  routes: [
    AppRoute(
      path: IrrigationRoutes.ops,
      titleAr: 'الريّ التشغيليّ',
      icon: Icons.water_drop_outlined,

      menu: const MenuEntry(MenuSection.operations, order: 30),
      builder: (_, _) => const IrrigationOpsScreen(),
    ),
  ],
);
