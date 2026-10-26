// SAHOOL — features/equipment/presentation/equipment_cubit.dart
// حالتا شاشتَي المعدّات: الأسطول (قائمة + تصفية بالحالة) وتفاصيل معدّة واحدة
// (المعدّة + سجلّ صيانتها). فشل تحديث لا يمسح بيانات معروضة.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/equipment/data/equipment_api.dart';
import 'package:sahool_app/features/equipment/data/equipment_models.dart';

// ── الأسطول ─────────────────────────────────────────────────────────

sealed class EquipmentState {
  const EquipmentState();
}

class EquipmentLoading extends EquipmentState {
  const EquipmentLoading();
}

class EquipmentFailed extends EquipmentState {
  const EquipmentFailed(this.error);
  final ApiException error;
}

class EquipmentLoaded extends EquipmentState {
  const EquipmentLoaded({
    required this.equipment,
    required this.fetchedAt,
    this.status,
    this.refreshError,
  });

  final List<Equipment> equipment;
  final DateTime fetchedAt;

  /// null ⇒ كلّ الحالات.
  final String? status;
  final ApiException? refreshError;

  int count(String status) => equipment.where((e) => e.status == status).length;

  List<Equipment> get visible => status == null
      ? equipment
      : equipment.where((e) => e.status == status).toList();
}

class EquipmentCubit extends Cubit<EquipmentState> {
  EquipmentCubit(this._api, {DateTime Function()? clock})
    : _clock = clock ?? DateTime.now,
      super(const EquipmentLoading());

  final EquipmentApi _api;
  final DateTime Function() _clock;

  Future<void> load() async {
    if (state is! EquipmentLoaded) emit(const EquipmentLoading());
    try {
      final list = await _api.listEquipment();
      if (isClosed) return;
      final prev = state;
      emit(
        EquipmentLoaded(
          equipment: list,
          fetchedAt: _clock(),
          status: prev is EquipmentLoaded ? prev.status : null,
        ),
      );
    } catch (e) {
      if (isClosed) return;
      final err = ApiException.from(e);
      final prev = state;
      emit(
        prev is EquipmentLoaded
            ? EquipmentLoaded(
                equipment: prev.equipment,
                fetchedAt: prev.fetchedAt,
                status: prev.status,
                refreshError: err,
              )
            : EquipmentFailed(err),
      );
    }
  }

  void setStatus(String? status) {
    final s = state;
    if (s is EquipmentLoaded) {
      emit(
        EquipmentLoaded(
          equipment: s.equipment,
          fetchedAt: s.fetchedAt,
          status: status,
          refreshError: s.refreshError,
        ),
      );
    }
  }
}

// ── تفاصيل معدّة ────────────────────────────────────────────────────

sealed class EquipmentDetailState {
  const EquipmentDetailState();
}

class EquipmentDetailLoading extends EquipmentDetailState {
  const EquipmentDetailLoading();
}

class EquipmentDetailFailed extends EquipmentDetailState {
  const EquipmentDetailFailed(this.error);
  final ApiException error;
}

class EquipmentDetailLoaded extends EquipmentDetailState {
  const EquipmentDetailLoaded({
    required this.equipment,
    required this.records,
    required this.now,
    this.refreshError,
  });

  final Equipment equipment;
  final List<MaintenanceRecord> records;
  final DateTime now;

  /// فشل آخر تحديث؛ المعروض من التحميل السابق.
  final ApiException? refreshError;

  /// المخطّطة، الأقرب موعداً أوّلاً (بلا تاريخ في الآخر).
  List<MaintenanceRecord> get upcoming {
    final list = records.where((r) => r.isPlanned).toList()
      ..sort((a, b) {
        final da = a.scheduledDate, db = b.scheduledDate;
        if (da == null && db == null) return 0;
        if (da == null) return 1;
        if (db == null) return -1;
        return da.compareTo(db);
      });
    return list;
  }

  /// المنجزة والملغاة بترتيب الخادم (الأحدث أوّلاً).
  List<MaintenanceRecord> get history =>
      records.where((r) => !r.isPlanned).toList();

  int get overdueCount => upcoming.where((r) => r.isOverdue(now)).length;
}

class EquipmentDetailCubit extends Cubit<EquipmentDetailState> {
  EquipmentDetailCubit(
    this._api,
    this.equipmentId, {
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now,
       super(const EquipmentDetailLoading());

  final EquipmentApi _api;
  final String equipmentId;
  final DateTime Function() _clock;

  Future<void> load() async {
    if (state is! EquipmentDetailLoaded) emit(const EquipmentDetailLoading());
    try {
      // لا نقطة لقراءة معدّة واحدة: تُقرأ من القائمة (وتعكس حالة «معطّلة» التي
      // يضعها الخادم بعد تسجيل عطل).
      final results = await Future.wait<Object>([
        _api.listEquipment(),
        _api.listMaintenance(equipmentId),
      ]);
      if (isClosed) return;
      Equipment? eq;
      for (final e in results[0] as List<Equipment>) {
        if (e.id == equipmentId) eq = e;
      }
      if (eq == null) {
        emit(
          const EquipmentDetailFailed(
            ApiException(
              kind: ApiErrorKind.notFound,
              statusCode: 404,
              messageAr: 'العنصر غير موجود.',
            ),
          ),
        );
        return;
      }
      emit(
        EquipmentDetailLoaded(
          equipment: eq,
          records: results[1] as List<MaintenanceRecord>,
          now: _clock(),
        ),
      );
    } catch (e) {
      if (isClosed) return;
      final err = ApiException.from(e);
      final prev = state;
      emit(
        prev is EquipmentDetailLoaded
            ? EquipmentDetailLoaded(
                equipment: prev.equipment,
                records: prev.records,
                now: prev.now,
                refreshError: err,
              )
            : EquipmentDetailFailed(err),
      );
    }
  }
}
