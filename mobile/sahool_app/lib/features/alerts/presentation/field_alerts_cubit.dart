// SAHOOL — features/alerts/presentation/field_alerts_cubit.dart
// لقسم الحقل في صندوق التنبيهات: التنبيهات المشتقّة من الحالة القانونيّة
// (للعرض) وتشغيل تقييم الحقل (owner/manager) بمفتاح ثابت للنيّة.
import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import '../data/alert_models.dart';
import '../data/alerts_api.dart';

@immutable
class FieldAlertsState {
  const FieldAlertsState({
    this.loading = true,
    this.derived = const [],
    this.error,
    this.evaluating = false,
    this.evalNote,
    this.evalFailed = false,
  });

  final bool loading;
  final List<DerivedAlert> derived;
  final ApiException? error;
  final bool evaluating;
  final String? evalNote;
  final bool evalFailed;

  FieldAlertsState copyWith({
    bool? loading,
    List<DerivedAlert>? derived,
    ApiException? error,
    bool clearError = false,
    bool? evaluating,
    String? evalNote,
    bool? evalFailed,
  }) => FieldAlertsState(
    loading: loading ?? this.loading,
    derived: derived ?? this.derived,
    error: clearError ? null : (error ?? this.error),
    evaluating: evaluating ?? this.evaluating,
    evalNote: evalNote ?? this.evalNote,
    evalFailed: evalFailed ?? this.evalFailed,
  );
}

class FieldAlertsCubit extends Cubit<FieldAlertsState> {
  FieldAlertsCubit(this._api, this.fieldId) : super(const FieldAlertsState());

  final AlertsApi _api;
  final String fieldId;
  IdempotencyKey? _evalKey;

  Future<void> loadDerived() async {
    emit(state.copyWith(loading: true, clearError: true));
    try {
      final list = await _api.fieldDerivedAlerts(fieldId);
      if (isClosed) return;
      emit(state.copyWith(loading: false, derived: list));
    } catch (e) {
      if (isClosed) return;
      emit(state.copyWith(loading: false, error: ApiException.from(e)));
    }
  }

  /// يعيد true إن أُنشئت تنبيهات (ليحدّث المستدعي الصندوق).
  Future<bool> evaluate() async {
    if (state.evaluating) return false;
    final key = _evalKey ??= IdempotencyKey.generate();
    emit(state.copyWith(evaluating: true));
    try {
      final r = await _api.evaluateFieldAlerts(fieldId, idempotencyKey: key);
      _evalKey = null; // النيّة اكتملت؛ الضغطة التالية نيّة جديدة.
      if (isClosed) return r.created.isNotEmpty;
      emit(
        state.copyWith(
          evaluating: false,
          evalNote: r.summaryAr,
          evalFailed: false,
        ),
      );
      return r.created.isNotEmpty;
    } catch (e) {
      if (isClosed) return false;
      final err = ApiException.from(e);
      emit(
        state.copyWith(
          evaluating: false,
          evalFailed: true,
          evalNote: 'تعذّر التقييم: ${err.messageAr}',
        ),
      );
      return false;
    }
  }
}
