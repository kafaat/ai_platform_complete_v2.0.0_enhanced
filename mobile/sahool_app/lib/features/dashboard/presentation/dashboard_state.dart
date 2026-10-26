// SAHOOL — features/dashboard/presentation/dashboard_state.dart
// حالة شاشة «اليوم». الأقسام تُحمَّل تدريجيّاً: اللوحة أوّلاً (هي ما يحدّد
// الشاشة)، ثمّ المهامّ والمزارع، ثمّ ما يخصّ المزرعة المختارة (حقولها، طابور
// أولويّاتها، طقسها). كلّ قسم يحمل حالته الصادقة: تحميل / جاهز / فشل / غير متاح.
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/dashboard/data/today_models.dart';

sealed class SectionState<T> {
  const SectionState();
}

class SectionLoading<T> extends SectionState<T> {
  const SectionLoading();
}

class SectionReady<T> extends SectionState<T> {
  const SectionReady(this.data, {this.fromSnapshot = false});
  final T data;

  /// من اللقطة المحفوظة لا من الخادم الآن.
  final bool fromSnapshot;
}

class SectionFailed<T> extends SectionState<T> {
  const SectionFailed(this.error);
  final ApiException error;
}

/// لا مصدر لهذا القسم في هذا السياق (مثلاً لا إحداثيّات للطقس).
class SectionUnavailable<T> extends SectionState<T> {
  const SectionUnavailable(this.reasonAr);
  final String reasonAr;
}

enum DashboardStatus { initial, loading, ready, failed }

class DashboardState {
  const DashboardState({
    this.status = DashboardStatus.initial,
    this.error,
    this.kpis = const [],
    this.alerts = const [],
    this.fields = const [],
    this.noteAr,
    this.fetchedAt,
    this.refreshing = false,
    this.refreshError,
    this.fromSnapshot = false,
    this.tasks = const SectionLoading(),
    this.farms = const SectionLoading(),
    this.selectedFarmId,
    this.farmFieldIds,
    this.priority = const SectionLoading(),
    this.weather = const SectionLoading(),
    this.ackBusy = const {},
  });

  final DashboardStatus status;

  /// فشل التحميل الأوّل بلا لقطة محفوظة.
  final ApiException? error;

  final List<TodayKpi> kpis;
  final List<TodayAlert> alerts;
  final List<TodayField> fields;
  final String? noteAr;

  /// وقت جلب حمولة اللوحة المعروضة من الخادم («آخر تحديث»).
  final DateTime? fetchedAt;
  final bool refreshing;

  /// فشل آخر تحديث بينما تُعرَض بيانات أقدم (لقطة أو ما سبق عرضه).
  final ApiException? refreshError;

  /// البيانات المعروضة من اللقطة المحفوظة على الجهاز.
  final bool fromSnapshot;

  final SectionState<List<TodayTask>> tasks;
  final SectionState<List<TodayFarm>> farms;
  final String? selectedFarmId;

  /// حقول المزرعة المختارة؛ null = كلّ الحقول (لا مزرعة مختارة أو لم تُحمَّل).
  final Set<String>? farmFieldIds;
  final SectionState<List<PriorityItem>> priority;
  final SectionState<TodayWeather> weather;
  final Set<String> ackBusy;

  bool get hasData => fetchedAt != null;

  /// المعروض قديم: لقطة محفوظة أو فشل التحديث الأخير.
  bool get isStale => fromSnapshot || refreshError != null;

  TodayFarm? get selectedFarm {
    final f = farms;
    if (f is! SectionReady<List<TodayFarm>>) return null;
    for (final farm in f.data) {
      if (farm.id == selectedFarmId) return farm;
    }
    return null;
  }

  bool _inScope(String? fieldId) {
    final ids = farmFieldIds;
    if (ids == null) return true;
    return fieldId != null && ids.contains(fieldId);
  }

  String? fieldName(String? fieldId) {
    if (fieldId == null) return null;
    for (final f in fields) {
      if (f.id == fieldId) return f.name;
    }
    return null;
  }

  List<TodayAlert> get visibleAlerts => [
    for (final a in alerts)
      if (_inScope(a.fieldId)) a,
  ];

  List<TodayTask> todayTasks(DateTime today) {
    final t = tasks;
    if (t is! SectionReady<List<TodayTask>>) return const [];
    return TodayTask.forToday([
      for (final x in t.data)
        if (_inScope(x.fieldId)) x,
    ], today);
  }

