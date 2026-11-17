// ═══════════════════════════════════════════════════════════════
// SAHOOL — سلسلة تصعيد الآفة (W3-07): منطق نقيّ بلا I/O، يُختبَر وحده.
//
// ① البداية من مرجع حقيقيّ: دبّوس استطلاع أعاده الخادم (GET /api/v1/scouting/pins)
//    وسياق دليل صورته (GET /api/v1/scouting-media/fields/{f}/pins/{p}/photo/context،
//    scout-ingest media_api.py). كلّ مرجع يُرسَل إلى POST /api/v1/pest-escalation/run
//    مأخوذ من ردّ خادم، لا من نصّ حرّ ولا من معرّف يصنعه العميل:
//      field_id      ← pin.field_id
//      season_id     ← season.season_id حين state = linked_accepted فقط (v262)
//      diagnosis_ref ← human_review.review_event_id حين يسجّل مختصّ تقييماً «مشتبهاً»
//                      بكود تشخيص على نفس بصمة الصورة (v268)
//      evidence_ref  ← "scout_photo_evidence:<evidence_id>@<sha256>" من إيصال الدليل
//                      (شكل <ref>@<64hex> الذي يفحصه shared/governance/chemical_lineage.py)
//      pest_type     ← كود التشخيص المراجَع، وإلّا issue_code الدبّوس
//
// ② حجب الموافقة بلا سلسلة: زرّ الموافقة لا يُفعَّل إلّا إذا أعاد الخادم في
//    context.chemical_lineage_audit تدقيقاً متوافقاً (compliant، بلا مخالفات، وضعه ليس
//    off) وأعاد المراجع الأربعة نفسها في سياق التدفّق. الخادم هو الحَكَم؛ الواجهة لا
//    تُعلن سلسلة لم يُعِدها.
//
// ③ نتيجة التنفيذ كما أعادها الخادم (step_results.execute): executed=true مع مرجعه، أو
//    executed=false مع سببه. لا نجاح متفائل: executed=true بلا مرجع لا يُعدّ تنفيذاً مؤكّداً.
// ═══════════════════════════════════════════════════════════════

/** جزء سياق دليل الصورة الذي تقرؤه الشاشة (sahool.scout-photo-evidence-context/v1). */
export interface ScoutPhotoEvidenceContext {
  schema?: string;
  source?: { kind?: string; field_id?: string; pin_id?: string };
  evidence?: {
    evidence_id?: string;
    field_id?: string;
    pin_id?: string;
    sha256?: string;
    persisted?: boolean;
    verification_state?: string;
  };
  season?: { state?: string; season_id?: string | null; link_event_id?: string };
  human_review?: {
    state?: string;
    review_event_id?: string;
    assessment?: string | null;
    diagnosis_code?: string | null;
    image_sha256?: string;
  };
  automatic_pesticide_action_authorized?: boolean;
}

/** ما تحتاجه الشاشة من دبّوس الخادم (ScoutingPinRecord). */
export interface EscalationPinSource {
  pin_id: string;
  field_id: string;
  issue_code: string | null;
  issue_category?: string | null;
}

export type LineageRefKey = 'field_id' | 'season_id' | 'diagnosis_ref' | 'evidence_ref';
export const LINEAGE_REF_KEYS: readonly LineageRefKey[] = [
  'field_id', 'season_id', 'diagnosis_ref', 'evidence_ref',
];

export const LINEAGE_REF_AR: Record<LineageRefKey, string> = {
  field_id: 'الحقل',
  season_id: 'الموسم المقبول',
  diagnosis_ref: 'التشخيص المراجَع',
  evidence_ref: 'دليل الصورة ببصمته',
};

export interface EscalationRefs {
  field_id: string;
  season_id?: string;
  diagnosis_ref?: string;
  evidence_ref?: string;
  pest_type?: string;
  /** سبب غياب كلّ مرجع ناقص قبل الإرسال (عرض فقط؛ الحكم للخادم بعد الإرسال). */
  missing: Partial<Record<LineageRefKey, string>>;
}

