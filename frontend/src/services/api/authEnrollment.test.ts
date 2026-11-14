// تسجيل MFA الإلزاميّ — عقد العميل مع services/auth (routers/session.py + mfa.py).
//
// axios حقيقيّ بمحوِّل (adapter) مزيَّف: نفحص الترويسات كما تصل إلى الشبكة فعلاً بعد
// كلّ الـinterceptors، لا كما يطلبها المستدعي. الخطر المحروس: عميل authApi العاديّ
// يكتب فوق Authorization الصريحة توكنَ الجلسة المخزَّن، ويرفض الطلب كلّه (ويُطلق
// خروجاً) إن كان ذلك التوكن منتهياً، ويحوّل 401 إلى مسح جلسة + 'sahool:auth:unauthorized'.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { authEnrollmentApi } from './client';
import {
  classifyMfaEnrollmentError,
  mfaEnrollmentActivate,
  mfaEnrollmentChallenge,
  mfaEnrollmentSetup,
} from './auth';

type Seen = { url?: string; authorization?: string; tenant?: string; data?: unknown };

function fakeServer(status: number, body: unknown) {
  const seen: Seen[] = [];
  const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
    const headers = AxiosHeaders.from(config.headers);
    seen.push({
      url: config.url,
      authorization: headers.get('Authorization') as string | undefined,
      tenant: headers.get('X-Tenant-ID') as string | undefined,
      data: typeof config.data === 'string' ? JSON.parse(config.data) : config.data,
    });
    const response = {
      data: body, status, statusText: String(status),
      headers: { 'content-type': 'application/json' }, config,
    } as AxiosResponse;
    if (status >= 400) {
      throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, null, response);
    }
    return response;
  });
  authEnrollmentApi.defaults.adapter = adapter;
  return seen;
}

// JWT منتهٍ بلا توقيع صالح (exp في الماضي) — يكفي لفحص انتهاء جهة العميل.
const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
const EXPIRED_SESSION = `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ sub: '9', exp: 1 })}.sig`;

const originalAdapter = authEnrollmentApi.defaults.adapter;
let unauthorized: ReturnType<typeof vi.fn<(e: Event) => void>>;

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  unauthorized = vi.fn<(e: Event) => void>();
  window.addEventListener('sahool:auth:unauthorized', unauthorized);
});

afterEach(() => {
  window.removeEventListener('sahool:auth:unauthorized', unauthorized);
  authEnrollmentApi.defaults.adapter = originalAdapter;
});

describe('mfaEnrollmentSetup / mfaEnrollmentActivate — the proof is the only credential', () => {
  it('setup sends Authorization: Bearer <setup proof>, not a stored session token, and no tenant header', async () => {
    sessionStorage.setItem('sahool_access_token', 'stale-session-token');
    sessionStorage.setItem('sahool_tenant_id', 'tenant-x');
    const seen = fakeServer(200, {
      secret: 'JBSWY3DPEHPK3PXP', provisioning_uri: 'otpauth://totp/SAHOOL:a?secret=JBSWY3DPEHPK3PXP',
      enrollment_token: 'proof-activate', expires_in: 300, message: 'ok',
    });

    const res = await mfaEnrollmentSetup('proof-setup');

    expect(seen).toHaveLength(1);
    expect(seen[0].url).toBe('/auth/mfa/setup');
    expect(seen[0].authorization).toBe('Bearer proof-setup');
    expect(seen[0].tenant).toBeUndefined();
    expect(res.enrollment_token).toBe('proof-activate');
  });

  it('activate sends the activation proof and the code body', async () => {
    const seen = fakeServer(200, { message: 'ok', mfa_enabled: true, recovery_codes: ['a-1'] });

    const res = await mfaEnrollmentActivate('proof-activate', '123456');

    expect(seen[0].url).toBe('/auth/mfa/activate');
    expect(seen[0].authorization).toBe('Bearer proof-activate');
    expect(seen[0].data).toEqual({ code: '123456' });
    expect(res.recovery_codes).toEqual(['a-1']);
  });

  it('an expired stored session token does not block the request or fire a logout', async () => {
    sessionStorage.setItem('sahool_access_token', EXPIRED_SESSION);
    const seen = fakeServer(200, { message: 'ok', mfa_enabled: true });

    await mfaEnrollmentActivate('proof-activate', '123456');

    expect(seen[0].authorization).toBe('Bearer proof-activate');
    expect(unauthorized).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('sahool_access_token')).toBe(EXPIRED_SESSION);
  });

  it('a 401 (proof expired/consumed) is returned to the caller without the session-logout interceptor', async () => {
    sessionStorage.setItem('sahool_access_token', 'other-session');
    fakeServer(401, { detail: 'MFA enrollment proof expired or consumed' });

    const err = await mfaEnrollmentSetup('proof-setup').catch((e: unknown) => e);

    expect(classifyMfaEnrollmentError(err)).toBe('restart');
    expect(unauthorized).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('sahool_access_token')).toBe('other-session');
  });

  it('never writes the proof to web storage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    fakeServer(200, { secret: 'S', provisioning_uri: 'otpauth://x', enrollment_token: 'proof-activate', message: '' });

    await mfaEnrollmentSetup('proof-setup');
    fakeServer(200, { message: 'ok', mfa_enabled: true });
    await mfaEnrollmentActivate('proof-activate', '123456');

    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
});

describe('mfaEnrollmentChallenge — reads the login 403 body', () => {
  it('returns the proof and TTL from 403 + enrollment_token', () => {
    expect(mfaEnrollmentChallenge({
      response: { status: 403, data: { detail: 'x', enrollment_token: 'p', expires_in: 300, token_type: 'Bearer' } },
    })).toEqual({ enrollment_token: 'p', expires_in: 300 });
  });

  it('ignores a plain 403, an empty/non-string token, and other statuses', () => {
    expect(mfaEnrollmentChallenge({ response: { status: 403, data: { detail: 'ممنوع' } } })).toBeNull();
    expect(mfaEnrollmentChallenge({ response: { status: 403, data: { enrollment_token: '' } } })).toBeNull();
    expect(mfaEnrollmentChallenge({ response: { status: 403, data: { enrollment_token: 7 } } })).toBeNull();
    expect(mfaEnrollmentChallenge({ response: { status: 401, data: { enrollment_token: 'p' } } })).toBeNull();
    expect(mfaEnrollmentChallenge(undefined)).toBeNull();
  });

  it('drops a non-numeric TTL instead of trusting it', () => {
    expect(mfaEnrollmentChallenge({ response: { status: 403, data: { enrollment_token: 'p', expires_in: 'soon' } } }))
      .toEqual({ enrollment_token: 'p' });
  });
});

describe('classifyMfaEnrollmentError', () => {
  it.each([
    [{ message: 'Network Error' }, 'network'],
    [{ response: { status: 400 } }, 'bad_code'],
    [{ response: { status: 422 } }, 'bad_code'],
    [{ response: { status: 401 } }, 'restart'],
    [{ response: { status: 404 } }, 'restart'],
    [{ response: { status: 409 } }, 'restart'],
    [{ response: { status: 429 } }, 'locked'],
    [{ response: { status: 503 } }, 'unavailable'],
    [{ response: { status: 502 } }, 'unavailable'],
    [{ response: { status: 500 } }, 'other'],
  ])('%j → %s', (err, kind) => {
    expect(classifyMfaEnrollmentError(err)).toBe(kind);
  });
});
