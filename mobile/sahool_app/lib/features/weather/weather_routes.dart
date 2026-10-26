// SAHOOL — features/weather/weather_routes.dart
// مسارات ميزة «الطقس»: `/weather` (اختيار الحقل) و`/weather?field_id=<id>`.
// يملكها وكيل الميزة.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/weather_screen.dart';
import 'weather_paths.dart';

final FeatureModule weatherFeature = FeatureModule(
  id: 'weather',
  routes: [
    AppRoute(
      path: WeatherPaths.weather,
      titleAr: 'الطقس ونوافذ العمليّات',
      icon: Icons.cloud_outlined,
      menu: const MenuEntry(MenuSection.cropHealth, order: 20),
      builder: (_, args) => WeatherScreen(fieldId: args['field_id']),
    ),
  ],
);
