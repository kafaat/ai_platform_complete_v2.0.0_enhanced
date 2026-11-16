// W3-07 — منطق سلسلة تصعيد الآفة النقيّ. الأشكال مطابقة لما يعيده الخادم:
// context.chemical_lineage_audit (shared/governance/chemical_lineage.py: to_dict)،
// step_results.execute (core/pest_escalation_flow.py: step_execute)، وسياق دليل الصورة
// (scout-ingest media_api.py: get_pin_photo_context).
import { describe, it, expect } from 'vitest';
import {
  evaluateApprovalLineage,
  lineageRefsFromContext,
  pestWorkflowIdForPin,
  readExecutionOutcome,
  refsFromPin,
  type ScoutPhotoEvidenceContext,
} from './pestEscalationLineage';

const SHA = 'a'.repeat(64);
const PIN = { pin_id: 'pin_1', field_id: 'fld_1', issue_code: 'tomato.tuta', issue_category: 'pest' };

const fullPhotoContext = (): ScoutPhotoEvidenceContext => ({
  schema: 'sahool.scout-photo-evidence-context/v1',
  source: { kind: 'scouting_pin', field_id: 'fld_1', pin_id: 'pin_1' },
  evidence: {
    evidence_id: 'ev-9', field_id: 'fld_1', pin_id: 'pin_1', sha256: SHA,
    persisted: true, verification_state: 'bytes_verified',
  },
  season: { state: 'linked_accepted', season_id: 'sea-3', link_event_id: 'le-1' },
  human_review: {
    state: 'human_assessment_recorded', review_event_id: 'rev-5', assessment: 'suspected',
    diagnosis_code: 'tomato_leafminer', image_sha256: SHA,
  },
  automatic_pesticide_action_authorized: false,
});

// سياق تدفّق كما يحفظه الخادم بعد أوّل تشغيل (حدّ draft) بمراجع كاملة.
const compliantContext = (): Record<string, unknown> => ({
  field_id: 'fld_1',
  season_id: 'sea-3',
  diagnosis_ref: 'rev-5',
  evidence_ref: `scout_photo_evidence:ev-9@${SHA}`,
  chemical_lineage_audit: {
    mode: 'audit', boundary: 'draft', compliant: true, validated: false, violations: [], details: [],
  },
});

describe('refsFromPin — المراجع من ردود الخادم فقط', () => {
  it('يبني المراجع الأربعة وكود التشخيص المراجَع من دبّوس الخادم وسياق صورته', () => {
    const refs = refsFromPin(PIN, fullPhotoContext());
    expect(refs).toMatchObject({
      field_id: 'fld_1',
      season_id: 'sea-3',
      diagnosis_ref: 'rev-5',
      evidence_ref: `scout_photo_evidence:ev-9@${SHA}`,
      pest_type: 'tomato_leafminer',
    });
    expect(refs.missing).toEqual({});
  });

  it('بلا سياق دليل: لا يخترع دليلاً ولا موسماً ولا تشخيصاً، ويعود لكود الدبّوس', () => {
    const refs = refsFromPin(PIN, null);
    expect(refs.evidence_ref).toBeUndefined();
    expect(refs.season_id).toBeUndefined();
    expect(refs.diagnosis_ref).toBeUndefined();
    expect(refs.pest_type).toBe('tomato.tuta');
    expect(Object.keys(refs.missing).sort()).toEqual(['diagnosis_ref', 'evidence_ref', 'season_id']);
  });

  it('موسم غير مقبول، أو تقييم «مستبعَد»، أو بصمة مختلفة ⇒ لا مرجع', () => {
    const ctx = fullPhotoContext();
    ctx.season = { state: 'linked_not_accepted', season_id: 'sea-3' };
    ctx.human_review = { ...ctx.human_review, assessment: 'ruled_out', diagnosis_code: null };
    const refs = refsFromPin(PIN, ctx);
    expect(refs.season_id).toBeUndefined();
    expect(refs.diagnosis_ref).toBeUndefined();

    const other = fullPhotoContext();
    other.human_review = { ...other.human_review, image_sha256: 'b'.repeat(64) };
    expect(refsFromPin(PIN, other).diagnosis_ref).toBeUndefined();
  });

  it('سياق دبّوس آخر أو دليل غير مُتحقَّق ⇒ لا دليل', () => {
    const foreign = fullPhotoContext();
    foreign.source = { kind: 'scouting_pin', field_id: 'fld_1', pin_id: 'pin_OTHER' };
    expect(refsFromPin(PIN, foreign).evidence_ref).toBeUndefined();

    const unverified = fullPhotoContext();
    unverified.evidence = { ...unverified.evidence, verification_state: 'pending' };
    expect(refsFromPin(PIN, unverified).evidence_ref).toBeUndefined();
  });

  it('معرّف التشغيل مشتقّ من معرّف الدبّوس الذي أعاده الخادم', () => {
    expect(pestWorkflowIdForPin('pin_1', 'r1')).toBe('pest-pin-pin_1-r1');
  });
});

