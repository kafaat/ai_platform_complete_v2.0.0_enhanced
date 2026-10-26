// SAHOOL — features/advisor/data/advisor_models.dart
// نماذج المستشار كما يُرجعها الخادم حرفيّاً — لا حقل يُخترَع ولا قيمة تُستكمَل.
//
// المصادر (أسماء الحقول مقروءة من المنتِج لا مُخمَّنة):
// - المحادثة: services/ai_agronomist/ai_evidence_runtime.py (build_evidence_response):
//   answer_ar · message · generation_status · mode · evidence_sources[{key,label_ar,
//   available,count}] · evidence_ids · confidence · confidence_calibrated ·
//   confidence_basis · advisory_validation{status,claims[{path,value}]} ·
//   ai_context_pack_readiness{warnings} · pending_approvals · advisory{limitations,
//   requires_human_review} · generation_provider/generation_model (حين يُعرَض فقط).
// - توصيات الحقل: services/sahool-platform/api/routers/fields.py (field_recommendations)
//   + api/recommendations_hub.py (Recommendation.to_dict).
// - توصية المحرّك: core/api_adapter.py (handle_recommendation_request) +
//   routers/recommendations.py (get_recommendation).
// - تصعيد الآفة: routers/pest_escalation.py + core/workflow_engine.py (workflow_trace).

/// يحوّل قيمة JSON إلى `Map<String, dynamic>` أو null (لا يرمي).
Map<String, dynamic>? _map(Object? v) =>
    v is Map ? v.map((k, val) => MapEntry(k.toString(), val)) : null;

List<Object?> _list(Object? v) => v is List ? v : const [];

String? _str(Object? v) {
  if (v is String) {
    final t = v.trim();
    return t.isEmpty ? null : t;
  }
  return null;
}

num? _num(Object? v) => (v is num && v is! bool && v.isFinite) ? v : null;

List<String> _strList(Object? v) =>
    _list(v).map(_str).whereType<String>().toList(growable: false);

// ═══════════════════════════════════════════════════════════════════
// المحادثة
// ═══════════════════════════════════════════════════════════════════

/// مصدر دليل كما يصفه الخادم (بطاقة شفافيّة، لا حمولة خامّ).
class EvidenceSource {
  const EvidenceSource({
    required this.key,
    required this.labelAr,
    required this.available,
    this.count,
  });

  final String key;
  final String labelAr;
  final bool available;
  final int? count;

  static EvidenceSource? fromJson(Object? raw) {
    final m = _map(raw);
    final key = _str(m?['key']);
    if (m == null || key == null) return null;
    return EvidenceSource(
      key: key,
      labelAr: _str(m['label_ar']) ?? key,
      available: m['available'] == true,
      count: _num(m['count'])?.toInt(),
    );
  }

  Map<String, dynamic> toJson() => {
    'key': key,
    'label_ar': labelAr,
    'available': available,
    if (count != null) 'count': count,
  };
}

/// قيمة مُعلَنة من مالك البيانات تحقّق الخادم من تطابقها رقميّاً
/// (shared/ai/structured_advisory.py: claims[{path,value,product_digest}]).
class AdvisoryClaim {
  const AdvisoryClaim({required this.path, required this.value});
  final String path;
  final String value;

  static AdvisoryClaim? fromJson(Object? raw) {
    final m = _map(raw);
    final path = _str(m?['path']);
    final value = m?['value'];
    if (path == null || value == null) return null;
    return AdvisoryClaim(path: path, value: value.toString());
  }
}

/// حالة التوليد كما يصنّفها الخادم (P1-8): يميّز «لم يُحاوَل» عن «حُوصِر بالسياسة»
/// عن «حُوول وفشل» عن «أُخمِد لعدم التحقّق».
abstract final class GenerationStatus {
  static const notAttempted = 'not_attempted';
  static const blockedByPolicy = 'blocked_by_policy';
  static const attemptedFailed = 'attempted_failed';
  static const suppressedUnvalidated = 'suppressed_unvalidated_output';
  static const suppressedUngrounded = 'suppressed_ungrounded';
  static const validatedFacts = 'validated_structured_facts';
}

