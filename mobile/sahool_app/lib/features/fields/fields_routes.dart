// SAHOOL — features/fields/fields_routes.dart
// مسارات ميزة الحقول: القائمة (تبويب «الحقول»)، معالج الإنشاء، ومساحة عمل الحقل.
// يملكها وكيل ميزة الحقول وحده.
//
// مساحة العمل في lib/screens/field_workspace_screen.dart — مسار مُثبَّت تقرؤه
// اختبارات CI خارج التطبيق. الاسم القديم 'field_workspace' يبقى اسماً بديلاً لأنّ
// بطاقات الحقول تدفعه بـpushNamed('field_workspace', arguments: id|Map).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/screens/field_workspace_screen.dart';

import 'presentation/field_create_wizard.dart';
import 'presentation/fields_screen.dart';

abstract final class FieldsRoutes {
  static const fields = '/fields';
  static const create = '/fields/new';

  /// الرابط العميق: `/fields/workspace?field_id=<id>`
  static const workspace = '/fields/workspace';
}

final FeatureModule fieldsFeature = FeatureModule(
  id: 'fields',
  routes: [
    AppRoute(
      path: FieldsRoutes.fields,
      titleAr: 'الحقول',
      icon: Icons.layers_outlined,
      builder: (_, _) => const FieldsScreen(),
    ),
    AppRoute(
      path: FieldsRoutes.create,
      titleAr: 'إضافة حقل',
      icon: Icons.add_location_alt_outlined,
      allowedRoles: RouteRoles.editors,
      builder: (_, _) => const FieldCreateWizard(),
    ),
    AppRoute(
      path: FieldsRoutes.workspace,
      titleAr: 'مساحة عمل الحقل',
      icon: Icons.dashboard_customize_outlined,
      aliases: const [FieldWorkspaceScreen.routeName],
      // معرّف الرابط العميق إن وُجد؛ وإلّا تقرأ الشاشة arguments بنفسها
      // (String معرّف، Map كائن الحقل، أو FieldWorkspaceArgs).
      builder: (_, args) =>
          FieldWorkspaceScreen(fieldId: args.query['field_id']),
    ),
  ],
);
