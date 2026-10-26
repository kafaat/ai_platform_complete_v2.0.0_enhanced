// SAHOOL — features/maps/io/presentation/field_ops_cubit.dart
// دمج حقلين وتقسيم حقل. لا مكتبة اتّحاد/فرق في تبعيّات Dart، فالهندسة تُحسب في
// الخادم: معاينة dry-run (POST /api/v1/gis/union · /api/v1/gis/split) ثمّ الالتزام
// الذرّيّ (POST /api/v1/fields/merge · /api/v1/fields/split) بالهندسة التي أعادتها
// المعاينة نفسها. المعاينة خلف FEATURE_GIS_KERNEL؛ إن كانت مُطفأة (404) يُعلَن
// ذلك ولا يُتاح الحفظ — لا هندسة تُخمَّن على الجهاز.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import '../data/maps_io_api.dart';
import '../geo/io_geometry.dart';
import 'io_errors.dart';

/// حقل قابل للعمليّات (له حدود).
class OpsField {
  const OpsField({
    required this.id,
    required this.name,
    required this.polygons,
    this.areaHa,
    this.farmId,
    this.crop,
  });
  final String id;
  final String name;
  final List<IoPolygon> polygons;
  final num? areaHa;
  final String? farmId;
  final String? crop;

  static OpsField? from(Map<String, dynamic> f) {
    final polys = polygonsFromGeoJson(f['geometry']);
    final id = (f['field_id'] ?? f['id'] ?? '').toString();
    if (polys.isEmpty || id.isEmpty) return null;
    final name = (f['name'] ?? '').toString();
    return OpsField(
      id: id,
      name: name.isEmpty ? id : name,
      polygons: polys,
      areaHa: f['area_ha'] is num ? f['area_ha'] as num : null,
      farmId: f['farm_id']?.toString(),
      crop: f['crop'] is String ? f['crop'] as String : null,
    );
  }
}

enum PreviewPhase { none, loading, disabled, failed, ready }

enum CommitPhase { idle, saving, done, failed }

class FieldOpsState {
  const FieldOpsState({
    this.loading = true,
    this.loadError,
    this.fields = const [],
    this.selected = const [],
    this.blade = const [],
    this.preview = PreviewPhase.none,
    this.previewError,
    this.resultGeometry,
    this.parts = const [],
    this.commit = CommitPhase.idle,
    this.commitError,
  });

  final bool loading;
  final Object? loadError;
  final List<OpsField> fields;

  /// المعرّفات المختارة (دمج: حتّى اثنين؛ تقسيم: واحد).
  final List<String> selected;

  /// رؤوس خطّ القطع (تقسيم).
  final List<LatLng> blade;
  final PreviewPhase preview;
  final String? previewError;

  /// هندسة الدمج كما أعادها الخادم (تُرسَل كما هي عند الالتزام).
  final Map<String, dynamic>? resultGeometry;

  /// أجزاء التقسيم كما أعادها الخادم (GeoJSON لكلّ جزء).
  final List<Map<String, dynamic>> parts;
  final CommitPhase commit;
  final String? commitError;

  List<OpsField> get selectedFields => [
    for (final id in selected) ...fields.where((f) => f.id == id),
  ];

  FieldOpsState copyWith({
    bool? loading,
    Object? loadError,
    bool clearLoadError = false,
    List<OpsField>? fields,
    List<String>? selected,
    List<LatLng>? blade,
    PreviewPhase? preview,
    String? previewError,
    Map<String, dynamic>? resultGeometry,
    bool clearResult = false,
    List<Map<String, dynamic>>? parts,
    CommitPhase? commit,
    String? commitError,
  }) => FieldOpsState(
    loading: loading ?? this.loading,
    loadError: clearLoadError ? null : (loadError ?? this.loadError),
    fields: fields ?? this.fields,
    selected: selected ?? this.selected,
    blade: blade ?? this.blade,
    preview: preview ?? this.preview,
    previewError: previewError ?? this.previewError,
    resultGeometry: clearResult
        ? null
        : (resultGeometry ?? this.resultGeometry),
    parts: parts ?? this.parts,
    commit: commit ?? this.commit,
    commitError: commitError ?? this.commitError,
  );

  /// يُبطل المعاينة (تغيّر المدخل ⇒ لا تُحفَظ هندسة قديمة).
  FieldOpsState invalidated() => FieldOpsState(
    loading: loading,
    fields: fields,
    selected: selected,
    blade: blade,
  );
}

abstract class _OpsCubit extends Cubit<FieldOpsState> {
  _OpsCubit(this.api) : super(const FieldOpsState());
  final MapsIoApi api;
  IdempotencyKey? _key;
  String? _sig;

  Future<void> load({String? preselect}) async {
    emit(state.copyWith(loading: true, clearLoadError: true));
    try {
      final rows = await api.listFields();
      final fields = [for (final r in rows) ?OpsField.from(r)];
      if (isClosed) return;
      final pre = preselect != null && fields.any((f) => f.id == preselect)
          ? [preselect]
          : const <String>[];
      emit(FieldOpsState(loading: false, fields: fields, selected: pre));
    } catch (e) {
      if (!isClosed) emit(state.copyWith(loading: false, loadError: e));
    }
  }

  IdempotencyKey keyFor(String signature) {
    if (_key == null || _sig != signature) {
      _key = IdempotencyKey.generate();
      _sig = signature;
    }
    return _key!;
  }

  void failPreview(Object e) {
    if (isClosed) return;
    emit(
      state.copyWith(
        preview: isGisKernelDisabled(e)
            ? PreviewPhase.disabled
            : PreviewPhase.failed,
        previewError: isGisKernelDisabled(e)
            ? kGisPreviewDisabledAr
            : ioErrorText(e),
      ),
    );
  }
}

