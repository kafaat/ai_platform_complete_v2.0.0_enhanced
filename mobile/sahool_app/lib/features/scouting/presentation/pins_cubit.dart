// SAHOOL — features/scouting/presentation/pins_cubit.dart
// دبابيس حقل واحد + المرشّحات (النوع/الشدّة/التاريخ). الترشيح محلّيّ على ما ردّه
// الخادم؛ لا يُخترَع دبّوس ولا تُخفى حالة «القاعدة غير مفعّلة».
import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';

import '../data/scouting_api.dart';
import '../data/scouting_models.dart';

enum PinsStatus { loading, loaded, failed }

/// نافذة التاريخ: null ⇒ الكلّ.
enum PinsDateWindow {
  all(null, 'كلّ التواريخ'),
  week(7, 'آخر ٧ أيّام'),
  month(30, 'آخر ٣٠ يوماً');

  const PinsDateWindow(this.days, this.labelAr);
  final int? days;
  final String labelAr;
}

@immutable
class PinFilters {
  const PinFilters({
    this.category,
    this.severity,
    this.window = PinsDateWindow.all,
  });
  final IssueCategory? category;
  final PinSeverity? severity;
  final PinsDateWindow window;

  bool get isActive =>
      category != null || severity != null || window != PinsDateWindow.all;

  bool matches(ScoutingPin p, DateTime now) {
    if (category != null && p.categoryWire != category!.wire) return false;
    if (severity != null && p.severityWire != severity!.wire) return false;
    final days = window.days;
    if (days != null) {
      final at = p.createdAt;
      // تاريخ غائب لا يُعدّ «حديثاً» — لا نفترض.
      if (at == null || now.difference(at).inDays >= days) return false;
    }
    return true;
  }
}

@immutable
class PinsState {
  const PinsState({
    this.status = PinsStatus.loading,
    this.page,
    this.error,
    this.filters = const PinFilters(),
  });

  final PinsStatus status;
  final ScoutingPinsPage? page;
  final ApiException? error;
  final PinFilters filters;

  List<ScoutingPin> visible(DateTime now) => [
    for (final p in page?.pins ?? const <ScoutingPin>[])
      if (filters.matches(p, now)) p,
  ];

  PinsState copyWith({
    PinsStatus? status,
    ScoutingPinsPage? page,
    ApiException? error,
    PinFilters? filters,
  }) => PinsState(
    status: status ?? this.status,
    page: page ?? this.page,
    error: error,
    filters: filters ?? this.filters,
  );
}

class PinsCubit extends Cubit<PinsState> {
  PinsCubit(this._api, this.fieldId) : super(const PinsState());

  final ScoutingApi _api;
  final String fieldId;

  Future<void> load() async {
    // إبقاء القائمة الحاليّة ظاهرة أثناء التحديث لا يكذب: الحالة loading معلنة.
    emit(state.copyWith(status: PinsStatus.loading));
    try {
      final page = await _api.listPins(fieldId);
      if (!isClosed) {
        emit(state.copyWith(status: PinsStatus.loaded, page: page));
      }
    } catch (e) {
      if (!isClosed) {
        emit(
          state.copyWith(
            status: PinsStatus.failed,
            error: ApiException.from(e),
          ),
        );
      }
    }
  }

  void setFilters(PinFilters filters) => emit(
    PinsState(
      status: state.status,
      page: state.page,
      error: state.error,
      filters: filters,
    ),
  );
}