const HEX64 = /^[0-9a-f]{64}$/;
const nonEmpty = (v: unknown): v is string => typeof v === 'string' && v.trim().length > 0;

/** يبني مراجع التصعيد من دبّوس الخادم وسياق دليل صورته. لا يخترع مرجعاً غائباً. */
export function refsFromPin(
  pin: EscalationPinSource,
  ctx: ScoutPhotoEvidenceContext | null | undefined,
): EscalationRefs {
  const missing: EscalationRefs['missing'] = {};
  const out: EscalationRefs = { field_id: pin.field_id, missing };

  const sameSource = !!ctx
    && ctx.source?.pin_id === pin.pin_id
    && ctx.source?.field_id === pin.field_id;
  if (!ctx) {
    const why = 'لم يُعِد الخادم سياق دليل لصورة هذا الدبّوس';
    missing.evidence_ref = why;
    missing.season_id = why;
    missing.diagnosis_ref = why;
  } else if (!sameSource) {
    const why = 'سياق الدليل لا يطابق هذا الدبّوس';
    missing.evidence_ref = why;
    missing.season_id = why;
    missing.diagnosis_ref = why;
  }

  // الدليل: إيصال مُتحقَّق البايتات ومحفوظ، وبصمته sha256 سداسيّة 64.
  const ev = sameSource ? ctx?.evidence : undefined;
  const sha = typeof ev?.sha256 === 'string' ? ev.sha256.trim().toLowerCase() : '';
  if (sameSource) {
    if (ev && ev.persisted === true && ev.verification_state === 'bytes_verified'
      && ev.pin_id === pin.pin_id && nonEmpty(ev.evidence_id) && HEX64.test(sha)) {
      out.evidence_ref = `scout_photo_evidence:${ev.evidence_id}@${sha}`;
    } else {
      missing.evidence_ref = 'لا إيصال دليل صورة مُتحقَّق البايتات لهذا الدبّوس';
    }

    // الموسم: رابط صريح مقبول بشريّاً فقط (linked_accepted).
    const season = ctx?.season;
    if (season?.state === 'linked_accepted' && nonEmpty(season.season_id)) {
      out.season_id = season.season_id;
    } else {
      missing.season_id = season?.state === 'linked_not_accepted'
        ? 'الموسم المرتبط بالصورة غير مقبول بشريّاً'
        : 'لا رابط صريح بموسم مقبول لصورة الدبّوس';
    }

    // التشخيص: تقييم مختصّ «مشتبه» بكود تشخيص على نفس بصمة الصورة.
    const hr = ctx?.human_review;
    if (hr?.state === 'human_assessment_recorded' && hr.assessment === 'suspected'
      && nonEmpty(hr.diagnosis_code) && nonEmpty(hr.review_event_id)
      && !!out.evidence_ref && (hr.image_sha256 ?? '').trim().toLowerCase() === sha) {
      out.diagnosis_ref = hr.review_event_id;
      out.pest_type = hr.diagnosis_code;
    } else {
      missing.diagnosis_ref = hr?.state === 'human_assessment_recorded' && hr.assessment !== 'suspected'
        ? 'تقييم المختصّ لا يُثبت إصابة (ليس «مشتبهاً»)'
        : 'لا تقييم مختصّ مسجَّل بكود تشخيص لهذه الصورة';
    }
  }

  if (!out.pest_type) {
    const code = pin.issue_code ?? pin.issue_category ?? undefined;
    if (nonEmpty(code)) out.pest_type = code;
  }
  return out;
}

/** معرّف تشغيل التدفّق: مشتقّ من معرّف الدبّوس الذي أعاده الخادم + لاحقة تشغيل. */
export function pestWorkflowIdForPin(pinId: string, runSuffix: string): string {
  return `pest-pin-${pinId}-${runSuffix}`;
}

