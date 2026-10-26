// SAHOOL — features/devices/devices_routes.dart
// مسارات ميزة devices. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/route_pages.dart';

import 'presentation/device_detail_screen.dart';
import 'presentation/devices_screen.dart';

abstract final class DevicesRoutes {
  static const devices = '/devices';

  /// رابط عميق: `/devices/detail?device_id=dev_…`.
  static const detail = '/devices/detail';
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
    AppRoute(
      path: DevicesRoutes.detail,
      titleAr: 'قراءات الجهاز',
      icon: Icons.show_chart_rounded,
      builder: (_, args) {
        final id = args['device_id'];
        if (id == null || id.isEmpty) {
          return const MissingRouteParamPage(param: 'device_id');
        }
        return DeviceDetailScreen(deviceId: id);
      },
    ),
  ],
);
