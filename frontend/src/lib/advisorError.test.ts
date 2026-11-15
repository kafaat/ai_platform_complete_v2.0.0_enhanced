import { describe, expect, it } from 'vitest';

import { describeAdvisorFailure } from './advisorError';

const http = (status: number, data?: unknown) => ({ response: { status, data } });

describe('describeAdvisorFailure', () => {
  it('tells a login problem apart from an advisor outage', () => {
    expect(describeAdvisorFailure(http(401)).kind).toBe('auth');
    expect(describeAdvisorFailure(http(403)).kind).toBe('auth');
    const down = describeAdvisorFailure(http(503, { detail: 'approval_store_unavailable' }));
    expect(down.kind).toBe('unavailable');
    expect(down.messageAr).not.toContain('سجّل الدخول');
  });

  it('surfaces the server reason code', () => {
    const f = describeAdvisorFailure(http(503, { detail: 'approval_store_unavailable' }));
    expect(f.reasonCode).toBe('approval_store_unavailable');
    expect(f.messageAr).toContain('approval_store_unavailable');
    expect(describeAdvisorFailure(http(502, { detail: { reason_code: 'rag_unavailable' } })).reasonCode)
      .toBe('rag_unavailable');
  });

  it('never echoes free text from the server', () => {
    const f = describeAdvisorFailure(http(500, { detail: 'Traceback (most recent call last): ...' }));
    expect(f.reasonCode).toBeNull();
    expect(f.messageAr).not.toContain('Traceback');
    expect(f.kind).toBe('rejected');
  });

  it('classifies timeouts and network errors', () => {
    expect(describeAdvisorFailure(http(504)).kind).toBe('timeout');
    expect(describeAdvisorFailure({ code: 'ECONNABORTED' }).kind).toBe('timeout');
    expect(describeAdvisorFailure(new Error('Network Error')).kind).toBe('network');
    expect(describeAdvisorFailure(undefined).kind).toBe('network');
  });
});
