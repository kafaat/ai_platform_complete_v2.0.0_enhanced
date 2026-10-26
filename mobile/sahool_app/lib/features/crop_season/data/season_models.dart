// SAHOOL — features/crop_season/data/season_models.dart
// نماذج المواسم والأطوار كما يردّها الخادم حرفيّاً (لا حقل مُخمَّن):
//   SeasonSummary  → services/sahool-platform/api/season_models.py
//   phenology      → api/routers/phenology.py:_shape_phenology
//   stage-actions  → api/routers/phenology.py:_shape_stage_actions
// قيمة غائبة تبقى null وتُعرَض «غير مقيس»/«—»، لا صفراً.

/// حالة الموسم وانتقالاتها — مرآة api/season_lifecycle.py:SEASON_TRANSITIONS.
enum SeasonStatus {
  planned('planned', 'مُخطَّط'),
  active('active', 'نشط'),
  closed('closed', 'مُغلَق');

  const SeasonStatus(this.wire, this.labelAr);
  final String wire;
  final String labelAr;

  static SeasonStatus? parse(Object? raw) {
    for (final s in values) {
      if (s.wire == raw) return s;
    }
    return null;
  }

  /// الانتقالات المسموحة من هذه الحالة (المُغلَق نهائيّ).
  Set<SeasonStatus> get allowedTargets => switch (this) {
    SeasonStatus.planned => {SeasonStatus.active, SeasonStatus.closed},
    SeasonStatus.active => {SeasonStatus.closed},
    SeasonStatus.closed => const {},
  };

  bool canTransitionTo(SeasonStatus target) => allowedTargets.contains(target);
}

/// أنواع الريّ التي يقبلها الخادم (season_models._IRRIGATION_TYPES).
const Map<String, String> kIrrigationTypesAr = {
  'drip': 'تنقيط',
  'sprinkler': 'رشّ',
  'pivot': 'محوريّ',
  'flood': 'غمر',
  'subsurface': 'تحت سطحيّ',
  'rainfed': 'مطريّ',
};

double? _num(Object? v) {
  if (v is num) return v.toDouble();
  if (v is String) return double.tryParse(v);
  return null;
}

int? _int(Object? v) {
  if (v is int) return v;
  if (v is num) return v.toInt();
  if (v is String) return int.tryParse(v);
  return null;
}

String? _str(Object? v) {
  if (v == null) return null;
  final s = v.toString().trim();
  return s.isEmpty ? null : s;
}

List<String> _strList(Object? v) => v is List
    ? v.map((e) => e.toString()).where((e) => e.isNotEmpty).toList()
    : const [];

/// تاريخ «YYYY-MM-DD» من الخادم كتاريخ تقويميّ محلّيّ (بلا إزاحة منطقة).
DateTime? parseIsoDay(String? iso) {
  if (iso == null || iso.isEmpty) return null;
  final d = DateTime.tryParse(iso);
  if (d == null) return null;
  return DateTime(d.year, d.month, d.day);
}

/// «YYYY-MM-DD» للإرسال.
String isoDay(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}'
    '-${d.day.toString().padLeft(2, '0')}';

class Season {
  const Season({
    required this.seasonId,
    required this.fieldId,
    required this.crops,
    required this.statusRaw,
    this.cultivar,
    this.irrigationType,
    this.sowingDate,
    this.seasonEnd,
    this.targetYieldKgHa,
    this.actualYieldKgHa,
    this.notesAr,
    this.createdAt,
    this.rowVersion,
    this.calendarCheck,
  });

  final String seasonId;
  final String fieldId;
  final List<String> crops;
  final String statusRaw;
  final String? cultivar;
  final String? irrigationType;

  /// «YYYY-MM-DD» كما خُزّن.
  final String? sowingDate;
  final String? seasonEnd;
  final double? targetYieldKgHa;
  final double? actualYieldKgHa;
  final String? notesAr;
  final String? createdAt;
  final int? rowVersion;

  /// حارس تقويم الموسم (إرشاديّ) — يُرَدّ عند الإنشاء فقط.
  final Map<String, dynamic>? calendarCheck;

  SeasonStatus? get status => SeasonStatus.parse(statusRaw);
  String? get primaryCrop => crops.isEmpty ? null : crops.first;
  DateTime? get sowingDay => parseIsoDay(sowingDate);
  DateTime? get seasonEndDay => parseIsoDay(seasonEnd);

  factory Season.fromJson(Map<String, dynamic> j) => Season(
    seasonId: j['season_id']?.toString() ?? '',
    fieldId: j['field_id']?.toString() ?? '',
    crops: _strList(j['crops']),
    statusRaw: j['status']?.toString() ?? '',
    cultivar: _str(j['cultivar']),
    irrigationType: _str(j['irrigation_type']),
    sowingDate: _str(j['sowing_date']),
    seasonEnd: _str(j['season_end']),
    targetYieldKgHa: _num(j['target_yield_kg_ha']),
    actualYieldKgHa: _num(j['actual_yield_kg_ha']),
    notesAr: _str(j['notes_ar']),
    createdAt: _str(j['created_at']),
    rowVersion: _int(j['row_version']),
    calendarCheck: j['calendar_check'] is Map
        ? (j['calendar_check'] as Map).cast<String, dynamic>()
        : null,
  );
}

