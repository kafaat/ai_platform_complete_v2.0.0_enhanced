// W3-07 — صفحة تصعيد الآفة: البداية من دبّوس الخادم ومراجع دليله، حجب الموافقة بلا سلسلة
// أثبتها الخادم، وعرض نتيجة التنفيذ كما أعادها (executed=false لا يُعرَض نجاحاً).
// الردود المحاكاة مطابقة لأشكال الخادم: POST /api/v1/pest-escalation/run (routers/
// pest_escalation.py)، GET /api/v1/scouting/pins، وسياق دليل الصورة (scout-ingest).
// الضابط السالب: لو أُزيل فحص السلسلة من الصفحة لصار زرّ الموافقة مُفعَّلاً في اختبار
// «بلا سلسلة» فيحمرّ.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const SHA = 'c'.repeat(64);
const PIN = {
  pin_id: 'pin_42', field_id: 'fld_1', lat: 15.3, lng: 44.2, issue_category: 'pest',
  severity: 'high', status: 'new', persistence: 'seasonal', crop: 'tomato',
  issue_code: 'tomato.tuta', note_ar: null, photo_uri: null, color: null, created_by: 'u1',
  created_at: '2026-11-10T08:00:00+00:00',
};
const PHOTO_CONTEXT = {
  schema: 'sahool.scout-photo-evidence-context/v1',
  source: { kind: 'scouting_pin', field_id: 'fld_1', pin_id: 'pin_42' },
  evidence: {
    evidence_id: 'ev-1', field_id: 'fld_1', pin_id: 'pin_42', sha256: SHA,
    persisted: true, verification_state: 'bytes_verified', review_state: 'unreviewed',
  },
  season: { state: 'linked_accepted', season_id: 'sea-7', link_event_id: 'le-1' },
  human_review: {
    state: 'human_assessment_recorded', review_event_id: 'rev-3', assessment: 'suspected',
    diagnosis_code: 'tomato_leafminer', image_sha256: SHA,
  },
  decision: { state: 'not_authorized', decision_id: null },
  automatic_pesticide_action_authorized: false,
};

const SUSPENDED_WORKFLOW = {
  workflow_id: 'pest-pin-pin_42-x', status: 'suspended',
  completed_steps: ['detect', 'confirm', 'recommend'], compensated_steps: [],
  current_step: 'await_approval', steps_done: 3, error: null,
};
const withLineage = () => ({
  workflow: SUSPENDED_WORKFLOW,
  context: {
    field_id: 'fld_1', season_id: 'sea-7', diagnosis_ref: 'rev-3',
    evidence_ref: `scout_photo_evidence:ev-1@${SHA}`, pest_type: 'tomato_leafminer',
    severity: 0.85, alert_level: 'critical', confirmed: true,
    recommendation_ar: 'مكافحة عاجلة — رشّ موجّه + عزل البؤرة', action_type: 'urgent_spray',
    approval_requested: true, approval_status: 'pending',
    chemical_lineage_audit: {
      mode: 'audit', boundary: 'draft', compliant: true, validated: false, violations: [], details: [],
    },
  },
  step_results: {},
});
const withoutLineage = () => ({
  workflow: SUSPENDED_WORKFLOW,
  context: {
    field_id: 'fld_1', pest_type: 'tomato.tuta', severity: 0.85, confirmed: true,
    recommendation_ar: 'مكافحة عاجلة', action_type: 'urgent_spray', approval_status: 'pending',
    chemical_lineage_audit: {
      mode: 'audit', boundary: 'draft', compliant: false, validated: false,
      violations: ['MISSING_SEASON_ID', 'MISSING_DIAGNOSIS_REF', 'MISSING_EVIDENCE_REF'], details: [],
    },
  },
  step_results: {},
});
const completedNotExecuted = () => ({
  workflow: {
    ...SUSPENDED_WORKFLOW, status: 'completed', current_step: null, steps_done: 6,
    completed_steps: ['detect', 'confirm', 'recommend', 'await_approval', 'execute', 'follow_up'],
  },
  context: { ...withLineage().context, approval_status: 'approved', executed: false },
  step_results: {
    execute: {
      executed: false, blocked_by: 'guardrails',
      note_ar: 'لا يُنفَّذ المبيد: أدلّة فحص السلامة الكيميائيّة غير متاحة على الخادم.',
      guardrails: {
        allowed: false, status: 'evidence_unavailable',
        reason_ar: 'لا يُنفَّذ المبيد: أدلّة فحص السلامة الكيميائيّة غير متاحة على الخادم.',
        no_server_source: ['action_data.chemical', 'farm_context.cash_reserve_usd'],
      },
    },
    follow_up: { follow_up_scheduled: false },
  },
});

