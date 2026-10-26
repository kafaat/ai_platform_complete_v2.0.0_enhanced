// SAHOOL — features/farm_book/farm_book_routes.dart
// وحدة ميزة «دفتر المزرعة». المُشاهِد محجوب (كالويب: VIEWER_BLOCKED_PAGES في
// frontend/src/lib/permissions.ts، والخادم لا يمنحه صلاحيّة ماليّة)، فلا يرى المسار
// في «المزيد» ويصله «لا صلاحيّة» عبر الرابط العميق. يملكها وكيل الميزة.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/farm_book_screen.dart';

abstract final class FarmBookRoutes {
  static const book = '/farm-book';

  /// الأدوار التي ترى الدفتر: الكلّ عدا المُشاهِد.
  static const roles = {
    AppRole.owner,
    AppRole.manager,
    AppRole.agronomist,
    AppRole.worker,
  };
}

final FeatureModule farmBookFeature = FeatureModule(
  id: 'farm_book',
  routes: [
    AppRoute(
      path: FarmBookRoutes.book,
      titleAr: 'دفتر المزرعة',
      icon: Icons.menu_book_outlined,
      allowedRoles: FarmBookRoutes.roles,
      aliases: const ['farm_book'],
      menu: const MenuEntry(MenuSection.records, order: 30),
      builder: (_, _) => const FarmBookScreen(),
    ),
  ],
);