/// تسمية عربيّة صادقة لحالة التوليد. المجهول يُعرَض كما أرسله الخادم.
String? generationStatusLabel(String? status) {
  switch (status) {
    case null:
      return null;
    case GenerationStatus.notAttempted:
      return 'التوليد غير مُفعَّل — الإجابة من الأدلّة فقط.';
    case GenerationStatus.blockedByPolicy:
      return 'رفضت سياسة الذكاء الاصطناعيّ لمؤسّستك توليد إجابة لهذا السؤال؛ '
          'المعروض ملخّص الأدلّة فقط، لا رأي نموذج.';
    case GenerationStatus.attemptedFailed:
      return 'تعذّر التوليد لدى مزوّد النموذج — المعروض ملخّص الأدلّة فقط.';
    case GenerationStatus.suppressedUnvalidated:
    case GenerationStatus.suppressedUngrounded:
      return 'لم تُعرض إجابة النموذج لأنّ الأدلّة والتحقّق المتاحين لا يكفيان لاعتمادها.';
    case GenerationStatus.validatedFacts:
      return 'قيم مُتحقَّق من تطابقها مع بيانات الحقل المُعلَنة.';
  }
  return 'حالة التوليد: $status';
}

/// قيود الإجابة كما يرمّزها المظروف الاستشاريّ (advisory_contract._limitations).
const Map<String, String> kLimitationLabels = {
  'generation_failed_evidence_only': 'فشل التوليد — أدلّة فقط',
  'generation_blocked_by_policy_evidence_only': 'محجوب بالسياسة — أدلّة فقط',
  'generation_suppressed_evidence_only': 'أُخمِد خرج النموذج — أدلّة فقط',
  'generation_disabled_evidence_only': 'لا نموذج مُفعَّل — أدلّة فقط',
  'proposed_actions_await_human_approval':
      'إجراءات مقترحة بانتظار موافقة بشريّة',
  'confidence_unavailable': 'جودة الدليل غير متاحة',
  'low_confidence': 'جودة دليل منخفضة',
  'tool_calls_truncated': 'اقتُطعت استدعاءات الأدوات',
};

/// ردّ المستشار كما أرسله الخادم.
class AdvisorReply {
  const AdvisorReply({
    required this.answerAr,
    this.generationStatus,
    this.mode,
    this.evidenceSources = const [],
    this.evidenceIds = const [],
    this.confidence,
    this.confidenceCalibrated,
    this.claims = const [],
    this.readinessWarnings = const [],
    this.pendingApprovals = 0,
    this.limitations = const [],
    this.requiresHumanReview,
    this.generationProvider,
    this.generationModel,
    this.fieldId,
  });

  final String answerAr;
  final String? generationStatus;
  final String? mode;
  final List<EvidenceSource> evidenceSources;
  final List<String> evidenceIds;

  /// جودة الدليل كما يُبلِغ عنها مالكه (confidence_basis)، لا احتمال صحّة. null ⇒
  /// لم يُرسلها الخادم.
  final double? confidence;

  /// false ⇒ «غير معايَر» (الخادم يقولها صراحةً). null ⇒ لم يُصرّح.
  final bool? confidenceCalibrated;

  /// تُملأ فقط حين يقبل الخادم التحقّق (advisory_validation.status == verified).
  final List<AdvisoryClaim> claims;
  final List<String> readinessWarnings;
  final int pendingApprovals;
  final List<String> limitations;
  final bool? requiresHumanReview;
  final String? generationProvider;
  final String? generationModel;
  final String? fieldId;

  bool get blockedByPolicy =>
      generationStatus == GenerationStatus.blockedByPolicy;