const h = vi.hoisted(() => ({
  mutate: vi.fn(),
  mut: { isPending: false, isError: false, error: null as unknown, data: undefined as unknown },
  photo: { isLoading: false, isError: false, error: null as unknown, data: undefined as unknown },
  pins: [] as unknown[],
  role: 'owner',
}));

vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => ({
    fieldId: 'fld_1',
    options: [{ id: 'fld_1', name: 'North block', crop: 'tomato' }],
    isLoading: false,
    isError: false,
  }),
}));
vi.mock('../hooks/useAuth', () => ({
  useAuthStore: (sel: (s: { user: { role: string } }) => unknown) => sel({ user: { role: h.role } }),
}));
vi.mock('../hooks/useApi', () => ({
  usePestEscalation: () => ({ ...h.mut, mutate: h.mutate }),
  useIpmPlan: () => ({ data: undefined }),
}));
vi.mock('../hooks/useScouting', () => ({
  useScoutingPins: (fieldId?: string) => ({
    isLoading: false, isError: false,
    data: fieldId ? { field_id: fieldId, pins: h.pins, total: h.pins.length } : undefined,
  }),
  useScoutPhotoContext: (fieldId?: string, pinId?: string) =>
    (fieldId && pinId ? h.photo : { isLoading: false, isError: false, error: null, data: undefined }),
}));

import PestEscalationPage from './PestEscalationPage';

const approveButton = () => screen.getByRole('button', { name: /موافقة الخبير/ });
const lastPayload = () => h.mutate.mock.calls[h.mutate.mock.calls.length - 1]?.[0] as Record<string, unknown>;
const pickPin = () => fireEvent.change(screen.getByLabelText('مشاهدة الاستطلاع'), { target: { value: 'pin_42' } });

beforeEach(() => {
  h.mutate.mockReset();
  h.mut = { isPending: false, isError: false, error: null, data: undefined };
  h.photo = { isLoading: false, isError: false, error: null, data: PHOTO_CONTEXT };
  h.pins = [PIN];
  h.role = 'owner';
});

describe('PestEscalationPage — البداية من مرجع حقيقيّ', () => {
  it('لا تشغيل بلا دبّوس استطلاع من الخادم، ولا قائمة آفات حرّة', () => {
    render(<PestEscalationPage />);
    expect(screen.getByRole('button', { name: /تشغيل التدفّق من المشاهدة/ })).toBeDisabled();
    expect(screen.queryByText('نوع الآفة')).toBeNull();
  });

  it('التشغيل يرسل مراجع الدبّوس وسياق دليله كما أعادها الخادم', () => {
    render(<PestEscalationPage />);
    pickPin();
    fireEvent.click(screen.getByRole('button', { name: /تشغيل التدفّق من المشاهدة/ }));
    const p = lastPayload();
    expect(p).toMatchObject({
      field_id: 'fld_1',
      season_id: 'sea-7',
      diagnosis_ref: 'rev-3',
      evidence_ref: `scout_photo_evidence:ev-1@${SHA}`,
      pest_type: 'tomato_leafminer',
    });
    expect(String(p.workflow_id)).toMatch(/^pest-pin-pin_42-/);
  });

  it('سياق دليل غائب (404) ⇒ يُرسَل ما أعاده الخادم فقط بلا اختراع مراجع', () => {
    h.photo = { isLoading: false, isError: true, error: { response: { status: 404 } }, data: undefined };
    render(<PestEscalationPage />);
    pickPin();
    expect(screen.getByText(/لا دليل صورة لهذا الدبّوس/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /تشغيل التدفّق من المشاهدة/ }));
    const p = lastPayload();
    expect(p.field_id).toBe('fld_1');
    expect(p.pest_type).toBe('tomato.tuta');
    expect(p.diagnosis_ref).toBeUndefined();
    expect(p.evidence_ref).toBeUndefined();
    expect(p.season_id).toBeUndefined();
  });
});

