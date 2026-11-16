// SAHOOL — features/field_plans/field_plans_routes.dart
// وحدة «خطط الحقل»: الوصفة وخطّة أخذ العيّنات، مقروءتان دون اتّصال من كاش
// مشفَّر منطَّق بالمستأجِر+المستخدم (core/offline/offline_read_cache.dart).
//
// الروابط العميقة: `/field-plans/recipes?field_id=<id>&field_name=<name>`
// و`/field-plans/scan-plan?field_id=<id>&field_name=<name>`. بلا field_id تعرض
// الشاشة قائمة الحقول.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/offline/offline_read_cache.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/field_plan_screens.dart';

abstract final class FieldPlansRoutes {
  static const recipes = '/field-plans/recipes';
  static const scanPlan = '/field-plans/scan-plan';

  static String recipesFor(String fieldId) =>
      '$recipes?field_id=${Uri.encodeQueryComponent(fieldId)}';
  static String scanPlanFor(String fieldId) =>
      '$scanPlan?field_id=${Uri.encodeQueryComponent(fieldId)}';
}

final FeatureModule fieldPlansFeature = FeatureModule(
  id: 'field_plans',
  routes: [
    AppRoute(
      path: FieldPlansRoutes.recipes,
      titleAr: 'وصفات الحقل',
      icon: Icons.science_outlined,
      menu: const MenuEntry(MenuSection.cropHealth, order: 32),
      builder: (_, args) => RecipeScreen(
        fieldId: args['field_id'],
        fieldName: args['field_name'],
      ),
    ),
    AppRoute(
      path: FieldPlansRoutes.scanPlan,
      titleAr: 'خطّة أخذ العيّنات',
      icon: Icons.place_outlined,
      menu: const MenuEntry(MenuSection.cropHealth, order: 34),
      builder: (_, args) => ScanPlanScreen(
        fieldId: args['field_id'],
        fieldName: args['field_name'],
      ),
    ),
  ],
  // الكاش يخصّ الحساب: يُمسَح كلّه (المدخلات + مفاتيح التشفير) عند الخروج.
  // تبديل المستأجِر دون خروج يمسحه الكاش نفسه عند أوّل وصول بنطاق جديد.
  onSessionEnd: (_) => OfflineReadCache.instance.clear(),
);
