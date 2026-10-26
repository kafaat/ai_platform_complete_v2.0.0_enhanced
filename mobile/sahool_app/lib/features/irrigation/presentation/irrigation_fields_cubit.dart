// SAHOOL — features/irrigation/presentation/irrigation_fields_cubit.dart
// قائمة الحقول لمنتقي الحقل في شاشات الريّ — قراءة فقط عبر FieldsApi.listFields
// (لا تعديل على ميزة الحقول). الحقل بلا معرّف يُسقَط؛ المساحة الغائبة تبقى null.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

class IrrigationField {
  const IrrigationField({required this.id, required this.name, this.areaHa});
  final String id;
  final String name;
  final num? areaHa;
}

sealed class IrrigationFieldsState {
  const IrrigationFieldsState();
}

class IrrigationFieldsLoading extends IrrigationFieldsState {
  const IrrigationFieldsLoading();
}

class IrrigationFieldsLoaded extends IrrigationFieldsState {
  const IrrigationFieldsLoaded(this.fields);
  final List<IrrigationField> fields;

  IrrigationField? byId(String? id) {
    for (final f in fields) {
      if (f.id == id) return f;
    }
    return null;
  }
}

class IrrigationFieldsFailed extends IrrigationFieldsState {
  const IrrigationFieldsFailed(this.error);
  final ApiException error;
}

/// يحمّل حقول المستأجر. [loader] قابل للحقن في الاختبارات.
class IrrigationFieldsCubit extends Cubit<IrrigationFieldsState> {
  IrrigationFieldsCubit({Future<List<Map<String, dynamic>>> Function()? loader})
    : _loader = loader ?? FieldsApi.instance.listFields,
      super(const IrrigationFieldsLoading());

  final Future<List<Map<String, dynamic>>> Function() _loader;

  Future<void> load() async {
    emit(const IrrigationFieldsLoading());
    try {
      final rows = await _loader();
      if (isClosed) return;
      final fields = <IrrigationField>[];
      for (final r in rows) {
        final id = (r['field_id'] ?? r['id'])?.toString();
        if (id == null || id.isEmpty) continue;
        final area = r['area_ha'];
        fields.add(
          IrrigationField(
            id: id,
            name: (r['name'] ?? r['field_name'] ?? id).toString(),
            areaHa: area is num ? area : null,
          ),
        );
      }
      emit(IrrigationFieldsLoaded(fields));
    } catch (e) {
      if (!isClosed) emit(IrrigationFieldsFailed(ApiException.from(e)));
    }
  }
}