describe('PestEscalationPage — حجب الموافقة بلا سلسلة', () => {
  it('بلا سلسلة من الخادم ⇒ زرّ الموافقة معطَّل ومشروح، والنقر لا يرسل شيئاً', () => {
    h.mut = { ...h.mut, data: withoutLineage() };
    render(<PestEscalationPage />);
    expect(approveButton()).toBeDisabled();
    expect(screen.getByText(/الموافقة محجوبة/)).toBeInTheDocument();
    const reasons = screen.getByTestId('lineage-block-reasons');
    expect(reasons.textContent).toContain('MISSING_DIAGNOSIS_REF');
    expect(reasons.textContent).toContain('MISSING_EVIDENCE_REF');
    fireEvent.click(approveButton());
    expect(h.mutate).not.toHaveBeenCalled();
  });

  it('تدقيق مفقود كلّيّاً من الردّ ⇒ زرّ الموافقة معطَّل', () => {
    const res = withLineage();
    delete (res.context as Record<string, unknown>).chemical_lineage_audit;
    h.mut = { ...h.mut, data: res };
    render(<PestEscalationPage />);
    expect(approveButton()).toBeDisabled();
  });

  it('بسلسلة أثبتها الخادم ⇒ زرّ الموافقة مُفعَّل ويعيد المراجع من سياق الخادم', () => {
    h.mut = { ...h.mut, data: withLineage() };
    render(<PestEscalationPage />);
    expect(approveButton()).toBeEnabled();
    expect(screen.queryByTestId('lineage-block-reasons')).toBeNull();
    fireEvent.click(approveButton());
    expect(lastPayload()).toEqual({
      workflow_id: expect.any(String),
      approval_status: 'approved',
      field_id: 'fld_1',
      season_id: 'sea-7',
      diagnosis_ref: 'rev-3',
      evidence_ref: `scout_photo_evidence:ev-1@${SHA}`,
    });
  });

  it('بسلسلة لكن دور viewer ⇒ معطَّل', () => {
    h.role = 'viewer';
    h.mut = { ...h.mut, data: withLineage() };
    render(<PestEscalationPage />);
    expect(approveButton()).toBeDisabled();
  });
});

describe('PestEscalationPage — نتيجة التنفيذ الحقيقيّة', () => {
  it('executed=false يُعرَض «لم يُنفَّذ» مع السبب، لا نجاحاً', () => {
    h.mut = { ...h.mut, data: completedNotExecuted() };
    render(<PestEscalationPage />);
    const box = screen.getByTestId('execution-outcome');
    expect(box.textContent).toContain('لم يُنفَّذ (executed=false)');
    expect(box.textContent).toContain('أدلّة فحص السلامة الكيميائيّة غير متاحة');
    expect(box.textContent).toContain('farm_context.cash_reserve_usd');
    expect(box.textContent).not.toContain('نُفِّذ بحسب الخادم');
    expect(screen.queryByRole('button', { name: /موافقة الخبير/ })).toBeNull();
  });

  it('executed=true يُعرَض بمرجع التنفيذ الذي أعاده الخادم', () => {
    const res = completedNotExecuted();
    res.step_results.execute = {
      executed: true, execution_ref: 'task-42',
      guardrails: { allowed: true, status: 'allowed', reason_ar: 'سمح' },
    } as never;
    h.mut = { ...h.mut, data: res };
    render(<PestEscalationPage />);
    const box = screen.getByTestId('execution-outcome');
    expect(box.textContent).toContain('نُفِّذ بحسب الخادم');
    expect(box.textContent).toContain('task-42');
  });

  it('the server placeholder exec-urgent_spray is shown as unconfirmed, never as executed', () => {
    const res = completedNotExecuted();
    res.step_results.execute = {
      executed: true, execution_ref: 'exec-urgent_spray',
      guardrails: { allowed: true, status: 'allowed', reason_ar: 'سمح' },
    } as never;
    h.mut = { ...h.mut, data: res };
    render(<PestEscalationPage />);
    const box = screen.getByTestId('execution-outcome');
    expect(box.textContent).toContain('تنفيذ غير مؤكَّد');
    expect(box.textContent).toContain('لا منفّذ موصول');
    expect(box.textContent).not.toContain('نُفِّذ بحسب الخادم');
  });

  it('رفض الخادم للسلسلة (422 CHEMICAL_LINEAGE_REQUIRED) يُعرَض بكلماته', () => {
    h.mut = {
      ...h.mut, isError: true,
      error: { response: { status: 422, data: { detail: { code: 'CHEMICAL_LINEAGE_REQUIRED', violations: ['MISSING_DIAGNOSIS_REF'] } } } },
    };
    render(<PestEscalationPage />);
    expect(screen.getByText(/يلزم ربط تشخيص ودليل/)).toBeInTheDocument();
    expect(screen.getByText(/MISSING_DIAGNOSIS_REF/)).toBeInTheDocument();
  });
});