/** شكل تدقيق السلسلة كما يعيده الخادم في context.chemical_lineage_audit. */
export interface ServerLineageAudit {
  mode?: string;
  boundary?: string;
  compliant?: unknown;
  validated?: unknown;
  violations?: unknown;
}

const VIOLATION_AR: Record<string, string> = {
  MISSING_FIELD_ID: 'لا حقل مرتبط',
  MISSING_SEASON_ID: 'لا موسم مرتبط',
  MISSING_TENANT_ID: 'لا مستأجِر موثوق',
  MISSING_DIAGNOSIS_REF: 'لا مرجع تشخيص',
  MISSING_EVIDENCE_REF: 'لا مرجع دليل',
  EVIDENCE_DIGEST_MISSING: 'مرجع الدليل بلا بصمة sha256',
  UNKNOWN_BOUNDARY: 'حدّ تدقيق غير معروف',
  DIAGNOSIS_NOT_FOUND: 'التشخيص غير موجود لدى مالكه',
  DIAGNOSIS_EXPIRED: 'التشخيص منتهي الصلاحيّة',
  DIAGNOSIS_SUPERSEDED: 'التشخيص مُستبدَل بآخر',
  REVIEW_STATE_NOT_ALLOWED: 'حالة مراجعة التشخيص غير مقبولة',
  DIAGNOSIS_INSUFFICIENT_EVIDENCE: 'التشخيص بأدلّة غير كافية',
  EVIDENCE_INSUFFICIENT: 'مستوى الأدلّة دون الحدّ',
  OWNER_FACTS_INCOMPLETE: 'حقائق مالك التشخيص ناقصة',
  TENANT_MISMATCH: 'المستأجِر لا يطابق التشخيص',
  FIELD_MISMATCH: 'الحقل لا يطابق التشخيص',
  SEASON_MISMATCH: 'الموسم لا يطابق التشخيص',
  MISSING_HUMAN_APPROVAL: 'لا موافقة بشريّة',
  VALIDATION_UNAVAILABLE: 'تعذّر التحقّق من التشخيص لدى مالكه',
};

export function violationAr(code: string): string {
  return VIOLATION_AR[code] ? `${VIOLATION_AR[code]} (${code})` : code;
}

export interface ApprovalLineageGate {
  /** هل تُتاح الموافقة؟ true فقط حين يُثبت ردّ الخادم السلسلة. */
  allowed: boolean;
  /** أسباب الحجب بالعربيّة (فارغة حين allowed). */
  reasons: string[];
  /** هل تحقّق الخادم من التشخيص لدى مالكه؟ (معلوماتيّ: لا مُحقِّق موصول اليوم). */
  validated: boolean;
}

/** يحكم على إتاحة الموافقة من سياق التدفّق الذي أعاده الخادم فقط. */
export function evaluateApprovalLineage(
  context: Record<string, unknown> | null | undefined,
): ApprovalLineageGate {
  const ctx = context ?? {};
  const reasons: string[] = [];
  const raw = ctx.chemical_lineage_audit;
  const audit = raw && typeof raw === 'object' ? (raw as ServerLineageAudit) : null;
  const violations = Array.isArray(audit?.violations)
    ? (audit?.violations as unknown[]).filter(nonEmpty)
    : [];

  if (!audit) {
    reasons.push('لم يُعِد الخادم تدقيق سلسلة المبيد (chemical_lineage_audit)');
  } else {
    if (audit.mode === 'off') {
      reasons.push('تدقيق سلسلة المبيد مُعطَّل على الخادم (mode=off) فلا إثبات للسلسلة');
    }
    for (const code of violations) reasons.push(violationAr(code));
    if (audit.compliant !== true && violations.length === 0) {
      reasons.push('تدقيق الخادم لم يُعلن السلسلة متوافقة');
    }
  }
  const covered = new Set(violations);
  const coverCode: Record<LineageRefKey, string> = {
    field_id: 'MISSING_FIELD_ID',
    season_id: 'MISSING_SEASON_ID',
    diagnosis_ref: 'MISSING_DIAGNOSIS_REF',
    evidence_ref: 'MISSING_EVIDENCE_REF',
  };
  for (const key of LINEAGE_REF_KEYS) {
    if (!nonEmpty(ctx[key]) && !covered.has(coverCode[key])) {
      reasons.push(`لم يُعِد الخادم مرجع ${LINEAGE_REF_AR[key]} في سياق التدفّق`);
    }
  }
  return { allowed: reasons.length === 0, reasons, validated: audit?.validated === true };
}

