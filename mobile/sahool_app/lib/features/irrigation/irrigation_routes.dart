// SAHOOL — features/irrigation/irrigation_routes.dart
// مسارات ميزة irrigation. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
//
// روابط عميقة: `/irrigation/today?field_id=f1` (من مساحة الحقل)،
// `/irrigation/ledger?field_id=f1` (أو arguments: {field_id, field_name, area_ha}).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import 'presentation/irrigation_ops_screen.dart';
import 'presentation/ledger/water_ledger_screen.dart';
import 'presentation/plan/irrigation_plan_screen.dart';
import 'presentation/today/irrigation_today_screen.dart';

abstract final class IrrigationRoutes {
  static const today = IrrigationPaths.today;
  static const ops = IrrigationPaths.ops;
  static const ledger = IrrigationPaths.ledger;
  static const plan = IrrigationPaths.plan;
}

final FeatureModule irrigationFeature = FeatureModule(
  id: 'irrigation',
  routes: [
    AppRoute(
      path: IrrigationRoutes.today,
      titleAr: 'هل أروي اليوم؟',
      icon: Icons.water_drop_rounded,
      menu: const MenuEntry(MenuSection.operations, order: 25),
      builder: (_, args) =>
          IrrigationTodayScreen(initialFieldId: args['field_id']),
    ),
    AppRoute(
      path: IrrigationRoutes.ops,
      titleAr: 'الريّ التشغيليّ',
      icon: Icons.water_drop_outlined,
      menu: const MenuEntry(MenuSection.operations, order: 30),
      builder: (_, _) => const IrrigationOpsScreen(),
    ),
    AppRoute(
      path: IrrigationRoutes.ledger,
      titleAr: 'دفتر المياه',
      icon: Icons.menu_book_rounded,
      builder: (_, args) {
        final fieldId = args['field_id'];
        if (fieldId == null || fieldId.isEmpty) {
          return const Scaffold(
            body: EmptyState(
              message: 'اختر حقلاً من شاشة «هل أروي اليوم؟» لفتح دفتر مياهه.',
              icon: Icons.menu_book_rounded,
            ),
          );
        }
        return WaterLedgerScreen(
          fieldId: fieldId,
          fieldName: args['field_name'],
          areaHa: num.tryParse(args['area_ha'] ?? ''),
        );
      },
    ),
    AppRoute(
      path: IrrigationRoutes.plan,
      titleAr: 'خطّة ريّ افتراضيّة',
      icon: Icons.calendar_month_rounded,
      menu: const MenuEntry(MenuSection.operations, order: 35),
      builder: (_, _) => const IrrigationPlanScreen(),
    ),
  ],
);
