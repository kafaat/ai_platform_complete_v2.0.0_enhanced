// SAHOOL — features/fields/presentation/common/cross_feature_routes.dart
// مسارات ميزات أخرى تفتحها شاشات الحقول (الإجراءات السريعة، مبدّل الخريطة).
// أسماء مسارات نصّيّة لا استيراد لشاشاتها: كلّ ميزة تملك مسارها في ملفّ
// مساراتها. إن لم تُسجَّل الميزة بعد يُقال ذلك بصدق بدل صفحة «غير موجود».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_router.dart';

abstract final class CrossFeatureRoutes {
  /// خريطة «حقولي» (ميزة maps: `MapsRoutes.farmMap`).
  static const maps = '/maps/farm';

  /// التقاط مشاهدة ميدانيّة (ميزة scouting: `ScoutingRoutes.capture`) — يأخذ field_id.
  static const scoutingNew = '/scouting/capture';

  /// تسجيل نشاط سريع (ميزة activities: `ActivitiesRoutes.log`) — يأخذ
  /// field_id و field_name.
  static const activityNew = '/activities/log';

  /// «هل أروي اليوم؟» لحقل (ميزة irrigation: `IrrigationRoutes.today`) — يأخذ field_id.
  static const irrigationToday = '/irrigation/today';

  /// الريّ التشغيليّ: الصمّامات والجداول على مستوى المزرعة
  /// (`IrrigationRoutes.ops`) — لا يأخذ field_id.
  static const irrigationOps = '/irrigation/ops';

  /// المستشار (ميزة advisor) — يأخذ field_id و field_name.
  static const advisor = '/advisor';

  /// المهامّ (ميزة tasks) — يأخذ field_id مرشِّحاً أوّليّاً.
  static const tasks = '/tasks';

  /// المواسم والأطوار (ميزة crop_season: `CropSeasonRoutes.seasons`) — يأخذ field_id.
  static const cropSeason = '/seasons';

  /// عيّنات المختبر (ميزة lab_sampling: `LabSamplingRoutes.samples`) — يأخذ field_id.
  static const labSampling = '/lab-samples';

  /// شاشة الأقمار (ميزة satellite) — تأخذ field_id.
  static const satellite = '/satellite';

  /// تنبيهات حقل (ميزة alerts: `AlertsPaths.fieldAlerts`) — يأخذ field_id.
  static const alertsField = '/alerts/field';

  /// الطقس ونوافذ العمليّات (ميزة weather: `WeatherPaths.weather`) — يأخذ field_id.
  static const weather = '/weather';

  /// كلّ المسارات أعلاه (يتحقّق الاختبار أنّ كلّاً منها مسجَّل في الموجِّه).
  static const all = <String>[
    maps,
    scoutingNew,
    activityNew,
    irrigationToday,
    irrigationOps,
    advisor,
    tasks,
    cropSeason,
    labSampling,
    satellite,
    alertsField,
    weather,
  ];
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