class MergeCubit extends _OpsCubit {
  MergeCubit(super.api);

  /// يختار/يُلغي حقلاً. معاينة الخادم تقبل حقلين بالضبط.
  void toggle(String id) {
    if (state.commit == CommitPhase.saving ||
        state.commit == CommitPhase.done) {
      return;
    }
    final sel = [...state.selected];
    if (sel.contains(id)) {
      sel.remove(id);
    } else {
      if (sel.length == 2) sel.removeAt(0);
      sel.add(id);
    }
    emit(state.invalidated().copyWith(selected: sel));
  }

  Future<void> preview() async {
    if (state.selected.length != 2 || state.preview == PreviewPhase.loading) {
      return;
    }
    emit(state.copyWith(preview: PreviewPhase.loading, clearResult: true));
    try {
      final r = await api.previewUnion(state.selected[0], state.selected[1]);
      final geom = r['result'];
      if (geom is! Map || polygonsFromGeoJson(geom).isEmpty) {
        throw const FormatException('لم يُرجِع الخادم مضلّعاً للاتّحاد.');
      }
      if (isClosed) return;
      emit(
        state.copyWith(
          preview: PreviewPhase.ready,
          resultGeometry: geom.cast<String, dynamic>(),
        ),
      );
    } catch (e) {
      failPreview(e);
    }
  }

  Future<void> commit(String name) async {
    final geom = state.resultGeometry;
    if (geom == null || state.preview != PreviewPhase.ready) return;
    if (state.commit == CommitPhase.saving ||
        state.commit == CommitPhase.done) {
      return;
    }
    final sources = state.selectedFields;
    final farm = sources.map((f) => f.farmId).toSet();
    final key = keyFor('${state.selected.join(',')}|${name.trim()}');
    emit(state.copyWith(commit: CommitPhase.saving));
    try {
      await api.mergeFields(
        sourceFieldIds: state.selected,
        name: name.trim(),
        geometry: geom,
        farmId: farm.length == 1 ? farm.first : null,
        idempotencyKey: key,
      );
      if (!isClosed) emit(state.copyWith(commit: CommitPhase.done));
    } catch (e) {
      if (!isClosed) {
        emit(
          state.copyWith(
            commit: CommitPhase.failed,
            commitError: ioErrorText(e),
          ),
        );
      }
    }
  }
}

class SplitCubit extends _OpsCubit {
  SplitCubit(super.api);

  void choose(String id) {
    if (state.commit == CommitPhase.saving ||
        state.commit == CommitPhase.done) {
      return;
    }
    emit(FieldOpsState(loading: false, fields: state.fields, selected: [id]));
  }

  void addBladePoint(LatLng p) {
    if (state.selected.isEmpty || state.commit == CommitPhase.saving) return;
    emit(state.invalidated().copyWith(blade: [...state.blade, p]));
  }

  void undoBladePoint() {
    if (state.blade.isEmpty) return;
    emit(
      state.invalidated().copyWith(
        blade: state.blade.sublist(0, state.blade.length - 1),
      ),
    );
  }

  void clearBlade() => emit(state.invalidated().copyWith(blade: const []));

  Map<String, dynamic> get bladeGeoJson => {
    'type': 'LineString',
    'coordinates': [
      for (final p in state.blade) [p.longitude, p.latitude],
    ],
  };

  Future<void> preview() async {
    if (state.selected.isEmpty || state.blade.length < 2) return;
    if (state.preview == PreviewPhase.loading) return;
    emit(state.copyWith(preview: PreviewPhase.loading, parts: const []));
    try {
      final r = await api.previewSplit(state.selected.first, bladeGeoJson);
      final result = r['result'];
      final geoms = result is Map ? result['geometries'] : null;
      final parts = <Map<String, dynamic>>[
        if (geoms is List)
          for (final g in geoms)
            if (g is Map && polygonsFromGeoJson(g).isNotEmpty)
              g.cast<String, dynamic>(),
      ];
      if (isClosed) return;
      if (parts.length < 2) {
        emit(
          state.copyWith(
            preview: PreviewPhase.failed,
            previewError:
                'الخطّ لا يقسم الحقل إلى جزأين — مدّه ليعبر الحدّ من جهة إلى أخرى.',
          ),
        );
        return;
      }
      if (parts.length > 10) {
        emit(
          state.copyWith(
            preview: PreviewPhase.failed,
            previewError:
                'الخطّ يُنتج ${parts.length} أجزاء والخادم يقبل حتّى 10 — بسّط الخطّ.',
          ),
        );
        return;
      }
      emit(state.copyWith(preview: PreviewPhase.ready, parts: parts));
    } catch (e) {
      failPreview(e);
    }
  }

  Future<void> commit(List<String> names) async {
    if (state.preview != PreviewPhase.ready ||
        names.length != state.parts.length) {
      return;
    }
    if (state.commit == CommitPhase.saving ||
        state.commit == CommitPhase.done) {
      return;
    }
    final src = state.selectedFields.first;
    final key = keyFor('${src.id}|${names.join(',')}|${state.blade}');
    emit(state.copyWith(commit: CommitPhase.saving));
    try {
      await api.splitField(
        sourceFieldId: src.id,
        children: [
          for (var i = 0; i < names.length; i++)
            (name: names[i].trim(), geometry: state.parts[i]),
        ],
        idempotencyKey: key,
        inheritCrop: src.crop,
      );
      if (!isClosed) emit(state.copyWith(commit: CommitPhase.done));
    } catch (e) {
      if (!isClosed) {
        emit(
          state.copyWith(
            commit: CommitPhase.failed,
            commitError: ioErrorText(e),
          ),
        );
      }
    }
  }
}
