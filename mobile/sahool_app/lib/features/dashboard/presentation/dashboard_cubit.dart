// SAHOOL — features/dashboard/presentation/dashboard_cubit.dart
// منطق شاشة «اليوم»: تحميل واحد مُدمَج (لا طلبان متزامنان لنفس الشاشة، واللوحة
// نفسها مدموجة مع الغلاف عبر DashboardApi)، سحب للتحديث، لقطة محفوظة عند تعذّر
// الشبكة مع عمرها، اختيار المزرعة مع رمز طلب يمنع ردّاً متأخّراً لمزرعة سابقة من
// الكتابة فوق الحاليّة، وإقرار التنبيه بمفتاح idempotency ثابت للنيّة الواحدة.
import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_api.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_snapshot_store.dart';
import 'package:sahool_app/features/dashboard/data/today_models.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/tasks/data/tasks_api.dart';

import 'dashboard_state.dart';

typedef _Result<T> = (T?, ApiException?);

class DashboardCubit extends Cubit<DashboardState> {
  DashboardCubit({
    required DashboardApi api,
    required TasksApi tasksApi,
    required FarmsApi farmsApi,
    DashboardSnapshotStore? snapshots,
    Stream<Object?>? alertEvents,
    this.eventDebounce = const Duration(seconds: 2),
  }) : _api = api,
       _tasksApi = tasksApi,
       _farmsApi = farmsApi,
       _snapshots = snapshots ?? MemoryDashboardSnapshotStore(),
       super(const DashboardState()) {
    _eventSub = alertEvents?.listen((_) => _onAlertEvent());
  }

  final DashboardApi _api;
  final TasksApi _tasksApi;
  final FarmsApi _farmsApi;
  final DashboardSnapshotStore _snapshots;
  final Duration eventDebounce;
  StreamSubscription<Object?>? _eventSub;
  Timer? _eventTimer;

  Future<void>? _loading;
  int _scopeGen = 0;
  final Map<String, IdempotencyKey> _ackKeys = {};

  /// تحميل الشاشة. نداءات متزامنة تنتظر التحميل الجاري نفسه (لا طلب ثانٍ).
  /// [force] يتجاوز كاش الذاكرة (سحب للتحديث).
  Future<void> load({bool force = false}) =>
      _loading ??= _load(force).whenComplete(() => _loading = null);

  Future<void> refresh() => load(force: true);

  static Future<_Result<T>> _guard<T>(Future<T> Function() body) async {
    try {
      return (await body(), null);
    } catch (e) {
      return (null, ApiException.from(e));
    }
  }

  /// أخطاء يُعرض معها آخر ما عُرِف: انقطاع/مهلة/خادم معطّل. أمّا 401/403/404
  /// فتُعرض كما هي (لقطة قديمة لا تُجيب عن «لا صلاحيّة»).
  static bool _staleWorthy(ApiException e) =>
      e.isConnectivity ||
      e.kind == ApiErrorKind.unavailable ||
      e.kind == ApiErrorKind.server ||
      e.kind == ApiErrorKind.rateLimited;