  /// يقرأ استجابة /v1/chat. يرمي [FormatException] إن غاب نصّ الإجابة: الشكل
  /// الخاطئ خطأ، لا إجابة فارغة.
  factory AdvisorReply.fromJson(Map<String, dynamic> json) {
    final answer = _str(json['answer_ar']) ?? _str(json['message']);
    if (answer == null) {
      throw const FormatException('لم يُرجع المستشار نصّ إجابة (answer_ar).');
    }
    final validation = _map(json['advisory_validation']);
    final verified = validation?['status'] == 'verified';
    final advisory = _map(json['advisory']);
    final readiness = _map(json['ai_context_pack_readiness']);
    return AdvisorReply(
      answerAr: answer,
      generationStatus: _str(json['generation_status']),
      mode: _str(json['mode']),
      evidenceSources: _list(json['evidence_sources'])
          .map(EvidenceSource.fromJson)
          .whereType<EvidenceSource>()
          .toList(growable: false),
      evidenceIds: _strList(json['evidence_ids']),
      confidence: _num(json['confidence'])?.toDouble(),
      confidenceCalibrated: json['confidence_calibrated'] is bool
          ? json['confidence_calibrated'] as bool
          : null,
      claims: verified
          ? _list(validation?['claims'])
                .map(AdvisoryClaim.fromJson)
                .whereType<AdvisoryClaim>()
                .toList(growable: false)
          : const [],
      readinessWarnings: _strList(readiness?['warnings']),
      pendingApprovals: _list(json['pending_approvals']).length,
      limitations: _strList(advisory?['limitations']),
      requiresHumanReview: advisory?['requires_human_review'] is bool
          ? advisory!['requires_human_review'] as bool
          : null,
      generationProvider: _str(json['generation_provider']),
      generationModel: _str(json['generation_model']),
      fieldId: _str(json['field_id']),
    );
  }

  /// الشكل المحفوظ في السجلّ المشفّر: نفس مفاتيح الخادم (يُعاد قراؤه بـfromJson).
  Map<String, dynamic> toJson() => {
    'answer_ar': answerAr,
    if (generationStatus != null) 'generation_status': generationStatus,
    if (mode != null) 'mode': mode,
    'evidence_sources': [for (final s in evidenceSources) s.toJson()],
    'evidence_ids': evidenceIds,
    if (confidence != null) 'confidence': confidence,
    if (confidenceCalibrated != null)
      'confidence_calibrated': confidenceCalibrated,
    if (claims.isNotEmpty)
      'advisory_validation': {
        'status': 'verified',
        'claims': [
          for (final c in claims) {'path': c.path, 'value': c.value},
        ],
      },
    if (readinessWarnings.isNotEmpty)
      'ai_context_pack_readiness': {'warnings': readinessWarnings},
    'pending_approvals': List<int>.filled(pendingApprovals, 0),
    'advisory': {
      'limitations': limitations,
      if (requiresHumanReview != null)
        'requires_human_review': requiresHumanReview,
    },
    if (generationProvider != null) 'generation_provider': generationProvider,
    if (generationModel != null) 'generation_model': generationModel,
    if (fieldId != null) 'field_id': fieldId,
  };
}

enum ChatRole { user, assistant }

/// رسالة في سجلّ المحادثة. الأخطاء لا تُحفَظ (حالة عابرة تُعرَض مع «أعد المحاولة»).
class ChatEntry {
  const ChatEntry({
    required this.role,
    required this.text,
    required this.at,
    this.reply,
    this.fieldId,
  });

  final ChatRole role;
  final String text;
  final DateTime at;
  final AdvisorReply? reply;
  final String? fieldId;

  Map<String, dynamic> toMap() => {
    'role': role.name,
    'text': text,
    'at': at.toUtc().toIso8601String(),
    if (fieldId != null) 'field_id': fieldId,
    if (reply != null) 'reply': reply!.toJson(),
  };

