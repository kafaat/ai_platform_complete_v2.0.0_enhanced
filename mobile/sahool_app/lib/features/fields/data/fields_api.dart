// SAHOOL — features/fields/data/fields_api.dart
// نقاط الحقول ومساحة عملها: القائمة، الإنشاء/الاستيراد/التحديث، سلسلة الإعداد
// (موسم ← فحص تربة ← تقدير إنتاجيّة)، والقراءات المرتبطة بحقل (الحالة الموحّدة،
// المواسم، الأنشطة، الطقس، الخطّ الزمنيّ). يملكه وكيل ميزة الحقول.
//
// صدق: 422 (هندسة غير صالحة) / 409 (تداخل-تكرار) / 503 (DB/طقس) / 404 تُرمى
// ApiException ليعرض الـUI حالة صادقة — لا حقل ولا قراءة مُلفَّقة.
// الكتابات تقبل [IdempotencyKey]: ولّده مرّة عند فتح النموذج وأعِد استعماله.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

class FieldsApi {
  FieldsApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final FieldsApi instance = FieldsApi();
  final ApiClient _client;

  /// قائمة حقول المستخدم مباشرةً من مصدر الحقيقة للحقول
  /// (GET /api/v1/fields). تُستخدم لشاشة «حقولي» بدل الاعتماد على dashboard،
  /// كي تظهر كل الحقول حتى لو لم تدخل بعد في مؤشرات اللوحة.
  Future<List<Map<String, dynamic>>> listFields() async {
    final r = await _client.get('/api/v1/fields');
    return asJsonList(r);
  }

  /// مساحة عمل موسم كاملة لحقل واحد: ملف الحقل + الموسم النشط + الجاهزية
  /// + الحالة الموحدة + التوصيات + المهام + الأنشطة + التربة + خط زمني مختصر.
  Future<Map<String, dynamic>> fetchSeasonWorkspace(String fieldId) async {
    final r = await _client.get('/api/v1/fields/$fieldId/season-workspace');
    return asJsonMap(r);
  }

  /// الحالة القانونيّة الموحّدة للحقل (Canonical Field State) —
  /// GET /api/v1/fields/{field_id}/state. مصدر الحقيقة الواحد الذي تمرّ عبره
  /// القرارات/التنبيهات: صلاحيّة القرار (validity)، نمط التنفيذ (execution_mode)،
  /// والحقائق الزراعيّة (agronomic.operational_truths: حيويّة المحصول/صنف الملوحة)
  /// مع أسباب عربيّة (reasons_ar). حارس الشكل (_asMap) كبقيّة المسارات. صدق: غياب
  /// مصدر ⇒ الخادم يردّ حالة «بيانات ناقصة» (insufficient) لا أرقاماً مُلفَّقة.
  Future<Map<String, dynamic>> getFieldState(String fieldId) async {
    final r = await _client.get('/api/v1/fields/$fieldId/state');
    return asJsonMap(r);
  }

  /// ينشئ حقلاً من مضلّع مرسوم/مستورَد (POST /api/v1/fields). [geometry] لازم
  /// (GeoJSON Polygon). يردّ الحقل المُنشأ (FieldSummary) بهندسته كي ترسمه الواجهة.
  Future<Map<String, dynamic>> createField({
    required String name,
    required Map<String, dynamic> geometry,
    String? crop,
    String? soilType,
    String? waterSource,
    String? manager,
    String? farmId,
    IdempotencyKey? idempotencyKey,
  }) async {
    final r = await _client.post(
      '/api/v1/fields',
      data: {
        'name': name,
        'geometry': geometry,
        if (crop != null) 'crop': crop,
        if (soilType != null) 'soil_type': soilType,
        if (waterSource != null) 'water_source': waterSource,
        if (manager != null) 'manager': manager,
        if (farmId != null) 'farm_id': farmId,
      },
      idempotencyKey: idempotencyKey,
    );
    return asJsonMap(r);
  }

  /// تحديث جزئيّ لتفاصيل حقل (ملء تدريجيّ) — PATCH /api/v1/fields/{id}.
  /// [advanced] يحوي الأعمدة المُرسَلة فقط (مثل irrigation_type، soil_ph…)؛
  /// تُحدَّث المُرسَلة فقط ولا تُمسح غير المُرسَلة. يردّ الحقل المُحدَّث (FieldDetail).
  Future<Map<String, dynamic>> updateField(
    String fieldId,
    Map<String, dynamic> advanced, {
    IdempotencyKey? idempotencyKey,
  }) async {
    final r = await _client.patch(
      '/api/v1/fields/$fieldId',
      data: advanced,
      idempotencyKey: idempotencyKey,
    );
    return asJsonMap(r);
  }

