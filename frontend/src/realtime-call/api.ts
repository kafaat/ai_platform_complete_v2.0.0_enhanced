export interface Session {
  session_id: string; field_id: string; expires_at: number; status: string;
  url: string; participant_token: string; token_expires_at: number;
}
export class CallApi {
  private bearer = '';
  private authEpoch = 0;
  constructor(private fetcher: typeof fetch = globalThis.fetch.bind(globalThis)) {}
  async login(email: string, password: string, mfa_code?: string): Promise<void> {
    const epoch = ++this.authEpoch;
    const response = await this.fetcher('/auth/login', {
      method: 'POST', credentials: 'omit', cache: 'no-store', signal: AbortSignal.timeout(10_000),
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, ...(mfa_code ? { mfa_code } : {}) }),
    });
    if (!response.ok) throw new Error(response.headers.get('X-MFA-Required') === 'true' ? 'MFA_REQUIRED' : 'تعذّر تسجيل الدخول');
    const data = await response.json();
    if (typeof data.access_token !== 'string' || !data.access_token) throw new Error('استجابة دخول غير صالحة');
    if (epoch !== this.authEpoch) throw new Error('انتهت محاولة تسجيل الدخول');
    this.bearer = data.access_token;
  }
  clear(): void { ++this.authEpoch; this.bearer = ''; }
  private async request(path: string, method: string, body?: unknown, keepalive = false): Promise<Response> {
    if (!this.bearer) throw new Error('يلزم تسجيل الدخول');
    const response = await this.fetcher(path, {
      method, credentials: 'omit', cache: 'no-store', keepalive,
      headers: { Authorization: `Bearer ${this.bearer}`, 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: keepalive ? undefined : AbortSignal.timeout(10_000),
    });
    if (!response.ok) throw new Error('تعذّر إتمام طلب الجلسة');
    return response;
  }
  async create(field: string): Promise<Session> {
    const response = await this.request('/api/v1/realtime/sessions', 'POST', {
      field_id: field, consent: true, voice_consent: true,
    });
    return response.json();
  }
  async close(id: string, keepalive = false): Promise<void> {
    await this.request(`/api/v1/realtime/sessions/${encodeURIComponent(id)}`, 'DELETE', undefined, keepalive);
  }
}
export function validateSession(session: Session, field: string, now = Date.now() / 1000): void {
  const url = new URL(session.url);
  if (url.protocol !== 'wss:' || url.username || url.password || url.search || url.hash ||
      session.field_id !== field || session.status !== 'ACTIVE' ||
      typeof session.session_id !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(session.session_id) ||
      typeof session.participant_token !== 'string' || !session.participant_token || session.participant_token.length > 16384 ||
      !Number.isSafeInteger(session.expires_at) || !Number.isSafeInteger(session.token_expires_at) ||
      session.expires_at <= now || session.expires_at > now + 305 ||
      session.token_expires_at <= now || session.token_expires_at > Math.min(now + 65, session.expires_at)) {
    throw new Error('بيانات جلسة غير صالحة');
  }
}
