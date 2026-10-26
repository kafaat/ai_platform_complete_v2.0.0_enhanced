// SAHOOL — features/dashboard/presentation/dashboard_bloc.dart
// Real BLoC implementation — not just re-exports
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_api.dart';

// ── Events ──────────────────────────────────────────────────
abstract class DashboardEvent {}

class LoadDashboard    extends DashboardEvent {}
class RefreshDashboard extends DashboardEvent {}
class AcknowledgeAlert extends DashboardEvent {
  final String alertId;
  AcknowledgeAlert(this.alertId);
}

// ── States ──────────────────────────────────────────────────
abstract class DashboardState {}
class DashboardInitial extends DashboardState {}
class DashboardLoading extends DashboardState {}
class DashboardLoaded  extends DashboardState {
  final Map<String, dynamic> data;
  DashboardLoaded(this.data);
}
class DashboardError extends DashboardState {
  final String message;
  DashboardError(this.message);
}

// ── BLoC ────────────────────────────────────────────────────
class DashboardBloc extends Bloc<DashboardEvent, DashboardState> {
  final DashboardApi _api;

  DashboardBloc(this._api) : super(DashboardInitial()) {
    on<LoadDashboard>   (_onLoad);
    on<RefreshDashboard>(_onRefresh);
    on<AcknowledgeAlert>(_onAck);
  }

  Future<void> _onLoad(LoadDashboard e, Emitter<DashboardState> emit) async {
    emit(DashboardLoading());
    await _fetch(emit);
  }

  Future<void> _onRefresh(RefreshDashboard e, Emitter<DashboardState> emit) async {
    await _fetch(emit);
  }

  Future<void> _onAck(AcknowledgeAlert e, Emitter<DashboardState> emit) async {
    try { await _api.acknowledgeAlert(e.alertId); } catch (_) {}
    add(RefreshDashboard());
  }

  Future<void> _fetch(Emitter<DashboardState> emit) async {
    try {
      final data = await _api.getDashboard();
      emit(DashboardLoaded(data));
    } catch (e) {
      emit(DashboardError(ApiException.from(e).messageAr));
    }
  }
}
