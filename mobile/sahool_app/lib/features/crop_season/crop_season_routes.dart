// SAHOOL — features/crop_season/crop_season_routes.dart
// وحدة ميزة «المواسم والأطوار». يملكها وكيل الميزة.
//
// الرابط العميق: `/seasons?field_id=<id>` (مساحة عمل الحقل تفتحه بمعرّف الحقل).
// بلا field_id تعرض الشاشة قائمة الحقول للاختيار.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/seasons_screen.dart';

abstract final class CropSeasonRoutes {
  /// `/seasons?field_id=<id>&field_name=<name>`
  static const seasons = '/seasons';

  static String forField(String fieldId) =>
      '$seasons?field_id=${Uri.encodeQueryComponent(fieldId)}';
}

final FeatureModule cropSeasonFeature = FeatureModule(
  id: 'crop_season',
  routes: [
    AppRoute(
      path: CropSeasonRoutes.seasons,
      titleAr: 'المواسم والأطوار',
      icon: Icons.calendar_month_outlined,
      menu: const MenuEntry(MenuSection.cropHealth, order: 20),
      builder: (_, args) => CropSeasonScreen(
        fieldId: args['field_id'],
        fieldName: args['field_name'],
      ),
    ),
  ],
);
