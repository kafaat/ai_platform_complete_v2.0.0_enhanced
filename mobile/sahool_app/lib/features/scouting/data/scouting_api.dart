// SAHOOL — features/scouting/data/scouting_api.dart
// نقاط الاستكشاف الميدانيّ. يملكه وكيل ميزة scouting.
//
// المصادر (مقروءة من الخادم، لا مُخمَّنة):
//   GET  /api/v1/scouting/pins?field_id=   api/routers/scouting.py:77
//        ⇒ {field_id, pins:[ScoutingPin.to_dict], total, note_ar?}
//   GET  /api/v1/scouting/taxonomy?crop=   api/routers/scouting.py:113
//        ⇒ {crop, issues:[{code, category, name_ar}]}
//   POST /api/v1/fields/{id}/pins          api/routers/fields.py:3845
//        جسم PinCreateRequest (api/api_models.py:374)؛ idempotent عبر
//        ON CONFLICT (pin_id) — لذا pin_id ثابت لنيّة المستخدم = قيمة مفتاح
//        Idempotency-Key نفسها. يردّ الدبّوس + persisted (false ⇒ لم يُحفظ).
//   POST /api/edge/v1/inference/pest-detect (service_proxy.py:172 → edge-inference
//        main.py:223) multipart: file + field_id (Form مطلوب ⇒ 422 بدونه) + crop.
//
// لا نقطة تخزين صور في المنصّة (photo_uri نصّ فقط): الصور تبقى على الجهاز.
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'scouting_models.dart';

/// مسار إنشاء دبّوس لحقل (يُستعمل أيضاً في عمليّة صندوق الإرسال).
String scoutingPinCreatePath(String fieldId) =>
    '/api/v1/fields/${Uri.encodeComponent(fieldId)}/pins';

const String kPestDetectPath = '/api/edge/v1/inference/pest-detect';

class ScoutingApi {
  ScoutingApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final ScoutingApi instance = ScoutingApi();
  final ApiClient _client;

  /// دبابيس الحقل المُخزَّنة، الأحدث أوّلاً.
  Future<ScoutingPinsPage> listPins(String fieldId) async {
    final r = asJsonMap(
      await _client.get('/api/v1/scouting/pins', query: {'field_id': fieldId}),
    );
    final pins = asJsonList(r['pins']).map(ScoutingPin.fromJson).toList();
    final note = r['note_ar']?.toString();
    return ScoutingPinsPage(
      pins: pins,
      noteAr: (note == null || note.isEmpty) ? null : note,
    );
  }

  /// مشاكل محصول من تصنيف الخادم. محصول غير معروف ⇒ قائمة فارغة (من الخادم).
  Future<List<TaxonomyIssue>> cropIssues(String crop) async {
    final r = asJsonMap(
      await _client.get('/api/v1/scouting/taxonomy', query: {'crop': crop}),
    );
    return asJsonList(
      r['issues'],
    ).map(TaxonomyIssue.fromJson).whereType<TaxonomyIssue>().toList();
  }

  /// ينشئ دبّوساً. [body] جسم PinCreateRequest كاملاً (يحوي pin_id وfield_id).
  Future<Map<String, dynamic>> createPin(
    String fieldId,
    Map<String, dynamic> body, {
    required IdempotencyKey idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      scoutingPinCreatePath(fieldId),
      data: body,
      idempotencyKey: idempotencyKey,
    ),
  );

  /// كشف الآفات من صورة. [fieldId] مطلوب: الخادم يعرّفه Form(...) ويرفض 422
  /// بدونه (كان المستشار يرسله بلا حقل فيفشل دائماً). multipart لا يُعاد تلقائيّاً.
  Future<PestDetectResult> detectPest({
    required String fieldId,
    required Uint8List bytes,
    required String filename,
    String? crop,
  }) async {
    if (fieldId.isEmpty) {
      throw ArgumentError.value(fieldId, 'fieldId', 'مطلوب لكشف الآفات');
    }
    final form = FormData.fromMap({
      'file': MultipartFile.fromBytes(
        bytes,
        filename: filename,
        // الحافّة ترفض 415 أيّ نوع لا يبدأ بـimage/ (لا octet-stream).
        contentType: _imageType(filename),
      ),
      'field_id': fieldId,
      if (crop != null && crop.isNotEmpty) 'crop': crop,
    });
    final r = await _client.send(
      'POST',
      kPestDetectPath,
      data: form,
      contentType: 'multipart/form-data',
      sendTimeout: const Duration(seconds: 120),
      receiveTimeout: const Duration(seconds: 120),
    );
    return PestDetectResult.fromJson(asJsonMap(r));
  }

  static DioMediaType _imageType(String filename) {
    final lower = filename.toLowerCase();
    if (lower.endsWith('.png')) return DioMediaType('image', 'png');
    if (lower.endsWith('.webp')) return DioMediaType('image', 'webp');
    if (lower.endsWith('.heic')) return DioMediaType('image', 'heic');
    return DioMediaType('image', 'jpeg');
  }
}
