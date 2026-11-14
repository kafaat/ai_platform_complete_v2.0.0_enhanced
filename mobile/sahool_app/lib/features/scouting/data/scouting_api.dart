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
//   v257: الجسم يحمل location_source (gps | manual | field_centroid | unknown) وaccuracy_m
//        (لـgps فقط). لا صورة في جسم الدبّوس ولا photo_uri.
//
//   v260: صورة المشاهدة دليلٌ مستقلّ في scout-ingest (جدول scout_photo_evidence، المصدر
//        الوحيد لها) بإيصالٍ مستقلّ عن إيصال الدبّوس:
//        POST /api/v1/scouting-media/fields/{field}/pins/{pin}/photo  بايتات JPEG/PNG/WebP
//             خامّاً + X-Content-SHA256 ⇒ {evidence_id, field_id, pin_id, sha256, persisted,
//             verification_state: bytes_verified, review_state: unreviewed, idempotent}
//        GET  …/photo ⇒ نفسه + url (HTTPS موقَّع لـ120 ثانية، Cache-Control: private, no-store)
//        الخادم يردّ 200 فقط بعد التحقّق من وجود الكائن في المخزن المشترك (HEAD).
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'scouting_models.dart';

/// مسار إنشاء دبّوس لحقل (يُستعمل أيضاً في عمليّة صندوق الإرسال).
String scoutingPinCreatePath(String fieldId) =>
    '/api/v1/fields/${Uri.encodeComponent(fieldId)}/pins';

const String kPestDetectPath = '/api/edge/v1/inference/pest-detect';

/// نوع عمليّة صندوق الإرسال لرفع صورة دبّوس (بعد عمليّة observation_create لنفس
/// الحقل). جسمها {field_id, pin_id, sha256} فقط: البايتات لا تُسلسَل في Hive، تُقرأ
/// من نسخة الجهاز عند الإرسال وتُرفض إن تغيّرت بصمتها (offline_sync_api.dart).
const String kObservationPhotoKind = 'observation_photo_upload';

/// مسار صورة دبّوس في scout-ingest (عبر بوّابة nginx، لا مسار في المنصّة).
String scoutingPhotoPath(String fieldId, String pinId) =>
    '/api/v1/scouting-media/fields/${Uri.encodeComponent(fieldId)}'
    '/pins/${Uri.encodeComponent(pinId)}/photo';

/// نوع المحتوى الذي يقبله الخادم: JPEG/PNG/WebP فقط (يفكّ الصورة كاملةً ويطابق النوع).
String scoutingPhotoType(String filename) {
  final lower = filename.toLowerCase();
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.webp')) return 'image/webp';
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
  throw const FormatException('نوع الصورة غير مدعوم؛ استخدم JPG أو PNG أو WebP.');
}

/// 2xx لا يكفي: الإيصال يجب أن يطابق الحقل والدبّوس وبصمة هذه البايتات بالضبط.
Map<String, dynamic> verifyScoutingPhotoReceipt(
  dynamic response,
  String fieldId,
  String pinId,
  String digest,
) {
  final body = asJsonMap(response);
  final evidence = body['evidence_id'];
  if (body['persisted'] != true ||
      body['field_id'] != fieldId ||
      body['pin_id'] != pinId ||
      body['sha256'] != digest ||
      body['verification_state'] != 'bytes_verified' ||
      body['review_state'] != 'unreviewed' ||
      evidence is! String ||
      evidence.isEmpty) {
    throw const FormatException(
      'إيصال حفظ الصورة لا يطابق الحقل والدبوس وبصمة الملف.',
    );
  }
  return body;
}

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

  /// يرفع صورة دبّوس محفوظ. يرمي [FormatException] إن لم يطابق الإيصال هذه البايتات.
  Future<Map<String, dynamic>> uploadPinPhoto({
    required String fieldId,
    required String pinId,
    required Uint8List bytes,
    required String filename,
    IdempotencyKey? idempotencyKey,
  }) async {
    final digest = crypto.sha256.convert(bytes).toString();
    final response = await _client.send(
      'POST',
      scoutingPhotoPath(fieldId, pinId),
      data: bytes,
      headers: {'X-Content-SHA256': digest},
      contentType: scoutingPhotoType(filename),
      idempotencyKey: idempotencyKey,
      sendTimeout: const Duration(seconds: 120),
      receiveTimeout: const Duration(seconds: 120),
    );
    return verifyScoutingPhotoReceipt(response, fieldId, pinId, digest);
  }

  /// رابط HTTPS مؤقّت (120 ثانية) لصورة الدبّوس المشتركة، لا رابط عامّ دائم.
  Future<Map<String, dynamic>> photoForPin(String fieldId, String pinId) async {
    final data = asJsonMap(
      await _client.get(scoutingPhotoPath(fieldId, pinId)),
    );
    final url = data['url'];
    if (data['field_id'] != fieldId ||
        data['pin_id'] != pinId ||
        data['persisted'] != true ||
        data['verification_state'] != 'bytes_verified' ||
        url is! String ||
        !url.startsWith('https://')) {
      throw const FormatException(
        'المرجع المؤقت للصورة غير موثوق أو لا يطابق المشاهدة.',
      );
    }
    return data;
  }

  Future<List<Map<String, dynamic>>> diagnosisSymptoms() async =>
      asJsonList(asJsonMap(await _client.get('/api/v1/diagnose/symptoms'))['symptoms']);

  Future<Map<String, dynamic>> assessSymptoms(ScoutingField field, List<String> symptoms) async =>
      asJsonMap(await _client.post('/api/v1/diagnose', data: {
        'field_id': field.id, 'crop': field.crop, 'symptoms': symptoms,
      }));

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
