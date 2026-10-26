// SAHOOL — features/realtime/realtime_routes.dart
// المكالمة الصوتيّة الحيّة لحقل. الرابط العميق: /realtime?field_id=<id>.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/route_pages.dart';

import 'realtime_screen.dart';

abstract final class RealtimeRoutes {
  static const call = '/realtime';
}

final FeatureModule realtimeFeature = FeatureModule(
  id: 'realtime',
  routes: [
    AppRoute(
      path: RealtimeRoutes.call,
      titleAr: 'مكالمة حيّة',
      icon: Icons.call_outlined,
      builder: (_, args) {
        final id = args['field_id'];
        return (id == null || id.isEmpty)
            ? const MissingRouteParamPage(param: 'field_id')
            : RealtimeScreen(fieldId: id);
      },
    ),
  ],
);