/** المراجع التي تُعاد مع الموافقة/الرفض: من سياق الخادم لا من حالة الواجهة. */
export function lineageRefsFromContext(
  context: Record<string, unknown> | null | undefined,
): Partial<Record<LineageRefKey, string>> {
  const ctx = context ?? {};
  const out: Partial<Record<LineageRefKey, string>> = {};
  for (const key of LINEAGE_REF_KEYS) {
    const v = ctx[key];
    if (nonEmpty(v)) out[key] = v;
  }
  return out;
}

export type ExecutionOutcome =
  | { state: 'pending' }
  | { state: 'executed'; executionRef: string }
  | { state: 'unconfirmed'; reasons: string[] }
  | { state: 'not_executed'; reasons: string[]; blockedBy?: string; guardrailsStatus?: string };

/** نتيجة خطوة التنفيذ كما أعادها الخادم. غياب الخطوة ⇒ pending، لا نجاح. */
export function readExecutionOutcome(
  stepResults: Record<string, Record<string, unknown>> | null | undefined,
  contextActionType?: unknown,
): ExecutionOutcome {
  const exec = stepResults?.execute;
  if (!exec || typeof exec !== 'object') return { state: 'pending' };
  const gr = (exec.guardrails && typeof exec.guardrails === 'object'
    ? exec.guardrails
    : null) as Record<string, unknown> | null;
  if (exec.executed === true) {
    if (!nonEmpty(exec.execution_ref)) {
      return {
        state: 'unconfirmed',
        reasons: ['أعلن الخادم التنفيذ بلا مرجع تنفيذ — لا يُعدّ تنفيذاً مؤكّداً'],
      };
    }
    // Older servers, without an injected execute_fn, answered executed=true with the
    // placeholder "exec-<action_type>". No executor ran. Current servers answer
    // executed=false with reason "executor_not_configured" (PEST-EXECUTE-DEFAULT-ACK-01);
    // this check stays for responses from a server that predates that fix.
    const action = stepResults?.recommend?.action_type ?? contextActionType;
    if (nonEmpty(action) && exec.execution_ref === `exec-${action}`) {
      return {
        state: 'unconfirmed',
        reasons: [
          'مرجع التنفيذ افتراضيّ من الخادم (لا منفّذ موصول) — لم يُنفَّذ شيء فعلياً',
        ],
      };
    }
    return { state: 'executed', executionRef: exec.execution_ref };
  }
  const reasons: string[] = [];
  if (nonEmpty(exec.note_ar)) reasons.push(exec.note_ar);
  // An allowing verdict's text ("سمح ...") is not a reason for not executing: when the gate
  // allowed but no executor ran, the note alone explains it.
  if (gr && gr.allowed !== true && nonEmpty(gr.reason_ar) && gr.reason_ar !== exec.note_ar) {
    reasons.push(gr.reason_ar);
  }
  const noSource = Array.isArray(gr?.no_server_source)
    ? (gr?.no_server_source as unknown[]).filter(nonEmpty)
    : [];
  if (noSource.length > 0) {
    reasons.push(`أدلّة بلا مصدر على الخادم اليوم: ${noSource.join('، ')}`);
  }
  if (reasons.length === 0) reasons.push('لم يُعِد الخادم سبباً');
  return {
    state: 'not_executed',
    reasons,
    blockedBy: nonEmpty(exec.blocked_by) ? exec.blocked_by : undefined,
    guardrailsStatus: gr && nonEmpty(gr.status) ? gr.status : undefined,
  };
}