  Future<void> _load(bool force) async {
    if (isClosed) return;
    final hadData = state.hasData;
    emit(
      hadData
          ? state.copyWith(refreshing: true)
          : state.copyWith(status: DashboardStatus.loading),
    );
    final scope = _api.scopeKey;
    final results = await Future.wait<Object?>([
      _guard(() => _api.fetchDashboard(forceRefresh: force)),
      _guard(_tasksApi.fetchTasks),
      _guard(_farmsApi.listFarms),
    ]);
    if (isClosed) return;
    final dash = results[0]! as _Result<DashboardFetch>;
    final tasks = results[1]! as _Result<List<Map<String, dynamic>>>;
    final farms = results[2]! as _Result<List<Map<String, dynamic>>>;

    final dashErr = dash.$2;
    if (dashErr == null) {
      final fetch = dash.$1!;
      final previous = await _snapshots.read(scope);
      if (isClosed) return;
      await _snapshots.write(scope, {
        'dashboard': fetch.data,
        'tasks': tasks.$1 ?? previous?.data['tasks'],
        'farms': farms.$1 ?? previous?.data['farms'],
      }, fetch.fetchedAt);
      if (isClosed) return;
      emit(
        _withDashboard(state, fetch.data).copyWith(
          status: DashboardStatus.ready,
          fetchedAt: fetch.fetchedAt,
          refreshing: false,
          clearRefreshError: true,
          fromSnapshot: false,
          tasks: _section(tasks, TodayTask.listFrom, previous?.data['tasks']),
          farms: _section(farms, TodayFarm.listFrom, previous?.data['farms']),
        ),
      );
    } else if (hadData) {
      // التحديث فشل وما يُعرض باقٍ: نُبقيه ونقول إنّه قديم ولماذا.
      emit(
        state.copyWith(
          refreshing: false,
          refreshError: dashErr,
          tasks: tasks.$2 == null
              ? SectionReady(TodayTask.listFrom(tasks.$1))
              : null,
          farms: farms.$2 == null
              ? SectionReady(TodayFarm.listFrom(farms.$1))
              : null,
        ),
      );
    } else {
      final snap = _staleWorthy(dashErr) ? await _snapshots.read(scope) : null;
      if (isClosed) return;
      final snapDash = snap?.data['dashboard'];
      if (snap != null && snapDash is Map) {
        emit(
          _withDashboard(state, Map<String, dynamic>.from(snapDash)).copyWith(
            status: DashboardStatus.ready,
            fetchedAt: snap.savedAt,
            refreshing: false,
            refreshError: dashErr,
            fromSnapshot: true,
            tasks: _section(tasks, TodayTask.listFrom, snap.data['tasks']),
            farms: _section(farms, TodayFarm.listFrom, snap.data['farms']),
          ),
        );
      } else {
        emit(
          state.copyWith(
            status: DashboardStatus.failed,
            error: dashErr,
            refreshing: false,
          ),
        );
        return;
      }
    }
    await _loadFarmScope(keepSelection: true);
  }

  /// قسم من نتيجة الشبكة، وإلّا من اللقطة (معلَّماً)، وإلّا الفشل كما هو.
  static SectionState<List<T>> _section<T>(
    _Result<List<Map<String, dynamic>>> r,
    List<T> Function(Object?) parse,
    Object? snapshot,
  ) {
    if (r.$2 == null) return SectionReady(parse(r.$1));
    if (_staleWorthy(r.$2!) && snapshot is List) {
      return SectionReady(parse(snapshot), fromSnapshot: true);
    }
    return SectionFailed(r.$2!);
  }

  static DashboardState _withDashboard(
    DashboardState s,
    Map<String, dynamic> data,
  ) => s.copyWith(
    kpis: TodayKpi.listFrom(data['kpis']),
    alerts: TodayAlert.listFrom(data['alerts']),
    fields: TodayField.listFrom(data['fields_summary']),
    noteAr: data['note_ar'] is String ? data['note_ar'] as String : null,
  );

  /// يختار مزرعة (null = كلّ المزارع) ويعيد تحميل ما يخصّها.
  Future<void> selectFarm(String? farmId) async {
    if (farmId == state.selectedFarmId) return;
    emit(
      farmId == null
          ? state.copyWith(clearSelectedFarm: true, clearFarmFieldIds: true)
          : state.copyWith(selectedFarmId: farmId, clearFarmFieldIds: true),
    );
    await _loadFarmScope(keepSelection: false);
  }

