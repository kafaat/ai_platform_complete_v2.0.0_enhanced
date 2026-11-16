// SAHOOL — features/advisor/data/pest_escalation_lineage.dart
// سلسلة تصعيد الآفة (W3-07): منطق نقيّ بلا I/O. مرآة frontend/src/lib/pestEscalationLineage.ts.
//
// ① البداية من مرجع حقيقيّ: دبّوس استطلاع أعاده الخادم (GET /api/v1/scouting/pins) وسياق
//    دليل صورته (GET /api/v1/scouting-media/fields/{f}/pins/{p}/photo/context، scout-ingest
//    media_api.py). كلّ مرجع يُرسَل إلى POST /api/v1/pest-escalation/run مأخوذ من ردّ خادم:
//      field_id      ← pin.fieldId
//      season_id     ← season.season_id حين state = linked_accepted فقط (v262)
//      diagnosis_ref ← human_review.review_event_id لتقييم مختصّ «مشتبه» بكود تشخيص على
//                      نفس بصمة الصورة (v268)
//      evidence_ref  ← "scout_photo_evidence:<evidence_id>@<sha256>" من إيصال الدليل
//      pest_type     ← كود التشخيص المراجَع، وإلّا issueCode الدبّوس
// ② حجب الموافقة بلا سلسلة: لا موافقة ما لم يُعِد الخادم context.chemical_lineage_audit
//    متوافقاً (compliant، بلا مخالفات، وضعه ليس off) والمراجع الأربعة في سياق التدفّق.
// ③ نتيجة التنفيذ كما أعادها الخادم (step_results.execute): مرجع تنفيذ أو executed=false
//    مع السبب. executed=true بلا مرجع لا يُعدّ تنفيذاً مؤكّداً.
import 'package:sahool_app/features/scouting/data/scouting_models.dart';

const List<String> kLineageRefKeys = [
  'field_id',
  'season_id',
  'diagnosis_ref',
  'evidence_ref',
];

const Map<String, String> kLineageRefAr = {
  'field_id': 'الحقل',
  'season_id': 'الموسم المقبول',
  'diagnosis_ref': 'التشخيص المراجَع',
  'evidence_ref': 'دليل الصورة ببصمته',
};

const Map<String, String> _kMissingCode = {
  'field_id': 'MISSING_FIELD_ID',
  'season_id': 'MISSING_SEASON_ID',
  'diagnosis_ref': 'MISSING_DIAGNOSIS_REF',
  'evidence_ref': 'MISSING_EVIDENCE_REF',
};

const Map<String, String> _kViolationAr = {
  'MISSING_FIELD_ID': 'لا حقل مرتبط',
  'MISSING_SEASON_ID': 'لا موسم مرتبط',
  'MISSING_TENANT_ID': 'لا مستأجِر موثوق',
  'MISSING_DIAGNOSIS_REF': 'لا مرجع تشخيص',
  'MISSING_EVIDENCE_REF': 'لا مرجع دليل',
  'EVIDENCE_DIGEST_MISSING': 'مرجع الدليل بلا بصمة sha256',
  'UNKNOWN_BOUNDARY': 'حدّ تدقيق غير معروف',
  'DIAGNOSIS_NOT_FOUND': 'التشخيص غير موجود لدى مالكه',
  'DIAGNOSIS_EXPIRED': 'التشخيص منتهي الصلاحيّة',
  'DIAGNOSIS_SUPERSEDED': 'التشخيص مُستبدَل بآخر',
  'REVIEW_STATE_NOT_ALLOWED': 'حالة مراجعة التشخيص غير مقبولة',
  'DIAGNOSIS_INSUFFICIENT_EVIDENCE': 'التشخيص بأدلّة غير كافية',
  'EVIDENCE_INSUFFICIENT': 'مستوى الأدلّة دون الحدّ',
  'OWNER_FACTS_INCOMPLETE': 'حقائق مالك التشخيص ناقصة',
  'TENANT_MISMATCH': 'المستأجِر لا يطابق التشخيص',
  'FIELD_MISMATCH': 'الحقل لا يطابق التشخيص',
  'SEASON_MISMATCH': 'الموسم لا يطابق التشخيص',
  'MISSING_HUMAN_APPROVAL': 'لا موافقة بشريّة',
  'VALIDATION_UNAVAILABLE': 'تعذّر التحقّق من التشخيص لدى مالكه',
};

String violationAr(String code) {
  final ar = _kViolationAr[code];
  return ar == null ? code : '$ar ($code)';
}

final RegExp _hex64 = RegExp(r'^[0-9a-f]{64}$');

