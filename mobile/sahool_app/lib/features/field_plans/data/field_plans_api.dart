// SAHOOL — features/field_plans/data/field_plans_api.dart
// نقاط «خطط الحقل» على الجوّال: الوصفة (معدّل متغيّر محفوظ) وخطّة أخذ العيّنات.
// كلّها قراءات GET حقيقيّة لها معالج في الخادم (يحرسها
// tests_v9/test_mobile_backend_contract.py):
//
//   • الوصفات المحفوظة — GET /api/v1/fields/{field_id}/prescriptions
//     (sahool-platform: api/routers/prescriptions.py::list_prescriptions، field:view)
//     ⇒ {field_id, prescriptions[], total, note_ar?}. الويب يقرأ النقطة نفسها
//     (frontend/src/services/api/fieldDetail.ts::fetchPrescriptions).
//   • خطّة أخذ عيّنات التربة — GET /api/raster/v1/fields/{field_id}/soil/sampling-plan
//     (raster-service: routers/soil_tiles.py::field_soil_sampling_plan) ⇒ GeoJSON
//     FeatureCollection نقاط + computed. بلا مصدر تربة ⇒ computed:false وfeatures:[]
//     (لا نقاط مختلَقة). الويب يقرأها كذلك (frontend/src/services/api.ts::fetchSoilSamplingPlan).
//     الخادم يقصّ على حدّ الحقل (poly) وbbox، فنقرأ الهندسة أوّلاً من
//     GET /api/v1/fields/{field_id} (FieldsApi.getField).
//
// لا نقطة «وصفة» أو «خطّة مسح» أخرى لها معالج يصل من البوّابة اليوم: خطّة soil-service
// المحفوظة (GET /v1/fields/{id}/soil/sampling-plans/current) غير مكشوفة عبر
// /api/soil/ (قائمة _SOIL_ROUTES في service_proxy.py تردّها 404)، فلا تُستدعى هنا.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_shape.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/maps/geo/geo_json.dart';

class FieldPlansApi {
  FieldPlansApi([ApiClient? client, FieldsApi? fieldsApi])
      : _client = client ?? ApiClient.instance,
        _fields = fieldsApi ?? FieldsApi(client ?? ApiClient.instance);

  static final FieldPlansApi instance = FieldPlansApi();

  final ApiClient _client;
  final FieldsApi _fields;

  /// قائمة الحقول (لاختيار الحقل) — الشكل الخام لـGET /api/v1/fields.
  Future<List<Map<String, dynamic>>> listFields() => _fields.listFields();

  /// الوصفات المحفوظة للحقل (الأحدث أوّلاً) — JSON الخادم الخام.
  Future<Map<String, dynamic>> fetchPrescriptions(String fieldId) async =>
      asJsonMap(
        await _client.get(
          '/api/v1/fields/${Uri.encodeComponent(fieldId)}/prescriptions',
        ),
      );

  /// خطّة أخذ عيّنات التربة للحقل — JSON الخادم الخام. بلا حدّ مرسوم يُرسَل
  /// الطلب بلا قصّ ويقول الخادم computed:false بصدق.
  Future<Map<String, dynamic>> fetchSoilSamplingPlan(
    String fieldId, {
    int zones = 3,
    int samplesPerZone = 1,
  }) async {
    final detail = await _fields.getField(fieldId);
    final query = <String, dynamic>{
      'zones': '$zones',
      'samples_per_zone': '$samplesPerZone',
      ...clipQueryFor(FieldGeometry.tryParse(detail['geometry'])),
    };
    return asJsonMap(
      await _client.get(
        '/api/raster/v1/fields/${Uri.encodeComponent(fieldId)}/soil/sampling-plan',
        query: query,
      ),
    );
  }

  /// bbox (minLon,minLat,maxLon,maxLat) وpoly (lng,lat;...) من الحلقة الخارجيّة
  /// للجزء الأوّل — كما يبنيهما الويب (cdseClipParams) وMapsApi.indicatorTileUrl.
  static Map<String, String> clipQueryFor(FieldGeometry? geometry) {
    if (geometry == null || geometry.isEmpty) return const {};
    final ring = geometry.polygons.first.outer;
    if (ring.length < 3) return const {};
    var w = double.infinity, s = double.infinity;
    var e = double.negativeInfinity, n = double.negativeInfinity;
    for (final p in ring) {
      if (p.longitude < w) w = p.longitude;
      if (p.longitude > e) e = p.longitude;
      if (p.latitude < s) s = p.latitude;
      if (p.latitude > n) n = p.latitude;
    }
    return {
      'bbox': '$w,$s,$e,$n',
      'poly': ring.map((p) => '${p.longitude},${p.latitude}').join(';'),
    };
  }
}
