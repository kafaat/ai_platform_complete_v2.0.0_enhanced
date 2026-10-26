// SAHOOL — features/scouting/presentation/scouting_fields_cubit.dart
// قائمة حقول المستخدم لاختيار حقل الاستكشاف (GET /api/v1/fields عبر FieldsApi —
// قراءة لواجهة ميزة الحقول العامّة، لا تعديل لها).
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

import '../data/scouting_models.dart';

typedef FieldsLoader = Future<List<Map<String, dynamic>>> Function();

sealed class ScoutingFieldsState {
  const ScoutingFieldsState();
}

class ScoutingFieldsLoading extends ScoutingFieldsState {
  const ScoutingFieldsLoading();
}

class ScoutingFieldsLoaded extends ScoutingFieldsState {
  const ScoutingFieldsLoaded(this.fields);
  final List<ScoutingField> fields;

  ScoutingField? byId(String? id) {
    if (id == null) return null;
    for (final f in fields) {
      if (f.id == id) return f;
    }
    return null;
  }
}

class ScoutingFieldsFailed extends ScoutingFieldsState {
  const ScoutingFieldsFailed(this.error);
  final ApiException error;
}

class ScoutingFieldsCubit extends Cubit<ScoutingFieldsState> {
  ScoutingFieldsCubit({FieldsLoader? loader})
    : _loader = loader ?? FieldsApi.instance.listFields,
      super(const ScoutingFieldsLoading());

  final FieldsLoader _loader;

  Future<void> load() async {
    emit(const ScoutingFieldsLoading());
    try {
      final raw = await _loader();
      final fields = raw
          .map(ScoutingField.fromSummary)
          .whereType<ScoutingField>()
          .toList();
      if (!isClosed) emit(ScoutingFieldsLoaded(fields));
    } catch (e) {
      if (!isClosed) emit(ScoutingFieldsFailed(ApiException.from(e)));
    }
  }
}
