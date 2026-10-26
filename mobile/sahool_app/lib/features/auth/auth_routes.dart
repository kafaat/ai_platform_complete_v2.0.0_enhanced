// SAHOOL — features/auth/auth_routes.dart
// مسارات ميزة الدخول والأمان. يملكها وكيل ميزة auth وحده: أضِف شاشة هنا، لا في
// app_router.dart. (شاشة الدخول نفسها يعرضها AuthGate عند غياب الجلسة؛ المسار
// /login موجود للروابط العميقة ولإعادة الدخول من شاشة مدفوعة.)
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/login_screen.dart';
import 'presentation/mfa_setup_screen.dart';
import 'presentation/onboarding_screen.dart';

abstract final class AuthRoutes {
  static const login = '/login';
  static const mfa = '/account/mfa';
  static const onboarding = '/onboarding';
}

final FeatureModule authFeature = FeatureModule(
  id: 'auth',
  routes: [
    AppRoute(
      path: AuthRoutes.login,
      titleAr: 'تسجيل الدخول',
      icon: Icons.login_rounded,
      public: true,
      builder: (_, _) => const LoginScreen(),
    ),
    AppRoute(
      path: AuthRoutes.mfa,
      titleAr: 'المصادقة الثنائيّة (MFA)',
      icon: Icons.shield_outlined,
      menu: const MenuEntry(MenuSection.account, order: 20),
      builder: (_, _) => const MfaSetupScreen(),
    ),
    AppRoute(
      path: AuthRoutes.onboarding,
      titleAr: 'مرحباً بك',
      icon: Icons.waving_hand_outlined,
      builder: (context, _) => OnboardingScreen(
        onStart: () => context.openRoute<void>('/fields/new'),
      ),
    ),
  ],
);
