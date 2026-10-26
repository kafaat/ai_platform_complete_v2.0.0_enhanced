// SAHOOL — features/irrigation/data/irrigation_models.dart
// نماذج قراءة لاستجابات الريّ بأسماء حقول الخادم كما هي (irrigation.py،
// irrigation_recommendation.py، water_ledger.py). صدق: الحقل الغائب يبقى null
// ولا يُستبدَل بصفر؛ الشكل الخاطئ يُرمى FormatException (لا قائمة فارغة صامتة).

num? _num(Object? v) => v is num ? v : null;
String? _str(Object? v) => v?.toString();
List<String> _strings(Object? v) =>
    v is List ? v.map((e) => e.toString()).toList() : const <String>[];

/// صمّام كما يعيده GET /api/v1/irrigation/valves.
class Valve {
  const Valve({
    required this.id,
    required this.name,
    required this.status,
    this.fieldId,
    this.valveType,
    this.flowRateLpm,
    this.lastChangedAt,
  });

  factory Valve.fromJson(Map<String, dynamic> j) => Valve(
    id: (j['valve_id'] ?? '').toString(),
    name: (j['name'] ?? '').toString(),
    // الحالة كما خزّنها الخادم: open / closed / أيّ قيمة أخرى ⇒ غير معروف.
    status: _str(j['status']),
    fieldId: _str(j['field_id']),
    valveType: _str(j['valve_type']),
    flowRateLpm: _num(j['flow_rate_lpm']),
    lastChangedAt: DateTime.tryParse((j['last_changed_at'] ?? '').toString()),
  );

  final String id;
  final String name;
  final String? status;
  final String? fieldId;
  final String? valveType;
  final num? flowRateLpm;
  final DateTime? lastChangedAt;

  bool get isOpen => status == 'open';
  bool get isClosed => status == 'closed';

  Valve withStatus(String? s, {DateTime? changedAt}) => Valve(
    id: id,
    name: name,
    status: s,
    fieldId: fieldId,
    valveType: valveType,
    flowRateLpm: flowRateLpm,
    lastChangedAt: changedAt ?? lastChangedAt,
  );
}

/// جدول ريّ كما يعيده GET /api/v1/irrigation/schedules.
class IrrigationSchedule {
  const IrrigationSchedule({
    required this.id,
    required this.name,
    this.fieldId,
    this.valveId,
    this.startTime,
    this.durationMin,
    this.daysOfWeek,
    this.waterTargetMm,
    this.enabled,
    this.lastRunAt,
  });

  factory IrrigationSchedule.fromJson(Map<String, dynamic> j) =>
      IrrigationSchedule(
        id: (j['schedule_id'] ?? '').toString(),
        name: (j['name'] ?? '').toString(),
        fieldId: _str(j['field_id']),
        valveId: _str(j['valve_id']),
        startTime: _str(j['start_time']),
        durationMin: _num(j['duration_min']),
        daysOfWeek: j['days_of_week'] is List
            ? (j['days_of_week'] as List)
                  .whereType<num>()
                  .map((e) => e.toInt())
                  .toList()
            : null,
        waterTargetMm: _num(j['water_target_mm']),
        enabled: j['enabled'] is bool ? j['enabled'] as bool : null,
        lastRunAt: DateTime.tryParse((j['last_run_at'] ?? '').toString()),
      );

  final String id;
  final String name;
  final String? fieldId;
  final String? valveId;
  final String? startTime;
  final num? durationMin;
  final List<int>? daysOfWeek;
  final num? waterTargetMm;
  final bool? enabled;
  final DateTime? lastRunAt;
}

/// قيد دفتر مياه يوميّ (row_to_ledger_entry في water_ledger_compute.py).
class WaterLedgerEntry {
  const WaterLedgerEntry(this.raw);
  factory WaterLedgerEntry.fromJson(Map<String, dynamic> j) =>
      WaterLedgerEntry(Map<String, dynamic>.unmodifiable(j));

  /// الصفّ كما ورد — يُعاد إرسال أعمدته عند الدمج فلا يُمحى ما حسبه الخادم.
  final Map<String, dynamic> raw;

  String get ledgerDate => (raw['ledger_date'] ?? '').toString();
  DateTime? get date => DateTime.tryParse(ledgerDate);
  num? get irrigationMm => _num(raw['irrigation_mm']);
  num? get rainMm => _num(raw['rain_mm']);
  num? get etcMm => _num(raw['etc_mm']);
  num? get et0Mm => _num(raw['et0_mm']);
  num? get depletionMm => _num(raw['depletion_mm']);
  num? get deficitMm => _num(raw['deficit_mm']);
  num? get confidence => _num(raw['confidence']);
  String? get stage => _str(raw['stage']);
  String? get createdBy => _str(raw['created_by']);

  /// قيد كتبه العامل الآليّ (water-balance-auto) لا إنسان.
  bool get isAuto => createdBy == 'water-balance-auto';

