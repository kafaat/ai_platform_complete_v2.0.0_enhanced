// SAHOOL — features/fields/presentation/workspace/workspace_deps.dart
// تبعيّات مساحة عمل الحقل (واجهات البرمجة) + Cubit «مساحة الموسم» المشترك بين
// تبويبات النظرة العامّة والموسم والتربة (طلب واحد لا ثلاثة).
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/satellite/data/satellite_api.dart';

import '../common/load_cubit.dart';

class WorkspaceDeps {
  WorkspaceDeps({
    FieldsApi? fields,
    SatelliteApi? satellite,
    IrrigationApi? irrigation,
  }) : fields = fields ?? FieldsApi.instance,
       satellite = satellite ?? SatelliteApi.instance,
       irrigation = irrigation ?? IrrigationApi.instance;

  final FieldsApi fields;
  final SatelliteApi satellite;
  final IrrigationApi irrigation;
}

/// GET /api/v1/fields/{id}/season-workspace — نموذج قراءة موحّد: field
/// (FieldDetail) · active_season · readiness · canonical_state ·
/// recommendations · tasks · activities · soil_tests · next_actions · gaps.
class SeasonWorkspaceCubit extends LoadCubit<Map<String, dynamic>> {
  SeasonWorkspaceCubit(WorkspaceDeps deps, String fieldId)
    : super(() => deps.fields.fetchSeasonWorkspace(fieldId));
}

Map<String, dynamic> wMap(Object? v) =>
    v is Map ? v.cast<String, dynamic>() : const <String, dynamic>{};

List<Map<String, dynamic>> wList(Object? v) => v is List
    ? v.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList()
    : const [];