describe('evaluateApprovalLineage — حجب الموافقة بلا سلسلة', () => {
  it('سلسلة متوافقة أعادها الخادم ⇒ الموافقة متاحة', () => {
    const gate = evaluateApprovalLineage(compliantContext());
    expect(gate.allowed).toBe(true);
    expect(gate.reasons).toEqual([]);
    expect(gate.validated).toBe(false);
  });

  it('بلا تدقيق سلسلة من الخادم ⇒ محجوبة', () => {
    const ctx = compliantContext();
    delete ctx.chemical_lineage_audit;
    const gate = evaluateApprovalLineage(ctx);
    expect(gate.allowed).toBe(false);
    expect(gate.reasons.join(' ')).toContain('chemical_lineage_audit');
  });

  it('مخالفات الخادم تُحجب وتُشرَح بأكوادها', () => {
    const gate = evaluateApprovalLineage({
      field_id: 'fld_1',
      chemical_lineage_audit: {
        mode: 'audit', boundary: 'draft', compliant: false, validated: false,
        violations: ['MISSING_SEASON_ID', 'MISSING_DIAGNOSIS_REF', 'MISSING_EVIDENCE_REF'],
      },
    });
    expect(gate.allowed).toBe(false);
    expect(gate.reasons).toHaveLength(3);
    expect(gate.reasons.join(' ')).toContain('MISSING_DIAGNOSIS_REF');
  });

  it('تدقيق «متوافق» لكنّه مُعطَّل (mode=off) أو بلا مراجع في السياق ⇒ محجوبة', () => {
    const off = evaluateApprovalLineage({
      field_id: 'fld_1',
      chemical_lineage_audit: { mode: 'off', boundary: 'draft', compliant: true, violations: [] },
    });
    expect(off.allowed).toBe(false);
    expect(off.reasons.some((r) => r.includes('mode=off'))).toBe(true);
    expect(off.reasons.some((r) => r.includes('التشخيص المراجَع'))).toBe(true);

    const ctx = compliantContext();
    delete ctx.evidence_ref;
    expect(evaluateApprovalLineage(ctx).allowed).toBe(false);
  });

  it('لا ردّ ⇒ محجوبة', () => {
    expect(evaluateApprovalLineage(null).allowed).toBe(false);
  });

  it('المراجع المُعادة مع الموافقة تُقرأ من سياق الخادم فقط', () => {
    expect(lineageRefsFromContext({ ...compliantContext(), pest_type: 'x' })).toEqual({
      field_id: 'fld_1',
      season_id: 'sea-3',
      diagnosis_ref: 'rev-5',
      evidence_ref: `scout_photo_evidence:ev-9@${SHA}`,
    });
  });
});

describe('readExecutionOutcome — نتيجة التنفيذ كما أعادها الخادم', () => {
  it('لا خطوة تنفيذ ⇒ pending لا نجاح', () => {
    expect(readExecutionOutcome({}).state).toBe('pending');
    expect(readExecutionOutcome(undefined).state).toBe('pending');
  });

  it('executed=false من بوّابة السلامة ⇒ لم يُنفَّذ مع السبب والمصادر الغائبة', () => {
    const o = readExecutionOutcome({
      execute: {
        executed: false,
        blocked_by: 'guardrails',
        note_ar: 'لا يُنفَّذ المبيد: أدلّة فحص السلامة غير متاحة',
        guardrails: {
          allowed: false, status: 'evidence_unavailable',
          reason_ar: 'لا يُنفَّذ المبيد: أدلّة فحص السلامة غير متاحة',
          no_server_source: ['action_data.chemical'],
        },
      },
    });
    expect(o.state).toBe('not_executed');
    if (o.state !== 'not_executed') throw new Error('unreachable');
    expect(o.blockedBy).toBe('guardrails');
    expect(o.guardrailsStatus).toBe('evidence_unavailable');
    expect(o.reasons).toHaveLength(2);
    expect(o.reasons[1]).toContain('action_data.chemical');
  });

  it('executed=true بمرجع ⇒ نُفِّذ بالمرجع؛ بلا مرجع ⇒ غير مؤكَّد', () => {
    expect(readExecutionOutcome({ execute: { executed: true, execution_ref: 'task-42' } }))
      .toEqual({ state: 'executed', executionRef: 'task-42' });
    expect(readExecutionOutcome({ execute: { executed: true } }).state).toBe('unconfirmed');
  });

  it('the server placeholder exec-<action_type> (no executor wired) is unconfirmed, not executed', () => {
    const fromRecommend = readExecutionOutcome({
      recommend: { action_type: 'urgent_spray' },
      execute: { executed: true, execution_ref: 'exec-urgent_spray' },
    });
    expect(fromRecommend.state).toBe('unconfirmed');
    expect(fromRecommend.state === 'unconfirmed' && fromRecommend.reasons[0]).toContain('لا منفّذ موصول');
    // The recommend step may be absent from step_results: the context's action_type decides.
    expect(
      readExecutionOutcome({ execute: { executed: true, execution_ref: 'exec-biocontrol' } }, 'biocontrol').state,
    ).toBe('unconfirmed');
    // A real executor's reference for the same action stays executed.
    expect(
      readExecutionOutcome({ execute: { executed: true, execution_ref: 'task-7' } }, 'urgent_spray'),
    ).toEqual({ state: 'executed', executionRef: 'task-7' });
  });

  it('executed ليس true حرفيّاً ⇒ لم يُنفَّذ', () => {
    expect(readExecutionOutcome({ execute: { executed: 'true', execution_ref: 'x' } }).state)
      .toBe('not_executed');
  });
});
