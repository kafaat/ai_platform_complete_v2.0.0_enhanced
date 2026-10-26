// SAHOOL — features/maps/presentation/farm_map_cubit.dart
// حالة شاشة «خريطة حقولي»: حقول المستخدم من مصدر الحقيقة (GET /api/v1/fields عبر
// FieldsApi — قراءة عبر الميزات مسموحة)، الحقل المختار، والحزمة بلا اتّصال المفعّلة.
// صدق: الفشل يحمل ApiException كما هو؛ حقل بلا هندسة يُعدّ ولا يُرسَم ولا يُخمَّن.
import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

import '../data/offline_pack_store.dart';
import 'layers/fields_layer.dart';

enum FarmMapStatus { loading, loaded, failed }

@immutable
class FarmMapState {
  const FarmMapState({
    this.status = FarmMapStatus.loading,
    this.fields = const [],
    this.error,
    this.selectedId,
    this.offlinePackPath,
  });

  final FarmMapStatus status;
  final List<MapField> fields;
  final ApiException? error;
  final String? selectedId;
  final String? offlinePackPath;

  List<MapField> get drawable => fields.where((f) => f.hasGeometry).toList();
  int get withoutGeometry => fields.length - drawable.length;
  bool get isEmpty => status == FarmMapStatus.loaded && fields.isEmpty;

  MapField? get selected {
    for (final f in fields) {
      if (f.id == selectedId) return f;
    }
    return null;
  }

  FarmMapState copyWith({
    FarmMapStatus? status,
    List<MapField>? fields,
    ApiException? error,
    bool clearError = false,
    String? selectedId,
    bool clearSelection = false,
    String? offlinePackPath,
    bool clearPack = false,
  }) => FarmMapState(
    status: status ?? this.status,
    fields: fields ?? this.fields,
    error: clearError ? null : (error ?? this.error),
    selectedId: clearSelection ? null : (selectedId ?? this.selectedId),
    offlinePackPath: clearPack
        ? null
        : (offlinePackPath ?? this.offlinePackPath),
  );
}

class FarmMapCubit extends Cubit<FarmMapState> {
  FarmMapCubit(this._fields, this._packs) : super(const FarmMapState());

  final FieldsApi _fields;
  final OfflinePackStore? _packs;

  Future<void> load() async {
    emit(state.copyWith(status: FarmMapStatus.loading, clearError: true));
    await refreshOfflinePack();
    try {
      final rows = await _fields.listFields();
      if (isClosed) return;
      final fields = [
        for (final r in rows) MapField.fromSummary(r),
      ].where((f) => f.id.isNotEmpty).toList();
      final keep = fields.any((f) => f.id == state.selectedId);
      emit(
        state.copyWith(
          status: FarmMapStatus.loaded,
          fields: fields,
          clearSelection: !keep,
        ),
      );
    } catch (e) {
      if (isClosed) return;
      emit(
        state.copyWith(
          status: FarmMapStatus.failed,
          error: ApiException.from(e),
        ),
      );
    }
  }

  /// يعيد قراءة الحزمة المفعّلة (بعد العودة من شاشة الحزم).
  Future<void> refreshOfflinePack() async {
    final store = _packs;
    if (store == null) return;
    String? path;
    try {
      path = await store.activePath();
    } catch (_) {
      path = null; // تفضيلات غير متاحة ⇒ الشبكة
    }
    if (isClosed) return;
    emit(
      path == null
          ? state.copyWith(clearPack: true)
          : state.copyWith(offlinePackPath: path),
    );
  }

  /// نقرة على الخريطة: يختار الحقل تحتها أو يُلغي الاختيار.
  void tapAt(LatLng point) {
    final hit = fieldAt(state.drawable, point);
    emit(
      hit == null
          ? state.copyWith(clearSelection: true)
          : state.copyWith(selectedId: hit.id),
    );
  }

  void select(String? id) => emit(
    id == null
        ? state.copyWith(clearSelection: true)
        : state.copyWith(selectedId: id),
  );
}
