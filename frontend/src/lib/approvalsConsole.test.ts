import { describe, expect, it } from 'vitest';
import { approvalKey, paramsSummary, pendingDispatchDecisions, riskColor } from './approvalsConsole';
import type { DispatchDecision } from './decisionRuntime';

const dec = (state: string): DispatchDecision => ({
  decision_id: 'd1', recommendation_id: 'r1', action_type: 'irrigation', field_id: null,
  state, risk_level: 'HIGH', required_approvals: 2, approvals_collected: 1,
  halt_breaches: [], warn_breaches: [], reason_ar: null, exec_status: null, created_at: null,
});

describe('riskColor — known risks only, unknown neutral', () => {
  it('colors the four known levels case-insensitively', () => {
    expect(riskColor('low')).toBe('#86efac');
    expect(riskColor('HIGH')).toBe('#fdba74');
    expect(riskColor('critical')).toBe('#fca5a5');
  });
  it('is neutral for unknown/missing', () => {
    expect(riskColor('weird')).toBe('#64748b');
    expect(riskColor(null)).toBe('#64748b');
  });
});

describe('approvalKey + paramsSummary', () => {
  it('prefers id then tool (mirrors ChatbotPage)', () => {
    expect(approvalKey({ id: 'a1', tool: 't' })).toBe('a1');
    expect(approvalKey({ tool: 'create_task' })).toBe('create_task');
    expect(approvalKey({})).toBe('approval');
  });
  it('summarizes param keys only (values may be sensitive) with honest overflow', () => {
    expect(paramsSummary({ a: 1, b: 2 })).toBe('a، b');
    expect(paramsSummary({ a: 1, b: 2, c: 3, d: 4, e: 5 })).toBe('a، b، c، d … (+1)');
    expect(paramsSummary(null)).toBe('—');
  });
});

describe('pendingDispatchDecisions — server state as-is', () => {
  it('keeps only pending_approval', () => {
    const out = pendingDispatchDecisions([dec('ready'), dec('pending_approval'), dec('blocked')]);
    expect(out).toHaveLength(1);
    expect(out[0].state).toBe('pending_approval');
  });
  it('is empty for missing input', () => {
    expect(pendingDispatchDecisions(null)).toEqual([]);
  });
});
