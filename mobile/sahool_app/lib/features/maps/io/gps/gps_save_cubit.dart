// SAHOOL — features/maps/io/gps/gps_save_cubit.dart
// حفظ مسار المشي حقلاً عبر POST /api/v1/fields/import (format=gps،
// points=[[lon,lat],...]). مفتاح Idempotency واحد لكلّ حمولة: إعادة المحاولة بعد
// انقطاع تُرسل المفتاح نفسه فلا يُنشأ حقلان؛ تغيير الاسم/التبسيط بعد فشل = نيّة
// جديدة بمفتاح جديد.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import '../../draw/field_created_events.dart';
import '../data/maps_io_api.dart';
import '../presentation/io_errors.dart';

enum SavePhase { idle, saving, saved, failed }

class GpsSaveState {
  const GpsSaveState({this.phase = SavePhase.idle, this.fieldId, this.error});
  final SavePhase phase;
  final String? fieldId;
  final String? error;
}

class GpsSaveCubit extends Cubit<GpsSaveState> {
  GpsSaveCubit(this._api, {this.farmId, FieldCreatedEvents? events})
    : _events = events ?? FieldCreatedEvents.instance,
      super(const GpsSaveState());

  final MapsIoApi _api;
  final String? farmId;
  final FieldCreatedEvents _events;
  IdempotencyKey? _key;
  String? _signature;

  /// المفتاح الحاليّ (للاختبار والتشخيص).
  IdempotencyKey? get currentKey => _key;

  Future<void> save({
    required String name,
    required List<LatLng> ring,
    required int rawVertexCount,
    required double toleranceM,
  }) async {
    if (state.phase == SavePhase.saving || state.phase == SavePhase.saved) {
      return;
    }
    final points = [
      for (final p in ring) [p.longitude, p.latitude],
    ];
    final sig = '${name.trim()}|$points';
    if (_key == null || sig != _signature) {
      _key = IdempotencyKey.generate();
      _signature = sig;
    }
    emit(const GpsSaveState(phase: SavePhase.saving));
    try {
      final created = await _api.importBoundary(
        format: 'gps',
        points: points,
        name: name.trim(),
        farmId: farmId,
        idempotencyKey: _key!,
        boundaryMetadata: {
          'source': 'gps_walk',
          'mode': 'track',
          'post_processing':
              'douglas_peucker_${toleranceM.toStringAsFixed(0)}m',
          'vertices_before': rawVertexCount,
          'vertices_after': ring.length,
        },
      );
      _events.notifyCreated(created);
      if (isClosed) return;
      emit(
        GpsSaveState(
          phase: SavePhase.saved,
          fieldId: created['field_id']?.toString(),
        ),
      );
    } catch (e) {
      if (isClosed) return;
      emit(GpsSaveState(phase: SavePhase.failed, error: ioErrorText(e)));
    }
  }

  /// مسار جديد ⇒ نيّة جديدة.
  void reset() {
    _key = null;
    _signature = null;
    emit(const GpsSaveState());
  }
}
