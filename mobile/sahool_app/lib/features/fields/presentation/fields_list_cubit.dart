// SAHOOL — features/fields/presentation/fields_list_cubit.dart
// حالة قائمة «حقولي»: الحقول (GET /api/v1/fields) + أسماء المزارع للتصفية
// (GET /api/v1/farms، اختياريّ) + الاستعلام (بحث/تصفية/ترتيب) + الأولويّات
// (تُجلب عند اختيار ترتيب «الأولويّة» فقط، من طوابير المزارع والحقول).
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/field_list_query.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

import 'common/load_cubit.dart';

class FieldsListState {
  const FieldsListState({
    this.fields = const LoadLoading(),
    this.farmNames = const {},
    this.query = const FieldQuery(),
    this.priority,
  });

  final LoadState<List<Map<String, dynamic>>> fields;

  /// farm_id ← الاسم (فارغة إن تعذّر جلب المزارع).
  final Map<String, String> farmNames;
  final FieldQuery query;

  /// null = لم تُطلب بعد.
  final LoadState<PriorityData>? priority;

  List<Map<String, dynamic>> get all => switch (fields) {
    LoadLoaded(:final data) => data,
    _ => const [],
  };

  List<Map<String, dynamic>> get visible => applyFieldQuery(
    all,
    query,
    priority: switch (priority) {
      LoadLoaded(:final data) => data,
      _ => null,
    },
  );

  /// المحاصيل الموجودة فعلاً في القائمة ('' = بلا محصول).
  List<String> get crops =>
      ({for (final f in all) fieldListCrop(f)}.toList()..sort());

  List<String> get statuses => ({
    for (final f in all)
      if ('${f['quality_grade'] ?? ''}'.isNotEmpty) '${f['quality_grade']}',
  }.toList()..sort());

  /// farm_id المستعملة في القائمة ('' = بلا مزرعة).
  List<String> get farmIds =>
      ({for (final f in all) '${f['farm_id'] ?? ''}'}.toList()..sort());

  FieldsListState copyWith({
    LoadState<List<Map<String, dynamic>>>? fields,
    Map<String, String>? farmNames,
    FieldQuery? query,
    LoadState<PriorityData>? Function()? priority,
  }) => FieldsListState(
    fields: fields ?? this.fields,
    farmNames: farmNames ?? this.farmNames,
    query: query ?? this.query,
    priority: priority == null ? this.priority : priority(),
  );
}

class FieldsListCubit extends Cubit<FieldsListState> {
  FieldsListCubit(this._fields, this._farms) : super(const FieldsListState());

  final FieldsApi _fields;
  final FarmsApi _farms;
  int _gen = 0;
  int _priorityGen = 0;

  /// أقصى عدد حقول بلا مزرعة نسأل عن طابورها فرديّاً (حدّ لعدد الطلبات).
  static const maxUnassignedQueues = 20;

  Future<void> load({bool silent = false}) async {
    final gen = ++_gen;
    if (!silent || state.fields is! LoadLoaded) {
      emit(state.copyWith(fields: const LoadLoading()));
    }
    final farmsFuture = _farms.listFarms().then<List<Map<String, dynamic>>?>(
      (v) => v,
      onError: (Object _) => null,
    );
    try {
      final fields = await _fields.listFields();
      final farms = await farmsFuture;
      if (isClosed || gen != _gen) return;
      emit(
        state.copyWith(
          fields: LoadLoaded(fields, DateTime.now()),
          farmNames: farms == null
              ? state.farmNames
              : {
                  for (final f in farms)
                    '${f['farm_id']}': '${f['name'] ?? f['farm_id']}',
                },
          priority: () => null,
        ),
      );
      if (state.query.sort == FieldSort.priority) await loadPriority();
    } catch (e) {
      await farmsFuture;
      if (isClosed || gen != _gen) return;
      emit(state.copyWith(fields: LoadFailed(ApiException.from(e))));
    }
  }

  void setText(String v) =>
      emit(state.copyWith(query: state.query.copyWith(text: v)));

  void setFarm(String? farmId) =>
      emit(state.copyWith(query: state.query.copyWith(farmId: () => farmId)));

  void setCrop(String? crop) =>
      emit(state.copyWith(query: state.query.copyWith(crop: () => crop)));

  void setStatus(String? s) =>
      emit(state.copyWith(query: state.query.copyWith(status: () => s)));

  void clearFilters() =>
      emit(state.copyWith(query: FieldQuery(sort: state.query.sort)));

  Future<void> setSort(FieldSort sort) async {
    emit(state.copyWith(query: state.query.copyWith(sort: sort)));
    if (sort == FieldSort.priority && state.priority is! LoadLoaded) {
      await loadPriority();
    }
  }

  /// يجمّع طوابير الأولويّة: طابور لكلّ مزرعة، وطابور فرديّ لحقول بلا مزرعة
  /// (حتّى [maxUnassignedQueues]). مصدر فاشل ⇒ حقوله «غير مقيسة» و partial.
  Future<void> loadPriority() async {
    final fields = state.all;
    if (fields.isEmpty) return;
    final gen = ++_priorityGen;
    emit(state.copyWith(priority: () => const LoadLoading()));
    final byFarm = <String, List<String>>{};
    final unassigned = <String>[];
    for (final f in fields) {
      final id = '${f['field_id'] ?? ''}';
      if (id.isEmpty) continue;
      final farm = '${f['farm_id'] ?? ''}';
      if (farm.isEmpty) {
        unassigned.add(id);
      } else {
        (byFarm[farm] ??= []).add(id);
      }
    }
    final items = <Map<String, dynamic>>[];
    final measured = <String>{};
    var partial = unassigned.length > maxUnassignedQueues;
    ApiException? lastError;

    Future<void> collect(
      Future<Map<String, dynamic>> req,
      Iterable<String> covers,
    ) async {
      try {
        final r = await req;
        if (r['degraded'] == true) partial = true;
        final raw = r['items'];
        if (raw is List) {
          for (final it in raw.whereType<Map>()) {
            items.add(it.cast<String, dynamic>());
          }
        }
        measured.addAll(covers);
      } catch (e) {
        partial = true;
        lastError = ApiException.from(e);
      }
    }

    await Future.wait([
      for (final e in byFarm.entries)
        collect(_farms.getFarmPriorityQueue(e.key), e.value),
      for (final id in unassigned.take(maxUnassignedQueues))
        collect(_fields.fetchFieldPriorityQueue(id), [id]),
    ]);
    if (isClosed || gen != _priorityGen) return;
    if (measured.isEmpty && lastError != null) {
      emit(state.copyWith(priority: () => LoadFailed(lastError!)));
      return;
    }
    emit(
      state.copyWith(
        priority: () => LoadLoaded(
          PriorityData.fromItems(items, measured: measured, partial: partial),
          DateTime.now(),
        ),
      ),
    );
  }
}
