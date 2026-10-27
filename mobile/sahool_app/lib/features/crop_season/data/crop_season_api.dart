// SAHOOL — features/crop_season/data/crop_season_api.dart
// نقاط ميزة «المواسم والأطوار». يملكه وكيل الميزة.
//
// المصدر (services/sahool-platform/api/routers):
//   GET   /api/v1/fields/{id}/seasons               fields.py:list_seasons   → [SeasonSummary]
//   POST  /api/v1/fields/{id}/seasons               fields.py:create_season  → SeasonSummary (يحترم Idempotency-Key)
//   PATCH /api/v1/fields/{id}/seasons/{sid}         fields.py:update_season  → SeasonSummary
//   GET   /api/v1/fields/{id}/seasons/{sid}/state   seasons.py               → field_season_state.v1
//   GET   /api/v1/fields/{id}/phenology             phenology.py             → {available, timeline, ...}
//   GET   /api/v1/fields/{id}/stage-actions         phenology.py             → {available, suggestions, ...}
//   GET   /api/v1/crop-cards                        crop_cards.py            → {crops:[{crop_id,name_ar}]}
//
// لا نستعمل /api/v1/seasons: يُعاد كتابته في nginx إلى خدمة scout-ingest
// (season_api.py — «سجلّ الموسم» خلف الراية SEASON_ENTRY_ENABLED، افتراضيّاً مطفأة)،
// وليس مصدر مواسم الحقل الذي تقرؤه الفينولوجيا والويب.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'season_models.dart';

class CropSeasonApi {
  CropSeasonApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final CropSeasonApi instance = CropSeasonApi();
  final ApiClient _client;

  String _f(String fieldId) => '/api/v1/fields/${Uri.encodeComponent(fieldId)}';

  /// مواسم الحقل، الأحدث أوّلاً.
  Future<List<Season>> listSeasons(String fieldId) async {
    final r = await _client.get('${_f(fieldId)}/seasons');
    return asJsonList(r).map(Season.fromJson).toList();
  }

  /// ينشئ موسماً نشطاً. الخادم يُغلق أيّ موسم نشط سابق للحقل ضمن نفس المعاملة.
  Future<Season> createSeason(
    String fieldId,
    Map<String, dynamic> body, {
    required IdempotencyKey idempotencyKey,
  }) async => Season.fromJson(
    await createSeasonRaw(fieldId, body, idempotencyKey: idempotencyKey),
  );

  /// كـ[createSeason] لكن بالردّ كما هو (سجلّ العمليّات المعلّقة يحفظ النتيجة).
  Future<Map<String, dynamic>> createSeasonRaw(
    String fieldId,
    Map<String, dynamic> body, {
    required IdempotencyKey idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '${_f(fieldId)}/seasons',
      data: body,
      idempotencyKey: idempotencyKey,
    ),
  );

  /// تحديث جزئيّ (الحقول الممرَّرة فقط) أو انتقال حالة (`status`).
  /// الخادم لا يقرأ Idempotency-Key هنا؛ نمرّره ليُعاد الطلب بأمان على 502/503/504
  /// (التحديث نفسه متساوي القوّة: نفس القيم/نفس الحالة ⇒ لا تغيير).
  Future<Season> updateSeason(
    String fieldId,
    String seasonId,
    Map<String, dynamic> body, {
    required IdempotencyKey idempotencyKey,
  }) async {
    final r = await _client.patch(
      '${_f(fieldId)}/seasons/${Uri.encodeComponent(seasonId)}',
      data: body,
      idempotencyKey: idempotencyKey,
    );
    return Season.fromJson(asJsonMap(r));
  }

  /// الحقيقة التشغيليّة الموحّدة للحقل-الموسم.
  Future<Map<String, dynamic>> getSeasonState(
    String fieldId,
    String seasonId,
  ) async {
    final r = await _client.get(
      '${_f(fieldId)}/seasons/${Uri.encodeComponent(seasonId)}/state',
    );
    return asJsonMap(r);
  }

  /// خطّ زمن مراحل نموّ الموسم النشط.
  Future<Phenology> getPhenology(String fieldId) async {
    final r = await _client.get('${_f(fieldId)}/phenology');
    return Phenology.fromJson(asJsonMap(r));
  }

  /// إجراءات الطور الحاليّ المقترحة (إرشاديّة، لا تُنشئ مهامّ).
  Future<StageActions> getStageActions(String fieldId) async {
    final r = await _client.get('${_f(fieldId)}/stage-actions');
    return StageActions.fromJson(asJsonMap(r));
  }

  /// فهرس بطاقات المحاصيل (crop_id + الاسم العربيّ) لاختيار المحصول بلا كتابة.
  Future<List<CropOption>> listCropCards() async {
    final r = asJsonMap(await _client.get('/api/v1/crop-cards'));
    return asWrappedJsonList(r, const [
      'crops',
    ]).map(CropOption.fromJson).where((c) => c.cropId.isNotEmpty).toList();
  }
}
