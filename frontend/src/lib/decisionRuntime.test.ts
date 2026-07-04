import { describe, expect, it } from 'vitest';
import {
  buildOutcomeInput,
  outcomeStatusColor,
  dispatchStateColor,
  dispatchStateLabel,
  summarizeDecisions,
  type DispatchDecision,
} from './decisionRuntime';

const dec = (state: string): DispatchDecision => ({
  decision_id: 'd1', recommendation_id: 'r1', action_type: 'irrigation', field_id: null,
  state, risk_level: 'HIGH', required_approvals: 1, approvals_collected: 0,
  halt_breaches: [], warn_breaches: [], reason_ar: null, exec_status: null, created_at: null,
});

describe('dispatchStateLabel/Color — server states as-is', () => {
  it('maps the three governed states', () => {
    expect(dispatchStateLabel('blocked')).toBe('محجوب');
    expect(dispatchStateLabel('pending_approval')).toBe('بانتظار موافقة');
    expect(dispatchStateLabel('ready')).toBe('جاهز');
    expect(dispatchStateColor('ready')).toBe('#86efac');
    expect(dispatchStateColor('blocked')).toBe('#fca5a5');
  });
  it('passes unknown states through honestly with neutral color', () => {
    expect(dispatchStateLabel('weird')).toBe('weird');
    expect(dispatchStateColor('weird')).toBe('#64748b');
    expect(dispatchStateLabel(null)).toBe('—');
  });
});

describe('summarizeDecisions — counts server states, strange states only in total', () => {
  it('counts blocked/pending/ready', () => {
    const o = summarizeDecisions([dec('blocked'), dec('ready'), dec('ready'), dec('pending_approval'), dec('mystery')]);
    expect(o).toEqual({ total: 5, blocked: 1, pendingApproval: 1, ready: 2 });
  });
  it('is all-zero for missing input', () => {
    expect(summarizeDecisions(null).total).toBe(0);
  });
});

describe('outcomeStatusColor — server outcome vocabulary', () => {
  it('colors positive/acceptable/negative/missing statuses', () => {
    expect(outcomeStatusColor('followed')).toBe('#86efac');
    expect(outcomeStatusColor('worse')).toBe('#fca5a5');
    expect(outcomeStatusColor('under')).toBe('#fdba74');
    expect(outcomeStatusColor('needs_data')).toBe('#64748b');
    expect(outcomeStatusColor('mystery')).toBe('#64748b');
  });
});

describe('buildOutcomeInput — empty stays absent, never zero-filled', () => {
  it('includes only provided numeric fields', () => {
    const input = buildOutcomeInput({ fieldId: 'f1', recommendedIrrigationMm: '120', actualIrrigationMm: '150' });
    expect(input.planned).toEqual({ recommended_irrigation_mm: 120 });
    expect(input.actual).toEqual({ actual_irrigation_mm: 150 });
    expect('decision_id' in input).toBe(false);
  });
  it('drops blanks and non-numeric junk (server will say needs_data honestly)', () => {
    const input = buildOutcomeInput({ recommendedIrrigationMm: '', actualYieldTHa: 'abc' });
    expect(input.planned).toEqual({});
    expect(input.actual).toEqual({});
  });
});
