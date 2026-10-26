// SAHOOL — features/maps/io/presentation/import_cubit.dart
// تدفّق الاستيراد: تحليل على الجهاز ← معاينة واختيار ← إرسال كلّ مضلّع مختار
// إلى POST /api/v1/fields/import بمفتاح Idempotency ثابت لذلك المضلّع.
//
// الخادم يحفظ الحلقة الخارجيّة الأولى فقط من كلّ طلب (geo_import.py)، لذا يُرسَل
// كلّ مضلّع في طلب مستقلّ، وتُعلَن الثقوب المُسقَطة قبل الإرسال لا بعده.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import '../data/maps_io_api.dart';
import '../geo/import_model.dart';
import '../geo/io_measure.dart';
import 'io_errors.dart';

enum RowStatus { pending, sending, created, failed }

class ImportRow {
  const ImportRow({
    required this.shape,
    required this.name,
    required this.areaHa,
    required this.issues,
    required this.key,
    this.selected = true,
    this.status = RowStatus.pending,
    this.error,
    this.createdFieldId,
  });

  final ImportedShape shape;
  final String name;
  final double areaHa;
  final List<GeometryIssue> issues;
  final IdempotencyKey key;
  final bool selected;
  final RowStatus status;
  final String? error;
  final String? createdFieldId;

  bool get blocked => issues.any((i) => i.blocking);
  bool get sendable => selected && !blocked && status != RowStatus.created;

  ImportRow copyWith({
    String? name,
    bool? selected,
    RowStatus? status,
    String? error,
    bool clearError = false,
    String? createdFieldId,
    IdempotencyKey? key,
  }) => ImportRow(
    shape: shape,
    name: name ?? this.name,
    areaHa: areaHa,
    issues: issues,
    key: key ?? this.key,
    selected: selected ?? this.selected,
    status: status ?? this.status,
    error: clearError ? null : (error ?? this.error),
    createdFieldId: createdFieldId ?? this.createdFieldId,
  );
}

class ImportState {
  const ImportState({
    this.parsed,
    this.rows = const [],
    this.parseError,
    this.submitting = false,
    this.formError,
  });

  final ParsedImport? parsed;
  final List<ImportRow> rows;
  final String? parseError;
  final bool submitting;

  /// خطأ تحقّق على مستوى النموذج (أسماء مكرّرة/فارغة، لا اختيار).
  final String? formError;

  int get selectedCount => rows.where((r) => r.sendable).length;
  int get createdCount =>
      rows.where((r) => r.status == RowStatus.created).length;
  bool get allDone =>
      rows.isNotEmpty &&
      rows
          .where((r) => r.selected && !r.blocked)
          .every((r) => r.status == RowStatus.created);

  ImportState copyWith({
    ParsedImport? parsed,
    List<ImportRow>? rows,
    String? parseError,
    bool clearParseError = false,
    bool? submitting,
    String? formError,
    bool clearFormError = false,
  }) => ImportState(
    parsed: parsed ?? this.parsed,
    rows: rows ?? this.rows,
    parseError: clearParseError ? null : (parseError ?? this.parseError),
    submitting: submitting ?? this.submitting,
    formError: clearFormError ? null : (formError ?? this.formError),
  );
}

/// تحذير الثقوب لمضلّع: الخادم يحفظ الحدّ الخارجيّ فقط.
GeometryIssue? holesDropIssue(ImportedShape s) => s.polygon.holes.isEmpty
    ? null
    : GeometryIssue(
        'holes_dropped',
        'يحوي ${s.polygon.holes.length} ثقباً — مسار الاستيراد في الخادم يحفظ '
            'الحدّ الخارجيّ فقط، فتُضمّ مساحة الثقوب إلى الحقل.',
        blocking: false,
      );

class ImportCubit extends Cubit<ImportState> {
  ImportCubit(this._api, {this.farmId}) : super(const ImportState());

  final MapsIoApi _api;
  final String? farmId;

