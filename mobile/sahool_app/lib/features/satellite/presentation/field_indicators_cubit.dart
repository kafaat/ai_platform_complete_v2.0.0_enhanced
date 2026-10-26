// SAHOOL — features/satellite/presentation/field_indicators_cubit.dart
// حالة مؤشّرات حقل واحد: اللقطة الحاليّة (vegetation /v1/analyze) + السلسلة
// الزمنيّة للمؤشّر المختار (raster timeseries) + خيارات المؤشّرات (الكتالوج).
//
// إصلاح سباق التبديل السريع: كلّ طلب يحمل رقم جيل ومعرّف الحقل/المؤشّر الذي
// طُلب له؛ الردّ الذي يصل بعد تبديل الحقل أو المؤشّر يُهمَل، فلا تظهر مؤشّرات
// الحقل (أ) تحت اسم الحقل (ب) مهما تأخّر ردّ (أ).
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/fields/presentation/common/load_cubit.dart';
import 'package:sahool_app/features/satellite/data/satellite_api.dart';
import 'package:sahool_app/features/satellite/data/satellite_models.dart';

class FieldIndicatorsState {
  const FieldIndicatorsState({
    this.fieldId,
    this.index = 'ndvi',
    this.options = kFallbackIndexOptions,
    this.optionsFromCatalog = false,
    this.snapshot = const LoadLoading(),
    this.series = const LoadLoading(),
    this.hideCloudy = false,
  });

  final String? fieldId;
  final String index;
  final List<IndexOption> options;

  /// false ⇒ الكتالوج تعذّر والقائمة احتياطيّة (يُقال ذلك في الواجهة).
  final bool optionsFromCatalog;
  final LoadState<IndicatorSnapshot> snapshot;
  final LoadState<IndexSeries> series;
  final bool hideCloudy;

  IndexOption get selectedOption => options.firstWhere(
    (o) => o.id == index,
    orElse: () => IndexOption(id: index, nameAr: index.toUpperCase()),
  );

  FieldIndicatorsState copyWith({
    String? fieldId,
    String? index,
    List<IndexOption>? options,
    bool? optionsFromCatalog,
    LoadState<IndicatorSnapshot>? snapshot,
    LoadState<IndexSeries>? series,
    bool? hideCloudy,
  }) => FieldIndicatorsState(
    fieldId: fieldId ?? this.fieldId,
    index: index ?? this.index,
    options: options ?? this.options,
    optionsFromCatalog: optionsFromCatalog ?? this.optionsFromCatalog,
    snapshot: snapshot ?? this.snapshot,
    series: series ?? this.series,
    hideCloudy: hideCloudy ?? this.hideCloudy,
  );
}

class FieldIndicatorsCubit extends Cubit<FieldIndicatorsState> {
  FieldIndicatorsCubit(this._api) : super(const FieldIndicatorsState());

  final SatelliteApi _api;
  int _snapshotGen = 0;
  int _seriesGen = 0;
  bool _catalogRequested = false;

  /// يجلب خيارات المؤشّرات من الكتالوج مرّة واحدة؛ الفشل يُبقي الاحتياطيّة.
  Future<void> loadCatalog() async {
    if (_catalogRequested) return;
    _catalogRequested = true;
    try {
      final options = await _api.getIndicatorCatalog();
      if (isClosed || options.isEmpty) return;
      final keep = options.any((o) => o.id == state.index);
      emit(
        state.copyWith(
          options: options,
          optionsFromCatalog: true,
          index: keep ? state.index : options.first.id,
        ),
      );
      if (!keep && state.fieldId != null) await _loadSeries();
    } catch (_) {
      // الكتالوج اختياريّ: القائمة الاحتياطيّة معلَنة في الواجهة.
    }
  }

  /// يختار حقلاً ويجلب لقطته وسلسلة المؤشّر المختار له.
  Future<void> selectField(String fieldId) async {
    if (fieldId.isEmpty) return;
    emit(
      state.copyWith(
        fieldId: fieldId,
        snapshot: const LoadLoading(),
        series: const LoadLoading(),
      ),
    );
    await Future.wait([_loadSnapshot(), _loadSeries()]);
  }

  /// يختار مؤشّراً ويجلب سلسلته للحقل الحاليّ.
  Future<void> selectIndex(String index) async {
    if (index == state.index && state.series is! LoadFailed) return;
    emit(state.copyWith(index: index, series: const LoadLoading()));
    if (state.fieldId != null) await _loadSeries();
  }

  void setHideCloudy(bool v) => emit(state.copyWith(hideCloudy: v));

  Future<void> retrySnapshot() async {
    emit(state.copyWith(snapshot: const LoadLoading()));
    await _loadSnapshot();
  }

  Future<void> retrySeries() async {
    emit(state.copyWith(series: const LoadLoading()));
    await _loadSeries();
  }

  Future<void> refresh() async {
    final id = state.fieldId;
    if (id != null) await selectField(id);
  }

  Future<void> _loadSnapshot() async {
    final fieldId = state.fieldId;
    if (fieldId == null) return;
    final gen = ++_snapshotGen;
    bool stale() => isClosed || gen != _snapshotGen || state.fieldId != fieldId;
    try {
      final snap = await _api.getIndicatorSnapshot(fieldId);
      if (stale()) return;
      emit(state.copyWith(snapshot: LoadLoaded(snap, DateTime.now())));
    } catch (e) {
      if (stale()) return;
      emit(state.copyWith(snapshot: LoadFailed(ApiException.from(e))));
    }
  }

  Future<void> _loadSeries() async {
    final fieldId = state.fieldId;
    if (fieldId == null) return;
    final index = state.index;
    final gen = ++_seriesGen;
    bool stale() =>
        isClosed ||
        gen != _seriesGen ||
        state.fieldId != fieldId ||
        state.index != index;
    try {
      final series = await _api.getFieldIndexTimeseries(fieldId, index);
      if (stale()) return;
      emit(state.copyWith(series: LoadLoaded(series, DateTime.now())));
    } catch (e) {
      if (stale()) return;
      emit(state.copyWith(series: LoadFailed(ApiException.from(e))));
    }
  }
}
