// SAHOOL — features/devices/devices_routes.dart
// مسارات ميزة devices. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/devices_screen.dart';

abstract final class DevicesRoutes {
  static const devices = '/devices';
}

final FeatureModule devicesFeature = FeatureModule(
  id: 'devices',
  routes: [
    AppRoute(
      path: DevicesRoutes.devices,
      titleAr: 'أجهزة الاستشعار (IoT)',
      icon: Icons.sensors,

      menu: const MenuEntry(MenuSection.operations, order: 60),
      builder: (_, _) => const DevicesScreen(),
    ),
  ],
);
