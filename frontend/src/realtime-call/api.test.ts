import { describe, expect, it, vi } from 'vitest';
import { CallApi, type Session, validateSession } from './api';
const valid = (): Session => ({ session_id: 'id', field_id: 'field', status: 'ACTIVE', expires_at: 1250, token_expires_at: 1050, participant_token: 'participant-token', url: 'wss://sfu.example.test' });
describe('trusted session response boundary', () => {
  it('accepts the valid scoped response', () => expect(() => validateSession(valid(), 'field', 1000)).not.toThrow());
  it.each([
    { url: 'ws://sfu.example.test' }, { url: 'wss://user:secret@sfu.example.test' },
    { url: 'wss://sfu.example.test?access_token=secret' }, { url: 'wss://sfu.example.test#secret' },
    { field_id: 'other' }, { status: 'PENDING' }, { expires_at: 999 }, { expires_at: 1350 },
    { token_expires_at: NaN }, { token_expires_at: undefined }, { token_expires_at: 1050.5 }, { session_id: '../unsafe' }, { participant_token: 12 }, { token_expires_at: 999 }, { token_expires_at: 1070 }, { participant_token: '' }, { expires_at: NaN },
  ])('rejects unsafe response %j', patch => expect(() => validateSession({ ...valid(), ...patch } as unknown as Session, 'field', 1000)).toThrow());
});
describe('independent in-memory authentication', () => {
  it('omits ambient cookies during login and sends MFA only when supplied', async () => { const fetcher = vi.fn(async () => new Response(JSON.stringify({ access_token: 'scoped' }))); const api = new CallApi(fetcher as typeof fetch); await api.login('a@example.test', 'password', '123456'); expect(fetcher).toHaveBeenCalledWith('/auth/login', expect.objectContaining({ credentials: 'omit', cache: 'no-store', body: JSON.stringify({ email: 'a@example.test', password: 'password', mfa_code: '123456' }) })); });
  it('cannot restore credentials after clear during an unresolved login', async () => {
    let resolve!: (response: Response) => void;
    const response = new Promise<Response>(r => { resolve = r; });
    const api = new CallApi(vi.fn(() => response) as typeof fetch);
    const loggingIn = api.login('a', 'b'); api.clear();
    resolve(new Response(JSON.stringify({ access_token: 'late-credential' })));
    await expect(loggingIn).rejects.toThrow('انتهت محاولة تسجيل الدخول');
    await expect(api.create('field')).rejects.toThrow('يلزم تسجيل الدخول');
  });
  it('surfaces the actual MFA challenge', async () => { const api = new CallApi(vi.fn(async () => new Response('', { status: 401, headers: { 'X-MFA-Required': 'true' } })) as typeof fetch); await expect(api.login('a', 'b')).rejects.toThrow('MFA_REQUIRED'); });
  it('requires login instead of reading localStorage or cookies', async () => { const api = new CallApi(vi.fn() as typeof fetch); await expect(api.create('field')).rejects.toThrow('يلزم تسجيل الدخول'); });
  it('sends consent and memory bearer only to a fixed relative endpoint', async () => { const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 'scoped' }))).mockResolvedValueOnce(new Response(JSON.stringify(valid()))); const api = new CallApi(fetcher as typeof fetch); await api.login('a', 'b'); await api.create('field'); expect(fetcher.mock.calls[1]).toEqual(['/api/v1/realtime/sessions', expect.objectContaining({ credentials: 'omit', headers: expect.objectContaining({ Authorization: 'Bearer scoped' }), body: JSON.stringify({ field_id: 'field', consent: true, voice_consent: true }) })]); api.clear(); await expect(api.create('field')).rejects.toThrow(); });
});
