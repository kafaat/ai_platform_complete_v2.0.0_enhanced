// SAHOOL — features/maps/io/data/maps_io_api.dart
// نقاط حزمة الاستيراد/مشي GPS/الدمج والتقسيم. أشكال الطلبات مقروءة من الخادم:
//   • POST /api/v1/fields/import — FieldImportRequest (field_models.py):
//     format ∈ {geojson, kml, gps}؛ content للملفّ، points [[lon,lat],...] لـgps؛
//     الخادم يأخذ **أوّل حلقة خارجيّة فقط** (geo_import.py) ⇒ مضلّع واحد لكلّ طلب.
//     Idempotency-Key يُحترَم (routers/fields.py → _persist_field → _idempotent).
//   • POST /api/v1/gis/union · /api/v1/gis/split — معاينة dry-run (routers/gis_kernel.py)
//     خلف FEATURE_GIS_KERNEL: مُطفأة ⇒ 404. لا تكتب شيئاً.
//   • POST /api/v1/fields/merge · /api/v1/fields/split — الالتزام الذرّيّ (يحذف
//     المصادر)؛ يقبل Idempotency-Key.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

class MapsIoApi {
  MapsIoApi([ApiClient? client])
    : _client = client ?? ApiClient.instance,
      _fields = FieldsApi(client);
  static final MapsIoApi instance = MapsIoApi();
  final ApiClient _client;
  final FieldsApi _fields;

  /// قائمة الحقول (GET /api/v1/fields) — عبر FieldsApi (قراءة عابرة للميزة).
  Future<List<Map<String, dynamic>>> listFields() => _fields.listFields();

  /// استيراد حدّ واحد. [format]='geojson'|'kml' مع [content]، أو 'gps' مع [points].
  Future<Map<String, dynamic>> importBoundary({
    required String format,
    required String name,
    required IdempotencyKey idempotencyKey,
    String? content,
    List<List<double>>? points,
    String? farmId,
    Map<String, dynamic>? boundaryMetadata,
  }) async {
    assert(format == 'gps' ? points != null : content != null);
    final r = await _client.post(
      '/api/v1/fields/import',
      data: {
        'format': format,
        'name': name,
        if (content != null) 'content': content,
        if (points != null) 'points': points,
        if (farmId != null && farmId.isNotEmpty) 'farm_id': farmId,
        if (boundaryMetadata != null) 'boundary_metadata': boundaryMetadata,
      },
      idempotencyKey: idempotencyKey,
    );
    return asJsonMap(r);
  }

  /// معاينة اتّحاد حقلين (لا كتابة). يردّ `{operation, dry_run, result}`.
  Future<Map<String, dynamic>> previewUnion(
    String fieldIdA,
    String fieldIdB,
  ) async => asJsonMap(
    await _client.post(
      '/api/v1/gis/union',
      data: {'field_id_a': fieldIdA, 'field_id_b': fieldIdB},
    ),
  );

  /// معاينة تقسيم حقل بخطّ (لا كتابة). يردّ `{part_count, result: GeometryCollection}`.
  Future<Map<String, dynamic>> previewSplit(
    String fieldId,
    Map<String, dynamic> blade,
  ) async => asJsonMap(
    await _client.post(
      '/api/v1/gis/split',
      data: {'field_id': fieldId, 'blade': blade},
    ),
  );

  /// دمج ذرّيّ: يُنشئ الحقل المدموج ويحذف المصادر في معاملة واحدة.
  Future<Map<String, dynamic>> mergeFields({
    required List<String> sourceFieldIds,
    required String name,
    required Map<String, dynamic> geometry,
    required IdempotencyKey idempotencyKey,
    String? farmId,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/fields/merge',
      data: {
        'source_field_ids': sourceFieldIds,
        'name': name,
        'geometry': geometry,
        if (farmId != null && farmId.isNotEmpty) 'farm_id': farmId,
      },
      idempotencyKey: idempotencyKey,
    ),
  );

  /// تقسيم ذرّيّ: يُنشئ الحقول الوليدة (٢..١٠) ويحذف الأصل في معاملة واحدة.
  Future<List<Map<String, dynamic>>> splitField({
    required String sourceFieldId,
    required List<({String name, Map<String, dynamic> geometry})> children,
    required IdempotencyKey idempotencyKey,
    String? inheritCrop,
  }) async => asJsonList(
    await _client.post(
      '/api/v1/fields/split',
      data: {
        'source_field_id': sourceFieldId,
        'children': [
          for (final c in children)
            {
              'name': c.name,
              'geometry': c.geometry,
              if (inheritCrop != null) 'crop': inheritCrop,
            },
        ],
      },
      idempotencyKey: idempotencyKey,
    ),
  );
}
