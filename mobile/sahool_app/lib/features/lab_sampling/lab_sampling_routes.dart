// SAHOOL — features/lab_sampling/lab_sampling_routes.dart
// وحدة ميزة «عيّنات المختبر». يملكها وكيل الميزة.
//
// الرابط العميق: `/lab-samples?field_id=<id>` (مساحة عمل الحقل تفتحه بمعرّف الحقل).
// بلا field_id تعرض الشاشة قائمة الحقول للاختيار.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/lab_samples_screen.dart';

abstract final class LabSamplingRoutes {
  /// `/lab-samples?field_id=<id>&field_name=<name>&area_ha=<ha>`
  static const samples = '/lab-samples';

  static String forField(String fieldId) =>
      '$samples?field_id=${Uri.encodeQueryComponent(fieldId)}';
}

final FeatureModule labSamplingFeature = FeatureModule(
  id: 'lab_sampling',
  routes: [
    AppRoute(
      path: LabSamplingRoutes.samples,
      titleAr: 'عيّنات المختبر',
      icon: Icons.science_outlined,
      menu: const MenuEntry(MenuSection.cropHealth, order: 30),
      builder: (_, args) => LabSamplesScreen(
        fieldId: args['field_id'],
        fieldName: args['field_name'],
        areaHa: double.tryParse(args['area_ha'] ?? ''),
      ),
    ),
  ],
);