  /// يستورد حدّ حقل من نصّ GeoJSON (POST /api/v1/fields/import، format=geojson).
  /// الخادم يحلّل المحتوى إلى Polygon ثمّ يعيد استخدام مسار الإنشاء. خطأ التحليل
  /// ⇒ 400 يُرمى ليُعرَض بصدق. يردّ الحقل المُنشأ (FieldSummary).
  Future<Map<String, dynamic>> importFieldGeoJson(
    String content, {
    required String name,
    String? crop,
    String? soilType,
    String? waterSource,
    String? manager,
    String? farmId,
    IdempotencyKey? idempotencyKey,
  }) async {
    final r = await _client.post(
      '/api/v1/fields/import',
      data: {
        'format': 'geojson',
        'content': content,
        'name': name,
        if (crop != null) 'crop': crop,
        if (soilType != null) 'soil_type': soilType,
        if (waterSource != null) 'water_source': waterSource,
        if (manager != null) 'manager': manager,
        if (farmId != null) 'farm_id': farmId,
      },
      idempotencyKey: idempotencyKey,
    );
    return asJsonMap(r);
  }

  /// يستورد حدّ حقل من نصّ KML (POST /api/v1/fields/import، format=kml).
  Future<Map<String, dynamic>> importFieldKml(
    String content, {
    required String name,
    String? crop,
    String? soilType,
    String? waterSource,
    String? manager,
    String? farmId,
    IdempotencyKey? idempotencyKey,
  }) async {
    final r = await _client.post(
      '/api/v1/fields/import',
      data: {
        'format': 'kml',
        'content': content,
        'name': name,
        if (crop != null) 'crop': crop,
        if (soilType != null) 'soil_type': soilType,
        if (waterSource != null) 'water_source': waterSource,
        if (manager != null) 'manager': manager,
        if (farmId != null) 'farm_id': farmId,
      },
      idempotencyKey: idempotencyKey,
    );
    return asJsonMap(r);
  }

  /// ينشئ موسماً للحقل (POST /api/v1/fields/{field_id}/seasons).
  /// [crop] لازم (يُرسَل ضمن مصفوفة crops). الحقول الأخرى اختياريّة وتُرسَل فقط
  /// إن وُجدت (ملء تدريجيّ). يردّ الموسم المُنشأ. صدق: الخطأ يُرمى ليُعرَض كما هو.
  Future<Map<String, dynamic>> createSeason(
    String fieldId, {
    required String crop,
    String? cultivar,
    String? irrigationType,
    String? landLevelingDate, // "YYYY-MM-DD" — تسوية الأرض
    String? plowingDate, // "YYYY-MM-DD" — حراثة الأرض
    String? sowingDate, // "YYYY-MM-DD"
    String? seasonEnd, // "YYYY-MM-DD"
    num? targetYieldKgHa,
    num? seedRateKgHa,
    num? plantDensity, // نبات/م² (v42)
    num? rowSpacingCm, // سم (v42)
    String? seedVarietySource, // مصدر البذور (v42)
    String? tillageType,
    String? maturity, // early/medium/late
    num? actualYieldKgHa,
    String? notesAr,
    IdempotencyKey? idempotencyKey,
  }) async {
    final r = await _client.post(
      '/api/v1/fields/$fieldId/seasons',
      data: {
        'crops': [crop],
        if (cultivar != null) 'cultivar': cultivar,
        if (irrigationType != null) 'irrigation_type': irrigationType,
        if (landLevelingDate != null) 'land_leveling_date': landLevelingDate,
        if (plowingDate != null) 'plowing_date': plowingDate,
        if (sowingDate != null) 'sowing_date': sowingDate,
        if (seasonEnd != null) 'season_end': seasonEnd,
        if (targetYieldKgHa != null) 'target_yield_kg_ha': targetYieldKgHa,
        if (seedRateKgHa != null) 'seed_rate_kg_ha': seedRateKgHa,
        if (plantDensity != null) 'plant_density': plantDensity,
        if (rowSpacingCm != null) 'row_spacing_cm': rowSpacingCm,
        if (seedVarietySource != null) 'seed_variety_source': seedVarietySource,
        if (tillageType != null) 'tillage_type': tillageType,
        if (maturity != null) 'maturity': maturity,
        if (actualYieldKgHa != null) 'actual_yield_kg_ha': actualYieldKgHa,
        if (notesAr != null) 'notes_ar': notesAr,
      },
      idempotencyKey: idempotencyKey,
    );
    return asJsonMap(r);
  }