  Future<void> _loadFarmScope({required bool keepSelection}) async {
    if (isClosed) return;
    final gen = ++_scopeGen;
    final farmsState = state.farms;
    final farms = farmsState is SectionReady<List<TodayFarm>>
        ? farmsState.data
        : const <TodayFarm>[];
    var selected = state.selectedFarmId;
    if (keepSelection) {
      final stillThere = farms.any((f) => f.id == selected);
      if (!stillThere) selected = farms.length == 1 ? farms.first.id : null;
    }
    emit(
      state.copyWith(
        selectedFarmId: selected,
        clearSelectedFarm: selected == null,
        priority: selected == null
            ? const SectionUnavailable(
                'اختر مزرعة لترتيب حقولها بطابور أولويّات الخادم.',
              )
            : const SectionLoading(),
        weather: const SectionLoading(),
      ),
    );

    final farm = state.selectedFarm;
    final results = await Future.wait<Object?>([
      if (farm != null) ...[
        _guard(() => _api.listFarmFields(farm.id)),
        _guard(() => _api.getFarmPriorityQueue(farm.id)),
      ],
    ]);
    if (isClosed || gen != _scopeGen) return;
    if (farm != null) {
      final ff = results[0]! as _Result<List<Map<String, dynamic>>>;
      final pq = results[1]! as _Result<Map<String, dynamic>>;
      emit(
        state.copyWith(
          farmFieldIds: ff.$2 == null
              ? {
                  for (final r in ff.$1!)
                    if (r['field_id'] != null) '${r['field_id']}',
                }
              : null,
          priority: pq.$2 == null
              ? SectionReady(PriorityItem.listFrom(pq.$1!['items']))
              : SectionFailed(pq.$2!),
        ),
      );
    }
    await _loadWeather(gen);
  }

  /// موقع الطقس: مركز المزرعة المختارة، وإلّا مركز أعلى حقل أولويّةً له هندسة.
  Future<void> _loadWeather(int gen) async {
    final farm = state.selectedFarm;
    (double, double)? point = farm?.centroid;
    String? place = point != null ? farm!.name : null;
    if (point == null) {
      for (final row in state.fieldsByPriority) {
        if (row.field.centroid != null) {
          point = row.field.centroid;
          place = row.field.name;
          break;
        }
      }
    }
    if (point == null) {
      emit(
        state.copyWith(
          weather: const SectionUnavailable(
            'لا إحداثيّات للمزرعة أو الحقول بعد، فلا طقس محلّيّ لعرضه.',
          ),
        ),
      );
      return;
    }
    final r = await _guard(() => _api.getWeatherSummary(point!.$1, point.$2));
    if (isClosed || gen != _scopeGen) return;
    emit(
      state.copyWith(
        weather: r.$2 == null
            ? SectionReady(TodayWeather.from(r.$1!, place!))
            : SectionFailed(r.$2!),
      ),
    );
  }

  /// يُقِرّ تنبيهاً. يعيد الخطأ (لعرضه) أو null عند النجاح. المفتاح ثابت لنيّة
  /// إقرار هذا التنبيه، فإعادة المحاولة بعد ردّ ضائع لا تُكرّر الكتابة.
  Future<ApiException?> acknowledge(String alertId) async {
    if (state.ackBusy.contains(alertId)) return null; // منع الإرسال المزدوج
    emit(state.copyWith(ackBusy: {...state.ackBusy, alertId}));
    final key = _ackKeys.putIfAbsent(alertId, IdempotencyKey.generate);
    try {
      await _api.acknowledgeAlert(alertId, idempotencyKey: key);
      _ackKeys.remove(alertId);
      if (isClosed) return null;
      emit(
        state.copyWith(
          alerts: [
            for (final a in state.alerts)
              if (a.id != alertId) a,
          ],
          ackBusy: {...state.ackBusy}..remove(alertId),
        ),
      );
      unawaited(load(force: true));
      return null;
    } catch (e) {
      if (!isClosed) {
        emit(state.copyWith(ackBusy: {...state.ackBusy}..remove(alertId)));
      }
      return ApiException.from(e);
    }
  }

  void _onAlertEvent() {
    _eventTimer?.cancel();
    _eventTimer = Timer(eventDebounce, () {
      if (!isClosed) unawaited(load(force: true));
    });
  }

  @override
  Future<void> close() async {
    _eventTimer?.cancel();
    await _eventSub?.cancel();
    return super.close();
  }
}
