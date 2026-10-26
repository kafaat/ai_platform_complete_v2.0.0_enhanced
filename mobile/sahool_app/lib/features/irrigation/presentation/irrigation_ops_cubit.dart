// SAHOOL — features/irrigation/presentation/irrigation_ops_cubit.dart
// حالة الريّ التشغيليّ: الصمّامات والجداول من الخادم، وطلبات الصمّام الجارية.
//
// إصلاح سلوك المفتاح (لا مسار أمر جديد — أوامر المشغِّلات مجمَّدة GATE-01):
//  • المفتاح يعكس حالة الخادم فقط: لا يتحرّك تفاؤليّاً، ويتحدّث من ردّ الخادم.
//  • طلبٌ جارٍ لصمّام ⇒ يُتجاهَل أيّ طلب آخر له (لا طلبات مكرّرة بنقرات متتالية).
//  • مفتاح Idempotency-Key واحد لكلّ نيّة (صمّام + حالة مطلوبة)؛ يُعاد بعد فشل
//    اتّصال (فإعادة المحاولة لا تُنشئ أمراً ثانياً على الخادم) ويُسقَط بعد ردّ قاطع.
//  • رفض الخادم (403/404/409/503…) يُعاد كما هو بنصّه، والحالة تبقى كما كانت.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_models.dart';

class IrrigationOpsState {
  const IrrigationOpsState({
    this.loading = true,
    this.error,
    this.valves = const [],
    this.schedules = const [],
    this.pendingValves = const {},
    this.pendingSchedules = const {},
  });

  final bool loading;
  final ApiException? error;
  final List<Valve> valves;
  final List<IrrigationSchedule> schedules;
  final Set<String> pendingValves;
  final Set<String> pendingSchedules;

  bool isValvePending(String id) => pendingValves.contains(id);

  IrrigationOpsState copyWith({
    bool? loading,
    ApiException? error,
    bool clearError = false,
    List<Valve>? valves,
    List<IrrigationSchedule>? schedules,
    Set<String>? pendingValves,
    Set<String>? pendingSchedules,
  }) => IrrigationOpsState(
    loading: loading ?? this.loading,
    error: clearError ? null : (error ?? this.error),
    valves: valves ?? this.valves,
    schedules: schedules ?? this.schedules,
    pendingValves: pendingValves ?? this.pendingValves,
    pendingSchedules: pendingSchedules ?? this.pendingSchedules,
  );
}

/// نتيجة طلبٍ تشغيليّ تُعرض للمستخدم كما هي.
class OpsOutcome {
  const OpsOutcome.ok(this.messageAr) : error = null, ignored = false;
  const OpsOutcome.failed(ApiException this.error)
    : messageAr = null,
      ignored = false;
  const OpsOutcome.ignored() : messageAr = null, error = null, ignored = true;

  final String? messageAr;
  final ApiException? error;

  /// طلب سابق لنفس العنصر ما زال جارياً ⇒ لم يُرسَل شيء.
  final bool ignored;
  bool get ok => error == null && !ignored;
}

class IrrigationOpsCubit extends Cubit<IrrigationOpsState> {
  IrrigationOpsCubit(this.api) : super(const IrrigationOpsState());

  final IrrigationApi api;
  final Map<String, IdempotencyKey> _intentKeys = {};

  Future<void> load() async {
    emit(state.copyWith(loading: true, clearError: true));
    await refresh();
  }

  /// يعيد القراءة دون إخفاء القائمة الحاليّة (بعد كتابة ناجحة).
  Future<void> refresh() async {
    try {
      final results = await Future.wait([
        api.listValves(),
        api.listSchedules(),
      ]);
      if (isClosed) return;
      emit(
        state.copyWith(
          loading: false,
          clearError: true,
          valves: results[0].map(Valve.fromJson).toList(),
          schedules: results[1].map(IrrigationSchedule.fromJson).toList(),
        ),
      );
    } catch (e) {
      if (isClosed) return;
      emit(state.copyWith(loading: false, error: ApiException.from(e)));
    }
  }

  /// مفتاح النيّة الحاليّ (للاختبار والتشخيص).
  IdempotencyKey? intentKey(String valveId, String status) =>
      _intentKeys['$valveId:$status'];

  /// يطلب حالة [status] ('open'/'closed') للصمّام عبر المسار القائم نفسه.
  Future<OpsOutcome> requestValveState(String valveId, String status) async {
    if (state.isValvePending(valveId)) return const OpsOutcome.ignored();
    final intent = '$valveId:$status';
    final key = _intentKeys.putIfAbsent(intent, IdempotencyKey.generate);
    emit(state.copyWith(pendingValves: {...state.pendingValves, valveId}));
    try {
      final res = await api.setValveState(valveId, status, idempotencyKey: key);
      _intentKeys.remove(intent);
      final serverStatus = res['status'] is String
          ? res['status'] as String
          : null;
      if (isClosed) return const OpsOutcome.ignored();
      emit(
        state.copyWith(
          pendingValves: {...state.pendingValves}..remove(valveId),
          valves: serverStatus == null
              ? state.valves
              : [
                  for (final v in state.valves)
                    v.id == valveId
                        ? v.withStatus(serverStatus, changedAt: DateTime.now())
                        : v,
                ],
        ),
      );
      // الحالة القانونيّة من الخادم (والطابع الزمنيّ الحقيقيّ).
      await refresh();
      return OpsOutcome.ok(
        (res['message_ar'] as String?) ??
            'سُجّل الطلب — التشغيل الفعليّ بانتظار موافقة بشريّة (HIL).',
      );
    } catch (e) {
      final err = ApiException.from(e);
      // ردّ قاطع من الخادم ⇒ نيّة منتهية؛ فشل اتّصال ⇒ نفس المفتاح عند الإعادة.
      if (!err.isConnectivity) {
        _intentKeys.remove(intent);
      }
      if (!isClosed) {
        emit(
          state.copyWith(
            pendingValves: {...state.pendingValves}..remove(valveId),
          ),
        );
      }
      return OpsOutcome.failed(err);
    }
  }

  Future<OpsOutcome> deleteSchedule(String scheduleId) async {
    if (state.pendingSchedules.contains(scheduleId)) {
      return const OpsOutcome.ignored();
    }
    final intent = 'delete:$scheduleId';
    final key = _intentKeys.putIfAbsent(intent, IdempotencyKey.generate);
    emit(
      state.copyWith(pendingSchedules: {...state.pendingSchedules, scheduleId}),
    );
    try {
      await api.deleteSchedule(scheduleId, idempotencyKey: key);
      _intentKeys.remove(intent);
      if (isClosed) return const OpsOutcome.ignored();
      emit(
        state.copyWith(
          pendingSchedules: {...state.pendingSchedules}..remove(scheduleId),
          schedules: state.schedules.where((s) => s.id != scheduleId).toList(),
        ),
      );
      return const OpsOutcome.ok('حُذف جدول الريّ.');
    } catch (e) {
      final err = ApiException.from(e);
      if (!err.isConnectivity) {
        _intentKeys.remove(intent);
      }
      if (!isClosed) {
        emit(
          state.copyWith(
            pendingSchedules: {...state.pendingSchedules}..remove(scheduleId),
          ),
        );
      }
      return OpsOutcome.failed(err);
    }
  }
}