bool _nonEmpty(Object? v) => v is String && v.trim().isNotEmpty;

Map<String, dynamic>? _asMap(Object? v) =>
    v is Map ? v.map((k, val) => MapEntry(k.toString(), val)) : null;

/// مراجع التصعيد المبنيّة من ردود الخادم، وسبب غياب كلّ ناقص (عرض فقط).
class EscalationRefs {
  const EscalationRefs({
    required this.pinId,
    required this.fieldId,
    this.seasonId,
    this.diagnosisRef,
    this.evidenceRef,
    this.pestType,
    this.missing = const {},
  });

  final String pinId;
  final String fieldId;
  final String? seasonId;
  final String? diagnosisRef;
  final String? evidenceRef;
  final String? pestType;
  final Map<String, String> missing;

  String? valueOf(String key) => switch (key) {
    'field_id' => fieldId,
    'season_id' => seasonId,
    'diagnosis_ref' => diagnosisRef,
    'evidence_ref' => evidenceRef,
    _ => null,
  };
}

/// يبني المراجع من دبّوس الخادم وسياق دليل صورته. لا يخترع مرجعاً غائباً.
EscalationRefs refsFromPin(ScoutingPin pin, Map<String, dynamic>? context) {
  final missing = <String, String>{};
  final source = _asMap(context?['source']);
  final sameSource =
      context != null &&
      source?['pin_id'] == pin.pinId &&
      source?['field_id'] == pin.fieldId;
  if (!sameSource) {
    final why = context == null
        ? 'لم يُعِد الخادم سياق دليل لصورة هذا الدبّوس'
        : 'سياق الدليل لا يطابق هذا الدبّوس';
    missing['evidence_ref'] = why;
    missing['season_id'] = why;
    missing['diagnosis_ref'] = why;
  }

  String? evidenceRef;
  String? seasonId;
  String? diagnosisRef;
  String? pestType;
  if (sameSource) {
    final ev = _asMap(context['evidence']);
    final rawSha = ev?['sha256'];
    final sha = rawSha is String ? rawSha.trim().toLowerCase() : '';
    if (ev != null &&
        ev['persisted'] == true &&
        ev['verification_state'] == 'bytes_verified' &&
        ev['pin_id'] == pin.pinId &&
        _nonEmpty(ev['evidence_id']) &&
        _hex64.hasMatch(sha)) {
      evidenceRef = 'scout_photo_evidence:${ev['evidence_id']}@$sha';
    } else {
      missing['evidence_ref'] =
          'لا إيصال دليل صورة مُتحقَّق البايتات لهذا الدبّوس';
    }

    final season = _asMap(context['season']);
    if (season?['state'] == 'linked_accepted' &&
        _nonEmpty(season?['season_id'])) {
      seasonId = season!['season_id'] as String;
    } else {
      missing['season_id'] = season?['state'] == 'linked_not_accepted'
          ? 'الموسم المرتبط بالصورة غير مقبول بشريّاً'
          : 'لا رابط صريح بموسم مقبول لصورة الدبّوس';
    }

    final hr = _asMap(context['human_review']);
    final reviewSha = hr?['image_sha256'];
    if (hr?['state'] == 'human_assessment_recorded' &&
        hr?['assessment'] == 'suspected' &&
        _nonEmpty(hr?['diagnosis_code']) &&
        _nonEmpty(hr?['review_event_id']) &&
        evidenceRef != null &&
        reviewSha is String &&
        reviewSha.trim().toLowerCase() == sha) {
      diagnosisRef = hr!['review_event_id'] as String;
      pestType = hr['diagnosis_code'] as String;
    } else {
      missing['diagnosis_ref'] =
          hr?['state'] == 'human_assessment_recorded' &&
              hr?['assessment'] != 'suspected'
          ? 'تقييم المختصّ لا يُثبت إصابة (ليس «مشتبهاً»)'
          : 'لا تقييم مختصّ مسجَّل بكود تشخيص لهذه الصورة';
    }
  }

  if (pestType == null) {
    final code = pin.issueCode ?? pin.categoryWire;
    if (code.trim().isNotEmpty) pestType = code;
  }
  return EscalationRefs(
    pinId: pin.pinId,
    fieldId: pin.fieldId,
    seasonId: seasonId,
    diagnosisRef: diagnosisRef,
    evidenceRef: evidenceRef,
    pestType: pestType,
    missing: missing,
  );
}

/// معرّف تشغيل التدفّق: مشتقّ من معرّف الدبّوس الذي أعاده الخادم + لاحقة تشغيل.
String pestWorkflowIdForPin(String pinId, String runSuffix) =>
    'pest-pin-$pinId-$runSuffix';

