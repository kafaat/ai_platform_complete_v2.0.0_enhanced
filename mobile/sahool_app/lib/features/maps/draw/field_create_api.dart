// SAHOOL — features/maps/draw/field_create_api.dart
// إنشاء حقل من حدٍّ مرسوم: POST /api/v1/fields بعقد `FieldCreateRequest`
// (services/sahool-platform/api/field_models.py) كاملاً، لا بالمجموعة الجزئيّة
// التي يرسلها `FieldsApi.createField`:
//   • `pivot` {center:{lon,lat}, radius_m, start/end_angle_deg, vertices:96} مع
//     `irrigation_type: "pivot"` — شرط الخادم كي يولّد المضلّع القانونيّ من
//     المعاملات (pivot_geometry.maybe_canonicalize_pivot_geometry) بدل حفظ مضلّع خام.
//   • `irrigation_type` في طلب الإنشاء نفسه (كان يُرسَل بـPATCH ثانٍ قد يفشل منفرداً).
//   • `farm_id` (فحص التكرار في الخادم يجري ضمن المزرعة).
//   • `boundary_metadata` (مصدر الحدّ: رسم/مستطيل/محور/استيراد/GPS).
//   • ترويسة `Idempotency-Key` ثابتة للنيّة: الخادم يحترمها (`_idem_key` ⇒
//     `_idempotent`)، فإعادة المحاولة بعد انقطاع تعيد الحقل نفسه بدل 409
//     «اسم مكرّر».
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

/// حمولة إنشاء الحقل. المفاتيح الاختياريّة تُرسَل فقط إن وُجدت.
class FieldCreateDraft {
  const FieldCreateDraft({
    required this.name,
    required this.geometry,
    this.farmId,
    this.pivot,
    this.crop,
    this.waterSource,
    this.irrigationType,
    this.soilType,
    this.boundarySource,
  });

  final String name;
  final Map<String, dynamic> geometry;
  final String? farmId;
  final Map<String, dynamic>? pivot;
  final String? crop;
  final String? waterSource;
  final String? irrigationType;
  final String? soilType;

  /// manual | rectangle | pivot | import_geojson | import_kml | gps
  final String? boundarySource;

  Map<String, dynamic> toJson() => {
    'name': name,
    'geometry': geometry,
    if (farmId != null) 'farm_id': farmId,
    if (crop != null) 'crop': crop,
    if (soilType != null) 'soil_type': soilType,
    if (waterSource != null) 'water_source': waterSource,
    // المحور يُلزم irrigation_type=pivot وإلّا يتجاهل الخادم معاملاته.
    if (pivot != null)
      'irrigation_type': 'pivot'
    else if (irrigationType != null)
      'irrigation_type': irrigationType,
    if (pivot != null) 'pivot': pivot,
    if (boundarySource != null)
      'boundary_metadata': {'source': boundarySource, 'mode': 'mobile'},
  };
}

class FieldCreateApi {
  FieldCreateApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final FieldCreateApi instance = FieldCreateApi();
  final ApiClient _client;

  /// يردّ `FieldSummary` (field_id, area_ha, geometry, …). 422/409/404/503 تُرمى
  /// ApiException بتفاصيل الخادم (`detail.code`/`message_ar`).
  Future<Map<String, dynamic>> createField(
    FieldCreateDraft draft, {
    required IdempotencyKey idempotencyKey,
  }) => createFieldPayload(draft.toJson(), idempotencyKey: idempotencyKey);

  /// الإرسال بحمولة محفوظة كما هي (سجلّ العمليّات المعلّقة يعيد الحمولة الأصليّة
  /// نفسها، لا مسودّة النموذج الحاليّة).
  Future<Map<String, dynamic>> createFieldPayload(
    Map<String, dynamic> payload, {
    required IdempotencyKey idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/fields',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );
}
