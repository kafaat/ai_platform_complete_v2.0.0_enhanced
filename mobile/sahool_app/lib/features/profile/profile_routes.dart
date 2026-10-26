// SAHOOL — features/profile/profile_routes.dart
// مسارات ميزة profile. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/profile_screen.dart';

abstract final class ProfileRoutes {
  static const profile = '/account/profile';
}

final FeatureModule profileFeature = FeatureModule(
  id: 'profile',
  routes: [
    AppRoute(
      path: ProfileRoutes.profile,
      titleAr: 'الحساب والإعدادات',
      icon: Icons.person_outline,

      menu: const MenuEntry(MenuSection.account, order: 10),
      builder: (_, _) => const ProfileScreen(),
    ),
  ],
);