  /// حقول النطاق مرتّبة بالأولويّة: أشدّ عنصر مفتوح (تنبيه/مهمّة) أوّلاً، ثمّ
  /// عدد العناصر، ثمّ الحقول بلا موسم نشط، ثمّ الاسم. المصدر: طابور أولويّات
  /// المزرعة إن حُمِّل، وإلّا التنبيهات والمهامّ المفتوحة نفسها — لا مؤشّر صحّة
  /// مُخترَع.
  List<FieldPriority> get fieldsByPriority {
    final byField = <String, List<String?>>{};
    final p = priority;
    if (p is SectionReady<List<PriorityItem>>) {
      for (final i in p.data) {
        if (i.fieldId == null) continue;
        byField.putIfAbsent(i.fieldId!, () => []).add(i.severity);
      }
    } else {
      for (final a in alerts) {
        if (a.fieldId == null) continue;
        byField.putIfAbsent(a.fieldId!, () => []).add(a.severity);
      }
      final t = tasks;
      if (t is SectionReady<List<TodayTask>>) {
        for (final x in t.data) {
          if (!x.isOpen || x.fieldId == null) continue;
          final sev = switch (x.priority) {
            1 => 'high',
            2 => 'medium',
            _ => 'low',
          };
          byField.putIfAbsent(x.fieldId!, () => []).add(sev);
        }
      }
    }
    final alertCounts = <String, int>{};
    for (final a in alerts) {
      if (a.fieldId != null) {
        alertCounts[a.fieldId!] = (alertCounts[a.fieldId!] ?? 0) + 1;
      }
    }
    final rows = [
      for (final f in fields)
        if (_inScope(f.id))
          FieldPriority(
            field: f,
            openItems: byField[f.id]?.length ?? 0,
            openAlerts: alertCounts[f.id] ?? 0,
            topRank: (byField[f.id] ?? const <String?>[])
                .map(TodayAlert.severityRankOf)
                .fold<int>(9, (m, r) => r < m ? r : m),
          ),
    ];
    rows.sort((a, b) {
      var c = a.topRank.compareTo(b.topRank);
      if (c != 0) return c;
      c = b.openItems.compareTo(a.openItems);
      if (c != 0) return c;
      final aa = a.field.hasActiveSeason == true ? 1 : 0;
      final bb = b.field.hasActiveSeason == true ? 1 : 0;
      c = aa.compareTo(bb);
      if (c != 0) return c;
      return a.field.name.compareTo(b.field.name);
    });
    return rows;
  }

  DashboardState copyWith({
    DashboardStatus? status,
    ApiException? error,
    List<TodayKpi>? kpis,
    List<TodayAlert>? alerts,
    List<TodayField>? fields,
    String? noteAr,
    DateTime? fetchedAt,
    bool? refreshing,
    ApiException? refreshError,
    bool clearRefreshError = false,
    bool? fromSnapshot,
    SectionState<List<TodayTask>>? tasks,
    SectionState<List<TodayFarm>>? farms,
    String? selectedFarmId,
    bool clearSelectedFarm = false,
    Set<String>? farmFieldIds,
    bool clearFarmFieldIds = false,
    SectionState<List<PriorityItem>>? priority,
    SectionState<TodayWeather>? weather,
    Set<String>? ackBusy,
  }) => DashboardState(
    status: status ?? this.status,
    error: error ?? this.error,
    kpis: kpis ?? this.kpis,
    alerts: alerts ?? this.alerts,
    fields: fields ?? this.fields,
    noteAr: noteAr ?? this.noteAr,
    fetchedAt: fetchedAt ?? this.fetchedAt,
    refreshing: refreshing ?? this.refreshing,
    refreshError: clearRefreshError
        ? null
        : (refreshError ?? this.refreshError),
    fromSnapshot: fromSnapshot ?? this.fromSnapshot,
    tasks: tasks ?? this.tasks,
    farms: farms ?? this.farms,
    selectedFarmId: clearSelectedFarm
        ? null
        : (selectedFarmId ?? this.selectedFarmId),
    farmFieldIds: clearFarmFieldIds
        ? null
        : (farmFieldIds ?? this.farmFieldIds),
    priority: priority ?? this.priority,
    weather: weather ?? this.weather,
    ackBusy: ackBusy ?? this.ackBusy,
  );
}

class FieldPriority {
  const FieldPriority({
    required this.field,
    required this.openItems,
    required this.openAlerts,
    required this.topRank,
  });

  final TodayField field;

  /// تنبيهات + مهامّ مفتوحة على الحقل.
  final int openItems;
  final int openAlerts;

  /// 0 حرج … 3 منخفض؛ 9 = لا عناصر مفتوحة.
  final int topRank;
}
