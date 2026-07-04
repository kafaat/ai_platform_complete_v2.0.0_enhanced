import { describe, expect, it } from 'vitest';
import {
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
