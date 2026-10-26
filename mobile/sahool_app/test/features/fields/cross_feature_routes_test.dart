// روابط مساحة عمل الحقل إلى الميزات الأخرى: كلّ ثابت في CrossFeatureRoutes
// يجب أن يطابق مساراً مسجَّلاً في الموجِّه الحقيقيّ (كانت /scouting/new و
// /activities/new و/crop-season و/lab-sampling و/maps غير موجودة فتظهر
// «غير متاحة بعد» لميزات مبنيّة)، وكلّ شاشة مستهدفة تقرأ field_id الذي يمرّره
// الحقل فعلاً (لا تتجاهله وتفتح بلا سياق).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/activities/presentation/activity_log_sheet.dart';
import 'package:sahool_app/features/advisor/presentation/advisor_screen.dart';
import 'package:sahool_app/features/alerts/presentation/alerts_screen.dart';
import 'package:sahool_app/features/crop_season/presentation/seasons_screen.dart';
import 'package:sahool_app/features/fields/presentation/common/cross_feature_routes.dart';
import 'package:sahool_app/features/irrigation/presentation/today/irrigation_today_screen.dart';
import 'package:sahool_app/features/lab_sampling/presentation/lab_samples_screen.dart';
import 'package:sahool_app/features/satellite/presentation/satellite_screen.dart';
import 'package:sahool_app/features/scouting/presentation/scouting_widgets.dart';
import 'package:sahool_app/features/tasks/presentation/tasks_screen.dart';
import 'package:sahool_app/features/weather/presentation/weather_screen.dart';

void main() {
  final router = AppRouter.instance;

  test('every CrossFeatureRoutes constant is a registered route', () {
    for (final path in CrossFeatureRoutes.all) {
      expect(router.match(path), isNotNull, reason: '$path is not registered');
    }
    // الثوابت كلّها مُدرجة في all (لا ثابت جديد يفلت من الفحص).
    expect(CrossFeatureRoutes.all.toSet(), hasLength(12));
  });

  testWidgets('each target screen reads the field_id the workspace passes', (
    t,
  ) async {
    late BuildContext ctx;
    await t.pumpWidget(
      Builder(
        builder: (c) {
          ctx = c;
          return const SizedBox();
        },
      ),
    );
    const args = RouteArgs(query: {'field_id': 'f1', 'field_name': 'حقل أ'});
    Widget build(String path) => router.match(path)!.builder(ctx, args);

    final checks = <String, String? Function(Widget)>{
      CrossFeatureRoutes.scoutingNew: (w) =>
          (w as ScoutingFieldGate).initialFieldId,
      CrossFeatureRoutes.activityNew: (w) =>
          ((w as AppScaffold).body as ActivityLogSheet).fieldId,
      CrossFeatureRoutes.irrigationToday: (w) =>
          (w as IrrigationTodayScreen).initialFieldId,
      CrossFeatureRoutes.advisor: (w) => (w as AdvisorScreen).fieldId,
      CrossFeatureRoutes.tasks: (w) => (w as TasksScreen).initialFieldId,
      CrossFeatureRoutes.cropSeason: (w) => (w as CropSeasonScreen).fieldId,
      CrossFeatureRoutes.labSampling: (w) => (w as LabSamplesScreen).fieldId,
      CrossFeatureRoutes.satellite: (w) =>
          (w as SatelliteScreen).initialFieldId,
      CrossFeatureRoutes.alertsField: (w) => (w as AlertsScreen).fieldId,
      CrossFeatureRoutes.weather: (w) => (w as WeatherScreen).fieldId,
    };
    for (final e in checks.entries) {
      expect(e.value(build(e.key)), 'f1', reason: '${e.key} drops field_id');
    }
    final log = (build(CrossFeatureRoutes.activityNew) as AppScaffold).body;
    expect((log as ActivityLogSheet).fieldName, 'حقل أ');
    expect(
      (build(CrossFeatureRoutes.advisor) as AdvisorScreen).fieldName,
      'حقل أ',
    );
  });
}