  /// يُعيد null لسجلّ تالف بدل أن يُسقط السجلّ كلّه.
  static ChatEntry? fromMap(Object? raw) {
    final m = _map(raw);
    if (m == null) return null;
    final role = ChatRole.values.where((r) => r.name == m['role']).firstOrNull;
    final text = _str(m['text']);
    final at = DateTime.tryParse(m['at']?.toString() ?? '');
    if (role == null || text == null || at == null) return null;
    AdvisorReply? reply;
    final r = _map(m['reply']);
    if (r != null) {
      try {
        reply = AdvisorReply.fromJson(r);
      } on FormatException {
        reply = null;
      }
    }
    return ChatEntry(
      role: role,
      text: text,
      at: at,
      reply: reply,
      fieldId: _str(m['field_id']),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
// توصيات الحقل (GET /api/v1/fields/{id}/recommendations)
// ═══════════════════════════════════════════════════════════════════

class FieldRecommendationItem {
  const FieldRecommendationItem({
    required this.category,
    required this.priority,
    required this.titleAr,
    required this.detailAr,
    this.source,
    this.safety = false,
  });

  final String category;
  final String priority;
  final String titleAr;
  final String detailAr;
  final String? source;
  final bool safety;

  static FieldRecommendationItem? fromJson(Object? raw) {
    final m = _map(raw);
    final title = _str(m?['title_ar']);
    if (m == null || title == null) return null;
    return FieldRecommendationItem(
      category: _str(m['category']) ?? '',
      priority: _str(m['priority']) ?? '',
      titleAr: title,
      detailAr: _str(m['detail_ar']) ?? '',
      source: _str(m['source']),
      safety: m['safety'] == true,
    );
  }
}

class FieldRecommendationSet {
  const FieldRecommendationSet({
    required this.fieldId,
    required this.items,
    this.crop,
    this.stage,
    this.weatherAvailable,
    this.requiresReview,
    this.validity,
    this.executionMode,
    this.confidenceLevel,
    this.reasonsAr = const [],
  });

  final String fieldId;
  final List<FieldRecommendationItem> items;
  final String? crop;
  final String? stage;
  final bool? weatherAvailable;
  final bool? requiresReview;
  final String? validity;
  final String? executionMode;
  final String? confidenceLevel;
  final List<String> reasonsAr;

  factory FieldRecommendationSet.fromJson(
    Map<String, dynamic> json,
    String fieldId,
  ) {
    final recs = json['recommendations'];
    if (recs is! List) {
      throw const FormatException(
        'استجابة التوصيات بلا قائمة recommendations.',
      );
    }
    final fs = _map(json['field_state']);
    return FieldRecommendationSet(
      fieldId: _str(json['field_id']) ?? fieldId,
      items: recs
          .map(FieldRecommendationItem.fromJson)
          .whereType<FieldRecommendationItem>()
          .toList(growable: false),
      crop: _str(json['crop']),
      stage: _str(json['stage']),
      weatherAvailable: json['weather_available'] is bool
          ? json['weather_available'] as bool
          : null,
      requiresReview: json['requires_review'] is bool
          ? json['requires_review'] as bool
          : null,
      validity: _str(fs?['validity']),
      executionMode: _str(fs?['execution_mode']),
      confidenceLevel: _str(fs?['confidence_level']),
      reasonsAr: _strList(fs?['reasons_ar']),
    );
  }
}

const Map<String, String> kRecommendationCategoryAr = {
  'irrigation': 'الريّ',
  'fertilizer': 'التسميد',
  'disease': 'الأمراض',
  'yield': 'الحصاد',
};

const Map<String, String> kPriorityAr = {
  'high': 'أولويّة عالية',
  'medium': 'أولويّة متوسّطة',
  'low': 'أولويّة منخفضة',
};

// ═══════════════════════════════════════════════════════════════════
// توصية المحرّك (POST /recommendations/for-field · GET /recommendations/{rec_id})
// ═══════════════════════════════════════════════════════════════════

class EngineRecommendation {
  const EngineRecommendation({
    required this.delivered,
    this.recId,
    this.reasonAr,
    this.headline,
    this.qualityGrade,
    this.status,
    this.confidence,
    this.nextActionAr,
    this.predictedYieldTHa,
    this.crossReferenceNoteAr,
    this.fieldId,
    this.farmId,
    this.crop,
    this.issuedAt,
  });

  final bool delivered;
  final String? recId;

  /// سبب الحجب (delivered=false) كما كتبه الخادم.
  final String? reasonAr;
  final String? headline;
  final String? qualityGrade;
  final String? status;

  /// ثقة المحرّك نصّيّة (high/medium/low/…) — لا رقم مُشتقّ.
  final String? confidence;
  final String? nextActionAr;

  /// null ⇒ «غير معايَر بعد» (لا رقم وهميّ).
  final double? predictedYieldTHa;
  final String? crossReferenceNoteAr;
  final String? fieldId;
  final String? farmId;
  final String? crop;
  final DateTime? issuedAt;

  factory EngineRecommendation.fromJson(Map<String, dynamic> json) {
    if (json['delivered'] is! bool) {
      throw const FormatException('استجابة التوصية بلا حقل delivered.');
    }
    final rec = _map(json['recommendation']) ?? const <String, dynamic>{};
    return EngineRecommendation(
      delivered: json['delivered'] as bool,
      recId: _str(json['rec_id']),
      reasonAr: _str(json['reason_ar']),
      headline: _str(rec['headline']),
      qualityGrade: _str(rec['quality_grade']),
      status: _str(rec['status']),
      confidence: _str(rec['confidence']),
      nextActionAr: _str(rec['next_action_ar']),
      predictedYieldTHa: _num(rec['predicted_yield_t_ha'])?.toDouble(),
      crossReferenceNoteAr: _str(json['cross_reference_note_ar']),
      fieldId: _str(json['field_id']),
      farmId: _str(json['farm_id']),
      crop: _str(json['crop']),
      issuedAt: DateTime.tryParse(_str(json['issued_at']) ?? ''),
    );
  }
}

const Map<String, String> kEngineConfidenceAr = {
  'high': 'ثقة عالية',
  'medium': 'ثقة متوسّطة',
  'low': 'ثقة منخفضة',
  'none': 'بلا ثقة كافية',
  'blocked': 'محجوبة',
  'unknown': 'غير معروفة',
};

// ═══════════════════════════════════════════════════════════════════
// تصعيد الآفة (POST /api/v1/pest-escalation/run)
// ═══════════════════════════════════════════════════════════════════

class PestWorkflow {
  const PestWorkflow({
    required this.workflowId,
    required this.status,
    this.currentStep,
    this.completedSteps = const [],
    this.error,
    this.context = const {},
  });

  final String workflowId;
  final String status;
  final String? currentStep;
  final List<String> completedSteps;
  final String? error;
  final Map<String, dynamic> context;

  bool get suspended => status == 'suspended';

  factory PestWorkflow.fromJson(Map<String, dynamic> json) {
    final wf = _map(json['workflow']);
    final id = _str(wf?['workflow_id']);
    final status = _str(wf?['status']);
    if (wf == null || id == null || status == null) {
      throw const FormatException('استجابة التصعيد بلا workflow.');
    }
    return PestWorkflow(
      workflowId: id,
      status: status,
      currentStep: _str(wf['current_step']),
      completedSteps: _strList(wf['completed_steps']),
      error: _str(wf['error']),
      context: _map(json['context']) ?? const {},
    );
  }
}

const Map<String, String> kWorkflowStatusAr = {
  'running': 'قيد التشغيل',
  'suspended': 'مُعلَّق بانتظار موافقة الخبير',
  'completed': 'مكتمل',
  'failed': 'فشل',
  'compensated': 'مُعوَّض (تراجع)',
  'compensation_failed': 'فشل التراجع — يحتاج تدخّلاً',
};

const Map<String, String> kWorkflowStepAr = {
  'detect': 'الرصد',
  'confirm': 'التأكيد',
  'recommend': 'التوصية',
  'await_approval': 'انتظار الموافقة',
  'execute': 'التنفيذ',
  'follow_up': 'المتابعة',
};
