// SAHOOL — features/maps/io/maps_io_routes.dart
// مسارات حزمة الاستيراد/التصدير/مشي GPS/الدمج والتقسيم. تُصدَّر كقائمة يضمّها
// maps_routes.dart (يملكه وكيل الخرائط الأساسيّ) عند الدمج:
//   routes: [..., ...mapsIoRoutes]
//
// وضع الالتقاط لتدفّق الرسم: `/maps/import?mode=pick` و`/maps/gps-walk?mode=pick`
// يُعيدان بـNavigator.pop مضلّعاً GeoJSON واحداً (`Map<String, dynamic>`، حلقة
// خارجيّة مغلقة [lon,lat]) دون أيّ كتابة على الخادم.
//
// الأدوار: إنشاء الحقول/الدمج/التقسيم في الخادم يتطلّب FIELD_CREATE (owner/manager
// في core/authorization.py) ⇒ RouteRoles.management. مشي GPS مفتوح للمحرّرين لقياس
// المساحة، وزرّ الحفظ فيه للإدارة فقط. التصدير قراءة ⇒ أيّ دور.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/export_screen.dart';
import 'presentation/field_ops_screens.dart';
import 'presentation/gps_walk_screen.dart';
import 'presentation/import_screen.dart';

abstract final class MapsIoRoutes {
  /// `?farm_id=<id>` اختياريّ؛ `?mode=pick` لتدفّق الرسم.
  static const import = '/maps/import';

  /// `?farm_id=<id>` اختياريّ؛ `?mode=pick` لتدفّق الرسم.
  static const gpsWalk = '/maps/gps-walk';

  /// `?field_id=<id>` لحقل واحد؛ بدونه كلّ الحقول.
  static const export = '/maps/export';
  static const merge = '/maps/merge';

  /// `?field_id=<id>` لاختيار الحقل مسبقاً.
  static const split = '/maps/split';
}

bool _pick(RouteArgs a) => a['mode'] == 'pick';

final List<AppRoute> mapsIoRoutes = [
  AppRoute(
    path: MapsIoRoutes.import,
    titleAr: 'استيراد حدود الحقول',
    icon: Icons.upload_file_outlined,
    allowedRoles: RouteRoles.management,
    menu: const MenuEntry(MenuSection.farm, order: 60),
    builder: (_, a) => ImportScreen(farmId: a['farm_id'], pickMode: _pick(a)),
  ),
  AppRoute(
    path: MapsIoRoutes.gpsWalk,
    titleAr: 'مشي حدود الحقل',
    icon: Icons.directions_walk_rounded,
    allowedRoles: RouteRoles.editors,
    menu: const MenuEntry(MenuSection.farm, order: 61),
    builder: (_, a) => GpsWalkScreen(farmId: a['farm_id'], pickMode: _pick(a)),
  ),
  AppRoute(
    path: MapsIoRoutes.export,
    titleAr: 'تصدير حدود الحقول',
    icon: Icons.ios_share_rounded,
    menu: const MenuEntry(MenuSection.farm, order: 62),
    builder: (_, a) => ExportScreen(fieldId: a['field_id']),
  ),
  AppRoute(
    path: MapsIoRoutes.merge,
    titleAr: 'دمج حقلين',
    icon: Icons.merge_type_rounded,
    allowedRoles: RouteRoles.management,
    menu: const MenuEntry(MenuSection.farm, order: 63),
    builder: (_, _) => const MergeFieldsScreen(),
  ),
  AppRoute(
    path: MapsIoRoutes.split,
    titleAr: 'تقسيم حقل',
    icon: Icons.content_cut_rounded,
    allowedRoles: RouteRoles.management,
    menu: const MenuEntry(MenuSection.farm, order: 64),
    builder: (_, a) => SplitFieldScreen(fieldId: a['field_id']),
  ),
];
