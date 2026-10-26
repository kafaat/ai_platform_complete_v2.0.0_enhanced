// SAHOOL — features/lab_sampling/data/lab_models.dart
// نماذج عيّنات المختبر كما يردّها الخادم (lab_samples — migrations/v156 +
// api/routers/soil_sampling.py) وقواعد انتقال حالتها — مرآة
// core/engines/soil_lab_workflow.py:SOIL_TEST_TRANSITIONS.

/// حالة العيّنة على الخادم.
enum LabSampleStatus {
  requested('requested', 'مطلوبة'),
  sampled('sampled', 'جُمعت'),
  inLab('in_lab', 'في المختبر'),
  resultReceived('result_received', 'وصلت النتيجة'),
  approved('approved', 'معتمدة'),
  published('published', 'منشورة'),
  rejected('rejected', 'مرفوضة'),
  cancelled('cancelled', 'ملغاة');

  const LabSampleStatus(this.wire, this.labelAr);
  final String wire;
  final String labelAr;

  static LabSampleStatus? parse(Object? raw) {
    for (final s in values) {
      if (s.wire == raw) return s;
    }
    return null;
  }

  Set<LabSampleStatus> get allowedTargets => switch (this) {
    requested => {sampled, cancelled},
    sampled => {inLab, cancelled},
    inLab => {resultReceived, cancelled},
    resultReceived => {approved, rejected},
    approved => {published},
    rejected => {inLab, cancelled},
    published || cancelled => const {},
  };

  /// حالات لا يُنتقل إليها بلا نتيجة مختبر فعليّة (invariant الخادم).
  bool get requiresResult =>
      this == resultReceived || this == approved || this == published;

  bool get isFinal => allowedTargets.isEmpty;
}

/// زرّ انتقال يعرضه التطبيق لعيّنة.
class LabTransitionAction {
  const LabTransitionAction(
    this.target,
    this.labelAr, {
    this.destructive = false,
  });
  final LabSampleStatus target;
  final String labelAr;
  final bool destructive;
}

/// الانتقالات التي يستطيع التطبيق طلبها فعلاً عبر /transition:
/// - «وصلت النتيجة» لا تُطلب انتقالاً: يضعها الخادم حين تُدخَل النتيجة
///   (POST /lab/soil-results أو /lab/water-results).
/// - الاعتماد والنشر لعيّنات التربة فقط: الخادم يشترط نتيجة تربة (has_result)
///   فيرفضهما لعيّنة الماء بـ422.
List<LabTransitionAction> labActionsFor(LabSample s) {
  final st = s.status;
  if (st == null) return const [];
  final out = <LabTransitionAction>[];
  for (final t in st.allowedTargets) {
    switch (t) {
      case LabSampleStatus.sampled:
        out.add(
          const LabTransitionAction(LabSampleStatus.sampled, 'تأكيد الجمع'),
        );
      case LabSampleStatus.inLab:
        out.add(
          LabTransitionAction(
            LabSampleStatus.inLab,
            st == LabSampleStatus.rejected
                ? 'إعادة الإرسال للمختبر'
                : 'أُرسلت للمختبر',
          ),
        );
      case LabSampleStatus.approved:
        if (s.isSoil) {
          out.add(
            const LabTransitionAction(
              LabSampleStatus.approved,
              'اعتماد النتيجة',
            ),
          );
        }
      case LabSampleStatus.published:
        if (s.isSoil) {
          out.add(
            const LabTransitionAction(LabSampleStatus.published, 'نشر النتيجة'),
          );
        }
      case LabSampleStatus.rejected:
        out.add(
          const LabTransitionAction(
            LabSampleStatus.rejected,
            'رفض النتيجة',
            destructive: true,
          ),
        );
      case LabSampleStatus.cancelled:
        out.add(
          const LabTransitionAction(
            LabSampleStatus.cancelled,
            'إلغاء العيّنة',
            destructive: true,
          ),
        );
      case LabSampleStatus.resultReceived:
      case LabSampleStatus.requested:
        break;
    }
  }
  return out;
}

double? _num(Object? v) {
  if (v is num) return v.toDouble();
  if (v is String) return double.tryParse(v);
  return null;
}

String? _str(Object? v) {
  if (v == null) return null;
  final s = v.toString().trim();
  return s.isEmpty ? null : s;
}

class LabSample {
  const LabSample({
    required this.sampleId,
    required this.fieldId,
    required this.kind,
    required this.statusRaw,
    this.latitude,
    this.longitude,
    this.sampledOn,
    this.depthFromCm,
    this.depthToCm,
    this.source,
    this.gpsAccuracyM,
    this.barcode,
    this.createdAt,
    this.updatedAt,
  });

  final String sampleId;
  final String fieldId;

  /// soil / water.
  final String kind;
  final String statusRaw;
  final double? latitude;
  final double? longitude;
  final String? sampledOn;
  final double? depthFromCm;
  final double? depthToCm;
  final String? source;
  final double? gpsAccuracyM;
  final String? barcode;
  final String? createdAt;
  final String? updatedAt;

  bool get isSoil => kind == 'soil';
  LabSampleStatus? get status => LabSampleStatus.parse(statusRaw);

  factory LabSample.fromJson(Map<String, dynamic> j) => LabSample(
    sampleId: j['sample_id']?.toString() ?? '',
    fieldId: j['field_id']?.toString() ?? '',
    kind: j['kind']?.toString() ?? '',
    statusRaw: j['status']?.toString() ?? '',
    latitude: _num(j['latitude']),
    longitude: _num(j['longitude']),
    sampledOn: _str(j['sampled_on']),
    depthFromCm: _num(j['depth_cm_from']),
    depthToCm: _num(j['depth_cm_to']),
    source: _str(j['source']),
    gpsAccuracyM: _num(j['gps_accuracy_m']),
    barcode: _str(j['barcode']),
    createdAt: _str(j['created_at']),
    updatedAt: _str(j['updated_at']),
  );
}

/// سياق المختبر للحقل (core/lab_sampling.lab_decision_context): أعلام فقط —
/// الخادم لا يعيد قيم التحليل ولا وحداتها ولا نطاقاتها المرجعيّة هنا.
class LabContext {
  const LabContext({
    required this.soilReadyForFertilizer,
    required this.waterLabAvailable,
    this.blockersAr = const [],
    this.warningsAr = const [],
    this.recommendationGate,
  });

  final bool soilReadyForFertilizer;
  final bool waterLabAvailable;
  final List<String> blockersAr;
  final List<String> warningsAr;

  /// allow / needs_review.
  final String? recommendationGate;

  static List<String> _list(Object? v) =>
      v is List ? v.map((e) => e.toString()).toList() : const [];

  factory LabContext.fromJson(Map<String, dynamic> j) => LabContext(
    soilReadyForFertilizer: j['soil_lab_ready_for_fertilizer'] == true,
    waterLabAvailable: j['water_lab_available'] == true,
    blockersAr: _list(j['blockers_ar']),
    warningsAr: _list(j['warnings_ar']),
    recommendationGate: _str(j['recommendation_gate']),
  );
}