  void parse(String text, {BoundaryFormat? format}) {
    if (state.submitting) return;
    try {
      final parsed = parseBoundaryText(text, format: format);
      final rows = <ImportRow>[];
      for (var i = 0; i < parsed.shapes.length; i++) {
        final s = parsed.shapes[i];
        final issues = [
          ...validateForSave(s.polygon.outerOnly()),
          ?holesDropIssue(s),
        ];
        rows.add(
          ImportRow(
            shape: s,
            name: s.suggestedName(i),
            areaHa: polygonAreaHa(s.polygon),
            issues: issues,
            key: IdempotencyKey.generate(),
            selected: !issues.any((x) => x.blocking),
          ),
        );
      }
      emit(ImportState(parsed: parsed, rows: rows));
    } on FormatException catch (e) {
      emit(ImportState(parseError: e.message));
    }
  }

  void clear() {
    if (state.submitting) return;
    emit(const ImportState());
  }

  void toggle(int i, bool selected) {
    final r = state.rows[i];
    if (r.blocked || r.status == RowStatus.created || state.submitting) return;
    _replace(i, r.copyWith(selected: selected));
  }

  void rename(int i, String name) {
    final r = state.rows[i];
    if (r.status == RowStatus.created) return;
    // اسم جديد بعد محاولة فاشلة = نيّة كتابة جديدة ⇒ مفتاح جديد (لا يُعاد مفتاح
    // بحمولة مختلفة).
    _replace(
      i,
      r.copyWith(
        name: name,
        key: r.status == RowStatus.failed ? IdempotencyKey.generate() : null,
      ),
    );
  }

  void _replace(int i, ImportRow row) {
    final rows = [...state.rows]..[i] = row;
    emit(state.copyWith(rows: rows, clearFormError: true));
  }

  String? _validate() {
    final chosen = state.rows.where((r) => r.sendable).toList();
    if (chosen.isEmpty) return 'اختر مضلّعاً واحداً على الأقلّ.';
    final names = <String>{};
    for (final r in state.rows.where((r) => r.selected && !r.blocked)) {
      final n = r.name.trim();
      if (n.isEmpty) return 'لكلّ حقل مختار اسم مطلوب.';
      if (n.length > 100) return 'اسم الحقل أطول من 100 حرف: «$n».';
      if (!names.add(n.toLowerCase())) {
        return 'الاسم «$n» مكرّر — لكلّ حقل اسم مختلف.';
      }
    }
    return null;
  }

  /// يرسل المضلّعات المختارة واحداً تلو الآخر. الناجح لا يُعاد إرساله؛ الفاشل
  /// يُعاد بالمفتاح نفسه عند «إعادة المحاولة».
  Future<void> submit() async {
    if (state.submitting) return;
    final err = _validate();
    if (err != null) {
      emit(state.copyWith(formError: err));
      return;
    }
    emit(state.copyWith(submitting: true, clearFormError: true));
    final fmt = state.parsed!.format;
    for (var i = 0; i < state.rows.length; i++) {
      final r = state.rows[i];
      if (!r.sendable) continue;
      _replace(i, r.copyWith(status: RowStatus.sending, clearError: true));
      try {
        final outer = r.shape.polygon.outerOnly();
        final created = await _api.importBoundary(
          format: 'geojson',
          content: polygonGeoJsonText(outer),
          name: r.name.trim(),
          farmId: farmId,
          idempotencyKey: r.key,
          boundaryMetadata: {
            'source': fmt == BoundaryFormat.kml ? 'kml_file' : 'geojson_file',
            'mode': 'mobile_import',
            'vertices_before': r.shape.polygon.vertexCount,
          },
        );
        if (isClosed) return;
        _replace(
          i,
          state.rows[i].copyWith(
            status: RowStatus.created,
            createdFieldId: created['field_id']?.toString(),
          ),
        );
      } catch (e) {
        if (isClosed) return;
        _replace(
          i,
          state.rows[i].copyWith(
            status: RowStatus.failed,
            error: ioErrorText(e),
          ),
        );
      }
    }
    if (!isClosed) emit(state.copyWith(submitting: false));
  }
}
