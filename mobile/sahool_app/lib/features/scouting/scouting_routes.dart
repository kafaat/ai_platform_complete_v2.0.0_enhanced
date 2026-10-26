// SAHOOL — features/scouting/scouting_routes.dart
// وحدة ميزة «الاستكشاف الميدانيّ». يملكها وكيل الميزة.
//
//   /scouting                 دبابيس الحقل (قائمة/خريطة) — ?field_id= اختياريّ
//   /scouting/capture         «التقاط مشاهدة»: الإجراء السريع (اختيار الحقل ثمّ
//                             النموذج مباشرةً) — في العمليّات بعد «المهام» مباشرةً
//   /scouting/pest-detect     كشف الآفات بالصورة لحقل (field_id يُرسل دائماً)
//
// لا تنظيف عند الخروج: المشاهدات غير المرسلة في صندوق الإرسال (يملكه offline_sync)
// وصورها مُنطَّقة بالمستأجِر على الجهاز (عمل ميدانيّ لم يُرفع لا يُحذف).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/new_observation_screen.dart';
import 'presentation/pest_detect_screen.dart';
import 'presentation/scouting_deps.dart';
import 'presentation/scouting_screen.dart';
import 'presentation/scouting_widgets.dart';

abstract final class ScoutingRoutes {
  static const pins = '/scouting';
  static const capture = '/scouting/capture';
  static const pestDetect = '/scouting/pest-detect';
}

final FeatureModule scoutingFeature = FeatureModule(
  id: 'scouting',
  routes: [
    AppRoute(
      path: ScoutingRoutes.pins,
      titleAr: 'الاستكشاف الميدانيّ',
      icon: Icons.pest_control_outlined,
      menu: const MenuEntry(MenuSection.cropHealth, order: 20),
      builder: (_, args) => ScoutingScreen(initialFieldId: args['field_id']),
    ),
    AppRoute(
      path: ScoutingRoutes.capture,
      titleAr: 'التقاط مشاهدة',
      icon: Icons.add_location_alt_outlined,
      allowedRoles: RouteRoles.editors,
      menu: const MenuEntry(MenuSection.operations, order: 15),
      builder: (_, args) {
        final deps = ScoutingDeps.device();
        return ScoutingFieldGate(
          title: 'التقاط مشاهدة',
          deps: deps,
          initialFieldId: args['field_id'],
          builder: (_, field) => NewObservationScreen(field: field, deps: deps),
        );
      },
    ),
    AppRoute(
      path: ScoutingRoutes.pestDetect,
      titleAr: 'كشف الآفات بالصورة',
      icon: Icons.camera_alt_outlined,
      allowedRoles: RouteRoles.editors,
      menu: const MenuEntry(MenuSection.cropHealth, order: 25),
      builder: (_, args) {
        final deps = ScoutingDeps.device();
        return ScoutingFieldGate(
          title: 'كشف الآفات بالصورة',
          deps: deps,
          initialFieldId: args['field_id'],
          builder: (_, field) => PestDetectScreen(field: field, deps: deps),
        );
      },
    ),
  ],
);
