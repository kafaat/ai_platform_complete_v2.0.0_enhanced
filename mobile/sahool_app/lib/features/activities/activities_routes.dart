// SAHOOL — features/activities/activities_routes.dart
// وحدة ميزة «الأنشطة»: موجز أنشطة المزرعة، أنشطة حقل وخطّه الزمنيّ، والتسجيل
// السريع. يملكها وكيل الميزة.
//
// روابط لبقيّة الميزات (مساحة عمل الحقل مثلاً):
//   /activities/field?field_id=<id>&field_name=<اسم>
//   /activities/log?field_id=<id>&field_name=<اسم>
// أو برمجيّاً: showActivityLogSheet(context, fieldId: ..., fieldName: ...).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import 'data/activity_writer.dart';
import 'presentation/activity_log_sheet.dart';
import 'presentation/farm_activity_feed_screen.dart';
import 'presentation/field_activities_screen.dart';

abstract final class ActivitiesRoutes {
  static const feed = '/activities';
  static const field = '/activities/field';
  static const log = '/activities/log';
}

Widget _missingField(String title) => AppScaffold(
  title: title,
  body: const EmptyState(
    title: 'لم يُحدَّد حقل',
    message: 'الرابط لا يحمل معرّف حقل (field_id).',
    icon: Icons.link_off_rounded,
  ),
);

final FeatureModule activitiesFeature = FeatureModule(
  id: 'activities',
  // النسخ المحلّيّة المنتظرة تخصّ المستخدم المنتهية جلسته؛ العمليّات نفسها تبقى
  // في صندوق الإرسال (يملكه وكيل المزامنة ويرشّحها بالمستأجر).
  onSessionEnd: (_) async => PendingActivities.instance.clear(),
  routes: [
    AppRoute(
      path: ActivitiesRoutes.feed,
      titleAr: 'سجلّ الأنشطة',
      icon: Icons.event_note_outlined,
      menu: const MenuEntry(MenuSection.operations, order: 20),
      builder: (_, _) => const FarmActivityFeedScreen(),
    ),
    AppRoute(
      path: ActivitiesRoutes.field,
      titleAr: 'أنشطة الحقل',
      icon: Icons.timeline_outlined,
      builder: (_, args) {
        final id = args['field_id'];
        if (id == null || id.isEmpty) return _missingField('أنشطة الحقل');
        return FieldActivitiesScreen(
          fieldId: id,
          fieldName: args['field_name'],
        );
      },
    ),
    AppRoute(
      path: ActivitiesRoutes.log,
      titleAr: 'تسجيل نشاط',
      icon: Icons.add_task_rounded,
      allowedRoles: RouteRoles.editors,
      builder: (context, args) {
        final id = args['field_id'];
        if (id == null || id.isEmpty) return _missingField('تسجيل نشاط');
        return AppScaffold(
          title: 'تسجيل نشاط',
          body: ActivityLogSheet(
            fieldId: id,
            fieldName: args['field_name'],
            onDone: (o) => ScaffoldMessenger.of(
              context,
            ).showSnackBar(SnackBar(content: Text(activityOutcomeMessage(o)))),
          ),
        );
      },
    ),
  ],
);