class ApprovalLineageGate {
  const ApprovalLineageGate({
    required this.allowed,
    required this.reasons,
    required this.validated,
  });
  final bool allowed;
  final List<String> reasons;
  final bool validated;
}

/// يحكم على إتاحة الموافقة من سياق التدفّق الذي أعاده الخادم فقط.
ApprovalLineageGate evaluateApprovalLineage(Map<String, dynamic>? context) {
  final ctx = context ?? const <String, dynamic>{};
  final reasons = <String>[];
  final audit = _asMap(ctx['chemical_lineage_audit']);
  final rawViolations = audit?['violations'];
  final violations = rawViolations is List
      ? rawViolations
            .whereType<String>()
            .where((v) => v.trim().isNotEmpty)
            .toList()
      : <String>[];
  if (audit == null) {
    reasons.add('لم يُعِد الخادم تدقيق سلسلة المبيد (chemical_lineage_audit)');
  } else {
    if (audit['mode'] == 'off') {
      reasons.add(
        'تدقيق سلسلة المبيد مُعطَّل على الخادم (mode=off) فلا إثبات للسلسلة',
      );
    }
    reasons.addAll(violations.map(violationAr));
    if (audit['compliant'] != true && violations.isEmpty) {
      reasons.add('تدقيق الخادم لم يُعلن السلسلة متوافقة');
    }
  }
  for (final key in kLineageRefKeys) {
    if (!_nonEmpty(ctx[key]) && !violations.contains(_kMissingCode[key])) {
      reasons.add('لم يُعِد الخادم مرجع ${kLineageRefAr[key]} في سياق التدفّق');
    }
  }
  return ApprovalLineageGate(
    allowed: reasons.isEmpty,
    reasons: reasons,
    validated: audit?['validated'] == true,
  );
}

/// المراجع التي تُعاد مع الموافقة/الرفض: من سياق الخادم لا من حالة الواجهة.
Map<String, String> lineageRefsFromContext(Map<String, dynamic>? context) {
  final ctx = context ?? const <String, dynamic>{};
  return {
    for (final key in kLineageRefKeys)
      if (_nonEmpty(ctx[key])) key: ctx[key] as String,
  };
}

enum ExecutionState { pending, executed, unconfirmed, notExecuted }

class ExecutionOutcome {
  const ExecutionOutcome(
    this.state, {
    this.executionRef,
    this.reasons = const [],
    this.blockedBy,
    this.guardrailsStatus,
  });
  final ExecutionState state;
  final String? executionRef;
  final List<String> reasons;
  final String? blockedBy;
  final String? guardrailsStatus;
}

/// نتيجة خطوة التنفيذ كما أعادها الخادم. غياب الخطوة ⇒ pending، لا نجاح.
ExecutionOutcome readExecutionOutcome(Map<String, dynamic>? stepResults) {
  final exec = _asMap(stepResults?['execute']);
  if (exec == null) return const ExecutionOutcome(ExecutionState.pending);
  final gr = _asMap(exec['guardrails']);
  if (exec['executed'] == true) {
    final ref = exec['execution_ref'];
    if (_nonEmpty(ref)) {
      return ExecutionOutcome(
        ExecutionState.executed,
        executionRef: ref as String,
      );
    }
    return const ExecutionOutcome(
      ExecutionState.unconfirmed,
      reasons: [
        'أعلن الخادم التنفيذ بلا مرجع تنفيذ — لا يُعدّ تنفيذاً مؤكّداً',
      ],
    );
  }
  final reasons = <String>[];
  final note = exec['note_ar'];
  if (_nonEmpty(note)) reasons.add(note as String);
  final grReason = gr?['reason_ar'];
  if (_nonEmpty(grReason) && grReason != note) reasons.add(grReason as String);
  final noSource = gr?['no_server_source'];
  final missing = noSource is List
      ? noSource.whereType<String>().where((s) => s.trim().isNotEmpty).toList()
      : <String>[];
  if (missing.isNotEmpty) {
    reasons.add('أدلّة بلا مصدر على الخادم اليوم: ${missing.join('، ')}');
  }
  if (reasons.isEmpty) reasons.add('لم يُعِد الخادم سبباً');
  final blockedBy = exec['blocked_by'];
  final status = gr?['status'];
  return ExecutionOutcome(
    ExecutionState.notExecuted,
    reasons: reasons,
    blockedBy: _nonEmpty(blockedBy) ? blockedBy as String : null,
    guardrailsStatus: _nonEmpty(status) ? status as String : null,
  );
}