  /// يسجّل نتيجة فحص تربة مخبريّ (POST /api/v1/fields/{field_id}/soil-lab-tests).
  /// pH/المادّة العضويّة/CEC تُرسَل داخل result. كلّ الحقول اختياريّة (خطوة قابلة
  /// للتخطّي). يردّ السجلّ المُنشأ. صدق: الخطأ يُرمى ليُعرَض كما هو.
  Future<Map<String, dynamic>> submitSoilLabTest(
    String fieldId, {
    String? labName,
    String? sampledOn, // "YYYY-MM-DD"
    String? notesAr,
    num? ph,
    num? organicMatter,
    num? cec,
    num? ecDsM,
    num? waterEcDsM,
    num? nPpm,
    num? pPpm,
    num? kPpm,
    String? soilTexture,
    num? sampleDepthCm,
    String? attachmentId,
    IdempotencyKey? idempotencyKey,
  }) async {
    final result = <String, dynamic>{
      if (ph != null) 'ph': ph,
      if (organicMatter != null) 'organic_matter': organicMatter,
      if (cec != null) 'cec': cec,
      if (ecDsM != null) 'ec_ds_m': ecDsM,
      if (waterEcDsM != null) 'water_ec_ds_m': waterEcDsM,
      if (nPpm != null) 'n_ppm': nPpm,
      if (pPpm != null) 'p_ppm': pPpm,
      if (kPpm != null) 'k_ppm': kPpm,
      if (soilTexture != null && soilTexture.trim().isNotEmpty)
        'soil_texture': soilTexture.trim(),
      if (sampleDepthCm != null) 'sample_depth_cm': sampleDepthCm,
      if (attachmentId != null && attachmentId.trim().isNotEmpty)
        'attachment_id': attachmentId.trim(),
    };
    final r = await _client.post(
      '/api/v1/fields/$fieldId/soil-lab-tests',
      data: {
        if (labName != null) 'lab_name': labName,
        if (sampledOn != null) 'sampled_on': sampledOn,
        if (notesAr != null) 'notes_ar': notesAr,
        if (result.isNotEmpty) 'result': result,
      },
      idempotencyKey: idempotencyKey,
    );
    return asJsonMap(r);
  }

  /// يطلب تقدير إنتاجيّة الحقل (POST /api/v1/fields/{field_id}/yield-estimate).
  /// [crop] لازم. أيّام النموّ/متوسّط NDVI اختياريّان. يردّ التقدير (خطوة قابلة
  /// للتخطّي). صدق: الخطأ يُرمى ليُعرَض كما هو.
  Future<Map<String, dynamic>> requestYieldEstimate(
    String fieldId, {
    required String crop,
    int? daysInGrowing,
    num? avgNdviGrowing,
    IdempotencyKey? idempotencyKey,
  }) async {
    final r = await _client.post(
      '/api/v1/fields/$fieldId/yield-estimate',
      data: {
        'field_id': fieldId,
        'crop': crop,
        if (daysInGrowing != null) 'days_in_growing': daysInGrowing,
        if (avgNdviGrowing != null) 'avg_ndvi_growing': avgNdviGrowing,
      },
      idempotencyKey: idempotencyKey,
    );
    return asJsonMap(r);
  }

  /// مواسم الحقل، الأحدث أوّلاً (GET /api/v1/fields/{id}/seasons).
  /// كلّ عنصر SeasonSummary: {season_id, crops:[..], cultivar, sowing_date,
  /// season_end, status(planned/active/closed), target_yield_kg_ha, ...}.
  Future<List<Map<String, dynamic>>> fetchFieldSeasons(String fieldId) async {
    final r = await _client.get('/api/v1/fields/$fieldId/seasons');
    return asJsonList(r);
  }

