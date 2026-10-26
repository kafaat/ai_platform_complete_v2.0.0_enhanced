// SAHOOL — features/field_forms/field_forms_routes.dart
// نماذج الحقل الميدانيّة لحقل محدّد. الرابط العميق: /field-forms?field_id=<id>.
// عند الخروج يتوقّف التصريف ويُسقَط عميل الجلسة؛ الطابور لا يُحذف (عمل ميدانيّ لم
// يُرسَل) ويُصرَّف فقط تحت مستأجِره.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/route_pages.dart';

import 'data/field_forms_coordinator.dart';
import 'presentation/field_forms_list_screen.dart';

abstract final class FieldFormsRoutes {
  static const list = '/field-forms';
}

final FeatureModule fieldFormsFeature = FeatureModule(
  id: 'field_forms',
  routes: [
    AppRoute(
      path: FieldFormsRoutes.list,
      titleAr: 'نماذج الحقل',
      icon: Icons.assignment_outlined,
      builder: (_, args) {
        final id = args['field_id'];
        return (id == null || id.isEmpty)
            ? const MissingRouteParamPage(param: 'field_id')
            : FieldFormsListScreen(fieldId: id);
      },
    ),
  ],
  onSessionEnd: (_) => FieldFormsCoordinator.instance.onSessionEnd(),
);
