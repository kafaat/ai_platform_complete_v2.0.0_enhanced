// قراءة الحمولات: الغائب يبقى null (يُعرض «غير مقيس»)، لا صفر ولا «null».
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/dashboard/data/today_models.dart';

import 'today_fixtures.dart';

void main() {
  test('real kpis are read by id/name_ar/value/unit', () {
    final k = TodayKpi.listFrom(realDashboard()['kpis']);
    expect(k.map((x) => x.id), [
      'fields_total',
      'area_total',
      'active_seasons',
      'open_alerts',
    ]);
    expect(k[1].value, 12.75);
    expect(k[1].unit, 'هـ');
  });

  test('missing kpis fall back to the four expected tiles with no value', () {
    for (final raw in [null, <dynamic>[], 'garbage']) {
      final k = TodayKpi.listFrom(raw);
      expect(k, hasLength(4));
      expect(k.every((x) => x.value == null), isTrue);
    }
    final partial = TodayKpi.listFrom([
      {'id': 'area_total'},
    ]);
    expect(partial.single.labelAr, 'إجماليّ المساحة');
    expect(partial.single.value, isNull);
  });

  test('alerts sort critical first and read title_ar/message_ar', () {
    final a = TodayAlert.listFrom(realDashboard()['alerts']);
    expect(a.first.id, 'alr_frost');
    expect(a.first.displayTitle, 'خطر صقيع الليلة');
    expect(a.first.messageAr, isNull);
    // بلا title_ar: ترجمة النوع لا «—».
    final untitled = TodayAlert.listFrom([
      {'alert_id': 'x', 'alert_type': 'heat_stress', 'severity': 'info'},
    ]);
    expect(untitled.single.displayTitle, 'إجهاد حراريّ');
  });

  test('field area 0 or missing is not measured; centroid from polygon', () {
    final f = TodayField.listFrom(realDashboard()['fields_summary']);
    expect(f[0].areaHa, 4.5);
    expect(f[2].areaHa, isNull);
    expect(f[2].crop, isNull);
    final c = f[0].centroid!;
    expect(c.$1, closeTo(15.1, 1e-9));
    expect(c.$2, closeTo(44.1, 1e-9));
    expect(f[1].centroid, isNull);
  });

  test(
    "today's tasks: due/overdue by priority, then undated; no future/done",
    () {
      final all = TodayTask.listFrom(realTasks()['tasks']);
      final today = TodayTask.forToday(all, kNow);
      expect(today.map((t) => t.id), ['t_late', 't_today']);
      expect(today.first.isOverdue(kNow), isTrue);
      expect(today.last.isOverdue(kNow), isFalse);
    },
  );

  test('weather sample keys and suitability are read as sent', () {
    final w = TodayWeather.from(realWeather(), 'مزرعة الوادي');
    expect(w.tempC, 24.4);
    expect(w.windKmh, 9);
    expect(w.spraying, 'optimal');
    expect(w.stale, isFalse);
    final empty = TodayWeather.from(const {}, 'x');
    expect(empty.tempC, isNull);
    expect(empty.spraying, isNull);
  });
}