  /// تسجيل عمليّة يوميّة من التطبيق (POST /api/v1/fields/{id}/activities).
  /// هذا يزيل فجوة القراءة فقط في الموبايل: السجلّ اليومي يُدخل من التطبيق نفسه.
  Future<Map<String, dynamic>> createFieldActivity(
    String fieldId, {
    required String activityType,
    String? titleAr,
    String? scheduledFor,
    String? performedOn,
    String? notes,
    IdempotencyKey? idempotencyKey,
  }) async {
    final payload = <String, dynamic>{
      'activity_type': activityType,
      if (titleAr != null && titleAr.trim().isNotEmpty)
        'title_ar': titleAr.trim(),
      if (scheduledFor != null && scheduledFor.isNotEmpty)
        'scheduled_for': scheduledFor,
      if (performedOn != null && performedOn.isNotEmpty)
        'performed_on': performedOn,
      if (notes != null && notes.trim().isNotEmpty)
        'details': {'notes': notes.trim()},
    };
    final r = await _client.post(
      '/api/v1/fields/$fieldId/activities',
      data: payload,
      idempotencyKey: idempotencyKey,
    );
    return asJsonMap(r);
  }

  /// عمليّات/أنشطة الحقل، الأحدث أوّلاً (GET /api/v1/fields/{id}/activities).
  /// كلّ عنصر ActivitySummary: {activity_id, activity_type, title_ar,
  /// scheduled_for, performed_on, status(planned/done), ...}.
  Future<List<Map<String, dynamic>>> fetchFieldActivities(
    String fieldId,
  ) async {
    final r = await _client.get('/api/v1/fields/$fieldId/activities');
    return asJsonList(r);
  }

  /// توصية ريّ بنمط FAO-56 من الطقس الحيّ ومحصول الموسم النشط
  /// (GET /api/v1/fields/{id}/weather/irrigation-advice). يردّ
  /// {crop, stage, urgency(none/low/moderate/high), recommended_mm, et0, kc,
  /// timing_ar, rationale_ar, soil_moisture_pct, source}. 503 إن تعذّر الطقس.
  Future<Map<String, dynamic>> fetchIrrigationAdvice(String fieldId) async {
    final r = await _client.get(
      '/api/v1/fields/$fieldId/weather/irrigation-advice',
    );
    return asJsonMap(r);
  }

  /// مخاطر أمراض فطريّة (agro-met) من الطقس الحيّ
  /// (GET /api/v1/fields/{id}/weather/disease-risk). يردّ
  /// {crop, temperature_c, humidity_pct, rain_mm_3d, risk_level(low/moderate/
  /// high), diseases_ar:[..], advice_ar, source}. 503 إن تعذّر الطقس.
  Future<Map<String, dynamic>> fetchDiseaseRisk(String fieldId) async {
    final r = await _client.get('/api/v1/fields/$fieldId/weather/disease-risk');
    return asJsonMap(r);
  }

  /// الخطّ الزمنيّ الموحّد للحقل (GET /api/v1/fields/{id}/unified-timeline).
  /// يردّ {events:[{timestamp, event_type, category, summary_ar, actor_id,
  /// payload}], total_events, category_counts, earliest_at, latest_at}؛ وقد
  /// يردّ note_ar/error عند تدهور القاعدة (صدق: لا تاريخ مخترَع).
  Future<Map<String, dynamic>> fetchUnifiedTimeline(String fieldId) async {
    final r = await _client.get(
      '/api/v1/fields/$fieldId/unified-timeline',
      query: {'limit': 100, 'newest_first': true},
    );
    return asJsonMap(r);
  }

  /// تفاصيل حقل واحد (GET /api/v1/fields/{id}) — FieldDetail: ملخّص الحقل
  /// (field_id, farm_id, name_ar, crop, area_ha, quality_grade, ...) + أعمدة
  /// التربة/الريّ المتقدّمة (soil_ph, soil_ec, soil_om, soil_n/p/k,
  /// irrigation_type, water_source...). 404 إن لم يكن الحقل ضمن المستأجِر.
  Future<Map<String, dynamic>> getField(String fieldId) async =>
      asJsonMap(await _client.get('/api/v1/fields/$fieldId'));

  /// أولويّات الحقل التشغيليّة (GET /api/v1/fields/{id}/priority-queue):
  /// {items:[{id, type(alert/task), title_ar, severity, due_at, ...}],
  /// degraded, warning_ar, note_ar}. العناصر من جداول alerts/field_tasks فقط.
  Future<Map<String, dynamic>> fetchFieldPriorityQueue(
    String fieldId, {
    int limit = 20,
  }) async => asJsonMap(
    await _client.get(
      '/api/v1/fields/$fieldId/priority-queue',
      query: {'limit': limit},
    ),
  );
}
