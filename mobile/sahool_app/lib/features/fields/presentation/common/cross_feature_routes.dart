// SAHOOL — features/fields/presentation/common/cross_feature_routes.dart
// مسارات ميزات أخرى تفتحها شاشات الحقول (الإجراءات السريعة، مبدّل الخريطة).
// أسماء مسارات نصّيّة لا استيراد لشاشاتها: كلّ ميزة تملك مسارها في ملفّ
// مساراتها. إن لم تُسجَّل الميزة بعد يُقال ذلك بصدق بدل صفحة «غير موجود».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_router.dart';

abstract final class CrossFeatureRoutes {
  /// خريطة «حقولي» (ميزة maps).
  static const maps = '/maps';

  /// تسجيل كشف ميدانيّ جديد (ميزة scouting) — يأخذ field_id.
  static const scoutingNew = '/scouting/new';

  /// تسجيل نشاط سريع (ميزة activities) — يأخذ field_id.
  static const activityNew = '/activities/new';

  /// الريّ التشغيليّ (ميزة irrigation).
  static const irrigation = '/irrigation/ops';

  /// المستشار (ميزة advisor) — يأخذ field_id.
  static const advisor = '/advisor';

  /// المهامّ (ميزة tasks) — يأخذ field_id.
  static const tasks = '/tasks';

  /// المواسم والمراحل (ميزة crop_season) — يأخذ field_id.
  static const cropSeason = '/crop-season';

  /// أخذ العيّنات (ميزة lab_sampling) — يأخذ field_id.
  static const labSampling = '/lab-sampling';

  /// شاشة الأقمار (ميزة satellite) — تأخذ field_id.
  static const satellite = '/satellite';
}

/// هل المسار مسجَّل في الموجِّه؟ قابل للاستبدال في الاختبارات.
typedef RouteExists = bool Function(String path);

bool _routerHas(String path) => AppRouter.instance.match(path) != null;

/// المصدر الافتراضيّ لوجود المسار (الموجِّه الحقيقيّ).
RouteExists routeExists = _routerHas;

const String kFeatureNotAvailableAr = 'هذه الميزة غير متاحة بعد في التطبيق.';

/// يفتح مسار ميزة أخرى بمعاملات استعلام، أو يقول بصدق إنّها غير متاحة بعد.
Future<T?> openFeatureRoute<T extends Object?>(
  BuildContext context,
  String path, {
  Map<String, String> query = const {},
}) async {
  if (!routeExists(path)) {
    ScaffoldMessenger.maybeOf(
      context,
    )?.showSnackBar(const SnackBar(content: Text(kFeatureNotAvailableAr)));
    return null;
  }
  final name = query.isEmpty
      ? path
      : Uri(path: path, queryParameters: query).toString();
  return Navigator.of(context).pushNamed<T>(name);
}