  /// أعلام القيد الآليّ من `decision` («auto:a;b» · «auto:daily_balance»)؛
  /// null لقيد يدويّ/قديم (لا يُدَّعى عنه ما لم يُعلنه) — مرآة
  /// ledger_notes_from_decision في water_ledger_auto.py.
  List<String>? get autoNotes {
    final d = raw['decision'];
    if (d is! String || !d.startsWith('auto:')) return null;
    final body = d.substring(5);
    if (body == 'daily_balance') return const [];
    return body.split(';').where((n) => n.isNotEmpty).toList();
  }

  /// العامل لم يجد سجلّ ريّ لهذا اليوم: irrigation_mm=0 يعني «مجهول» لا «صفر».
  bool get irrigationUnobserved =>
      isAuto && (autoNotes?.contains('irrigation_unobserved') ?? false);

  /// رُصد ريّ بلا حجم: الرقم أدنى تقدير.
  bool get irrigationVolumeUntracked =>
      isAuto && (autoNotes?.contains('irrigation_volume_untracked') ?? false);

  /// كمّيّة الريّ المعروضة: null حين تكون «مجهولة» لا مقيسة.
  num? get knownIrrigationMm => irrigationUnobserved ? null : irrigationMm;
}

/// أعمدة القيد التي يقبلها POST water-ledger (WaterLedgerUpsertRequest).
const List<String> kLedgerWritableKeys = [
  'et0_mm',
  'kc',
  'etc_mm',
  'rain_mm',
  'irrigation_mm',
  'soil_moisture_pct',
  'depletion_mm',
  'deficit_mm',
  'stage',
  'decision',
  'confidence',
];

/// حالات استجابة التوصية كما يُعلنها الخادم.
abstract final class RecommendationStatus {
  static const ready = 'recommendation_ready';
  static const insufficient = 'insufficient_data';
  static const inconsistent = 'inconsistent_state';
  static const dependencyUnavailable = 'dependency_unavailable';
}

/// مرشَّح «هل أروي اليوم؟» (POST /fields/{id}/irrigation-recommendation).
class IrrigationRecommendation {
  IrrigationRecommendation._(this.raw);

  factory IrrigationRecommendation.fromJson(Map<String, dynamic> j) {
    if (j['status'] is! String) {
      throw const FormatException('استجابة توصية الريّ بلا حالة (status).');
    }
    return IrrigationRecommendation._(j);
  }

  final Map<String, dynamic> raw;

  String get status => raw['status'] as String;
  bool get isReady =>
      status == RecommendationStatus.ready && raw['recommendation'] is Map;

  Map<String, dynamic> get inputs => raw['inputs'] is Map
      ? Map<String, dynamic>.from(raw['inputs'] as Map)
      : const {};
  Map<String, dynamic>? get recommendation => raw['recommendation'] is Map
      ? Map<String, dynamic>.from(raw['recommendation'] as Map)
      : null;

  List<String> get limitations => _strings(raw['limitations']);
  num? get confidence => _num(raw['confidence']);
  bool get calibrated => raw['calibrated'] == true;
  String? get approvalState => _str(raw['approval_state']);
  String? get generatedOn => _str(raw['generated_on']);

  // ── مدخلات القرار ─────────────────────────────────────────────
  num? get depletionMm => _num(inputs['depletion_mm']);
  num? get depletionUpperBoundMm => _num(inputs['depletion_upper_bound_mm']);
  num? get tawMm => _num(inputs['taw_mm']);
  num? get ledgerAgeHours => _num(inputs['ledger_age_hours']);

  /// true مسجَّل · false غير مسجَّل · null لم يُعلَن (قيد يدويّ/قديم).
  bool? get irrigationKnown => inputs['irrigation_known'] is bool
      ? inputs['irrigation_known'] as bool
      : null;
  String? get appliedWaterStatus => _str(inputs['applied_water_status']);
  String? get crop => _str(inputs['crop']);
  String? get stage => _str(inputs['stage']);

  // ── المرشَّح نفسه (فقط عند recommendation_ready) ───────────────
  /// true اروِ · false لا حاجة · null امتناع (مطر متوقَّع / لا استنزاف).
  bool? get shouldIrrigate {
    final v = recommendation?['should_irrigate'];
    return v is bool ? v : null;
  }

  String? get triggerReason => _str(recommendation?['trigger_reason']);
  num? get netIrrigationMm => _num(recommendation?['net_irrigation_mm']);
  num? get targetRefillMm => _num(recommendation?['target_refill_mm']);
  String? get urgency => _str(recommendation?['urgency']);
  String? get waterStressClass => _str(recommendation?['water_stress_class']);
  String? get timingAr => _str(recommendation?['timing_ar']);
  String? get rationaleAr => _str(recommendation?['rationale_ar']);
  bool get forecastHold => recommendation?['forecast_hold'] == true;
}