/// مرحلة في خطّ الزمن الطوريّ (core/season_phenology.season_timeline).
class PhenologyStage {
  const PhenologyStage({
    required this.stage,
    this.nameAr,
    this.startDate,
    this.endDate,
    this.status,
    this.keyActionAr,
    this.kc,
  });

  final String stage;
  final String? nameAr;
  final String? startDate;
  final String? endDate;

  /// past / current / upcoming.
  final String? status;
  final String? keyActionAr;
  final double? kc;

  factory PhenologyStage.fromJson(Map<String, dynamic> j) => PhenologyStage(
    stage: j['stage']?.toString() ?? '',
    nameAr: _str(j['name_ar']),
    startDate: _str(j['start_date']),
    endDate: _str(j['end_date']),
    status: _str(j['status']),
    keyActionAr: _str(j['key_action_ar']),
    kc: _num(j['kc']),
  );
}

class Phenology {
  const Phenology({
    required this.available,
    this.reasonAr,
    this.crop,
    this.sowingDate,
    this.daysAfterSowing,
    this.currentStage,
    this.currentKc,
    this.timeline = const [],
  });

  final bool available;
  final String? reasonAr;
  final String? crop;
  final String? sowingDate;
  final int? daysAfterSowing;

  /// null حين تجاوز العمر آخر مرحلة (الخادم لا يلفّق مرحلة).
  final PhenologyStage? currentStage;
  final double? currentKc;
  final List<PhenologyStage> timeline;

  factory Phenology.fromJson(Map<String, dynamic> j) {
    final cs = j['current_stage'];
    final tl = j['timeline'];
    return Phenology(
      available: j['available'] == true,
      reasonAr: _str(j['reason_ar']),
      crop: _str(j['crop']),
      sowingDate: _str(j['sowing_date']),
      daysAfterSowing: _int(j['days_after_sowing']),
      currentStage: cs is Map
          ? PhenologyStage.fromJson(cs.cast<String, dynamic>())
          : null,
      currentKc: _num(j['current_stage_kc']),
      timeline: tl is List
          ? tl
                .whereType<Map>()
                .map((e) => PhenologyStage.fromJson(e.cast<String, dynamic>()))
                .toList()
          : const [],
    );
  }
}

class StageSuggestion {
  const StageSuggestion({required this.actionAr, this.stage, this.stageNameAr});
  final String actionAr;
  final String? stage;
  final String? stageNameAr;
}

class StageActions {
  const StageActions({
    required this.available,
    this.reasonAr,
    this.currentStage,
    this.currentStageNameAr,
    this.daysAfterSowing,
    this.suggestions = const [],
    this.noteAr,
  });

  final bool available;
  final String? reasonAr;
  final String? currentStage;
  final String? currentStageNameAr;
  final int? daysAfterSowing;
  final List<StageSuggestion> suggestions;
  final String? noteAr;

  factory StageActions.fromJson(Map<String, dynamic> j) {
    final s = j['suggestions'];
    return StageActions(
      available: j['available'] == true,
      reasonAr: _str(j['reason_ar']),
      currentStage: _str(j['current_stage']),
      currentStageNameAr: _str(j['current_stage_name_ar']),
      daysAfterSowing: _int(j['days_after_sowing']),
      noteAr: _str(j['note_ar']),
      suggestions: s is List
          ? s
                .whereType<Map>()
                .map((e) => e.cast<String, dynamic>())
                .where((e) => _str(e['action_ar']) != null)
                .map(
                  (e) => StageSuggestion(
                    actionAr: _str(e['action_ar'])!,
                    stage: _str(e['stage']),
                    stageNameAr: _str(e['stage_name_ar']),
                  ),
                )
                .toList()
          : const [],
    );
  }
}

/// محصول من فهرس البطاقات. نرسل [cropId] لأنّ الخادم يحلّه مباشرةً
/// (core/season_phenology.resolve_crop_id) فتعمل الفينولوجيا؛ الاسم العربيّ في
/// البطاقة لا يُحلّ دائماً عبر جدول المرادفات.
class CropOption {
  const CropOption({required this.cropId, this.nameAr});
  final String cropId;
  final String? nameAr;

  String get label => nameAr ?? cropId;

  factory CropOption.fromJson(Map<String, dynamic> j) => CropOption(
    cropId: j['crop_id']?.toString() ?? '',
    nameAr: _str(j['name_ar']),
  );
}

/// اسم عرض لمحصول مُخزَّن: الاسم العربيّ من الفهرس إن طابق crop_id، وإلّا كما خُزّن.
String cropLabel(String? stored, List<CropOption> catalog) {
  if (stored == null || stored.isEmpty) return '—';
  for (final c in catalog) {
    if (c.cropId == stored) return c.label;
  }
  return stored;
}
