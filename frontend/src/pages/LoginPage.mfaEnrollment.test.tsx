// تسجيل MFA الإلزاميّ من شاشة الدخول — 403 + enrollment_token ⇒ setup ⇒ activate ⇒ دخول.
//
// useAuth مُستبدَل (login يرفض بخطأ أكسيوس الشكل كما يردّه الخادم)، أمّا setup/activate
// فيمرّان عبر axios حقيقيّ بمحوِّل مزيَّف على authEnrollmentApi — فنرى الترويسة الفعليّة
// التي تخرج للشبكة. العقد: services/auth/routers/session.py (جسم 403) وrouters/mfa.py.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';

const mockLogin = vi.fn();
vi.mock('../hooks/useAuth', () => ({
  useAuthStore: () => ({ login: mockLogin, loginDemo: vi.fn() }),
}));

import LoginPage from './LoginPage';
import { authEnrollmentApi } from '../services/api/client';

const SETUP_PROOF = 'proof-setup-SECRET-1';
const ACTIVATION_PROOF = 'proof-activate-SECRET-2';
const TOTP_SECRET = 'JBSWY3DPEHPK3PXP';
const URI = `otpauth://totp/SAHOOL:admin%40sahool.ye?secret=${TOTP_SECRET}&issuer=SAHOOL`;

const enrollment403 = {
  response: {
    status: 403,
    headers: {},
    data: {
      detail: 'يتطلّب الحساب تفعيل MFA عبر /v1/auth/mfa/setup',
      enrollment_token: SETUP_PROOF,
      expires_in: 300,
      token_type: 'Bearer',
    },
  },
};

type Reply = { status: number; body: unknown } | 'network';
type Call = { url?: string; authorization?: string; tenant?: string; data?: unknown };

function serve(replies: Reply[]) {
  const calls: Call[] = [];
  authEnrollmentApi.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    const headers = AxiosHeaders.from(config.headers);
    calls.push({
      url: config.url,
      authorization: headers.get('Authorization') as string | undefined,
      tenant: headers.get('X-Tenant-ID') as string | undefined,
      data: typeof config.data === 'string' ? JSON.parse(config.data) : config.data,
    });
    const reply = replies.shift();
    if (!reply) throw new Error(`unexpected request ${config.url}`);
    if (reply === 'network') throw new AxiosError('Network Error', 'ERR_NETWORK', config, null);
    const response = {
      data: reply.body, status: reply.status, statusText: String(reply.status),
      headers: { 'content-type': 'application/json' }, config,
    } as AxiosResponse;
    if (reply.status >= 400) throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, null, response);
    return response;
  };
  return calls;
}

const setupOk = {
  status: 200,
  body: { enrollment_token: ACTIVATION_PROOF, expires_in: 300, secret: TOTP_SECRET, provisioning_uri: URI, message: 'x' },
};
const activateOk = {
  status: 200,
  body: { message: 'ok', mfa_enabled: true, recovery_codes: ['rc-aaaa-1111', 'rc-bbbb-2222'], recovery_codes_notice: 'x' },
};

const originalAdapter = authEnrollmentApi.defaults.adapter;
let setItem: ReturnType<typeof vi.spyOn>;
let consoleSpies: ReturnType<typeof vi.spyOn>[];

beforeEach(() => {
  mockLogin.mockReset();
  sessionStorage.clear();
  localStorage.clear();
  setItem = vi.spyOn(Storage.prototype, 'setItem');
  consoleSpies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m));
});

afterEach(() => {
  authEnrollmentApi.defaults.adapter = originalAdapter;
  setItem.mockRestore();
  consoleSpies.forEach((s) => s.mockRestore());
});

function signIn() {
  fireEvent.change(screen.getByLabelText('البريد الإلكتروني'), { target: { value: 'admin@sahool.ye' } });
  fireEvent.change(screen.getByLabelText('كلمة المرور'), { target: { value: 'Correct#Pass1' } });
  fireEvent.click(screen.getByRole('button', { name: 'تسجيل الدخول' }));
}

async function reachSetup() {
  mockLogin.mockRejectedValueOnce(enrollment403);
  render(<LoginPage />);
  signIn();
  fireEvent.click(await screen.findByRole('button', { name: 'بدء تفعيل المصادقة الثنائيّة' }));
  await screen.findByTestId('mfa-enroll-secret');
}

function enterCode(code: string) {
  fireEvent.change(screen.getByLabelText(/رمز التأكيد من تطبيق المصادقة/), { target: { value: code } });
  fireEvent.click(screen.getByRole('button', { name: /^تفعيل/ }));
}

function assertProofNeverPersistedOrLogged() {
  const proofs = [SETUP_PROOF, ACTIVATION_PROOF];
  for (const call of setItem.mock.calls) {
    for (const p of proofs) expect(JSON.stringify(call)).not.toContain(p);
  }
  for (const spy of consoleSpies) {
    for (const call of spy.mock.calls) {
      for (const p of proofs) expect(call.map(String).join(' ')).not.toContain(p);
    }
  }
  const stored = JSON.stringify({ ...sessionStorage }) + JSON.stringify({ ...localStorage });
  for (const p of proofs) expect(stored).not.toContain(p);
}

describe('LoginPage — mandatory MFA enrollment (403 + enrollment_token)', () => {
  it('login 403 with an enrollment token opens the enrollment step (not an error)', async () => {
    mockLogin.mockRejectedValueOnce(enrollment403);
    render(<LoginPage />);
    signIn();

    expect(await screen.findByText('تفعيل المصادقة الثنائيّة (إلزاميّ)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'بدء تفعيل المصادقة الثنائيّة' })).toBeInTheDocument();
    expect(screen.getByText(/أكمِل الخطوات خلال 5 دقائق/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('كلمة المرور')).not.toBeInTheDocument();
  });

  it('setup is called with Authorization: Bearer <proof>, no tenant header, and nothing is stored', async () => {
    sessionStorage.setItem('sahool_access_token', 'leftover-session-token');
    sessionStorage.setItem('sahool_tenant_id', 'tenant-left');
    setItem.mockClear();
    const calls = serve([setupOk]);

    await reachSetup();

    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ url: '/auth/mfa/setup', authorization: `Bearer ${SETUP_PROOF}` });
    expect(calls[0].tenant).toBeUndefined();
    expect(screen.getByTestId('mfa-enroll-secret')).toHaveTextContent(TOTP_SECRET);
    expect(screen.getByTestId('mfa-enroll-uri')).toHaveTextContent(URI);
    expect(screen.getByRole('link', { name: /فتح في تطبيق المصادقة/ })).toHaveAttribute('href', URI);
    expect(setItem).not.toHaveBeenCalled();
    assertProofNeverPersistedOrLogged();
  });

  it('activate success shows recovery codes once, then returns to sign-in with TOTP required and a message', async () => {
    const calls = serve([setupOk, activateOk]);
    await reachSetup();

    enterCode('123456');

    expect(await screen.findByText('تم تفعيل المصادقة الثنائيّة بنجاح')).toBeInTheDocument();
    expect(calls[1]).toMatchObject({
      url: '/auth/mfa/activate', authorization: `Bearer ${ACTIVATION_PROOF}`, data: { code: '123456' },
    });
    expect(screen.getByText('rc-aaaa-1111')).toBeInTheDocument();
    expect(screen.queryByTestId('mfa-enroll-secret')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'متابعة لتسجيل الدخول' }));

    expect(await screen.findByRole('status')).toHaveTextContent('تم تفعيل المصادقة الثنائيّة');
    expect(screen.getByText(/رمز المصادقة الثنائيّة \(TOTP\)/)).toBeInTheDocument();
    expect(screen.queryByText('rc-aaaa-1111')).not.toBeInTheDocument();
    // الدخول التالي يُرسِل الرمز مع كلمة المرور (المسار العاديّ بعد الإعداد).
    mockLogin.mockResolvedValueOnce(undefined);
    fireEvent.change(screen.getByPlaceholderText('123456'), { target: { value: '654321' } });
    fireEvent.click(screen.getByRole('button', { name: 'تسجيل الدخول' }));
    await waitFor(() => expect(mockLogin).toHaveBeenLastCalledWith('admin@sahool.ye', 'Correct#Pass1', '654321'));
    assertProofNeverPersistedOrLogged();
  });

  it('a wrong code shows an error and allows a retry with the same activation proof', async () => {
    const calls = serve([
      setupOk,
      { status: 400, body: { detail: 'رمز غير صحيح — تأكّد من تطبيق المصادقة' } },
      activateOk,
    ]);
    await reachSetup();

    enterCode('000000');
    expect(await screen.findByRole('alert')).toHaveTextContent('رمز غير صحيح');
    expect(screen.getByTestId('mfa-enroll-secret')).toBeInTheDocument();

    enterCode('123456');
    expect(await screen.findByText('تم تفعيل المصادقة الثنائيّة بنجاح')).toBeInTheDocument();
    expect(calls.map((c) => c.authorization)).toEqual([
      `Bearer ${SETUP_PROOF}`, `Bearer ${ACTIVATION_PROOF}`, `Bearer ${ACTIVATION_PROOF}`,
    ]);
  });

  it.each([
    [401, 'MFA enrollment proof expired or consumed'],
    [409, 'MFA enrollment state changed; sign in again'],
  ])('activate %i (expired/consumed proof) tells the user to sign in again and hides the secret', async (status, detail) => {
    serve([setupOk, { status, body: { detail } }]);
    await reachSetup();

    enterCode('123456');

    expect(await screen.findByRole('alert')).toHaveTextContent('سجّل الدخول من جديد');
    expect(screen.queryByTestId('mfa-enroll-secret')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/رمز التأكيد/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'العودة لتسجيل الدخول' }));
    // نموذج الدخول يعود بالبريد/كلمة المرور نفسيهما فيُصدِر دخولٌ جديد إثباتاً جديداً.
    expect(await screen.findByLabelText('كلمة المرور')).toHaveValue('Correct#Pass1');
    expect(screen.queryByText(/رمز المصادقة الثنائيّة \(TOTP\)/)).not.toBeInTheDocument();
  });

  it('setup 401 (proof already used) goes straight to the restart message', async () => {
    serve([{ status: 401, body: { detail: 'MFA enrollment proof expired or consumed' } }]);
    mockLogin.mockRejectedValueOnce(enrollment403);
    render(<LoginPage />);
    signIn();
    fireEvent.click(await screen.findByRole('button', { name: 'بدء تفعيل المصادقة الثنائيّة' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('انتهت صلاحيّة خطوة التفعيل');
  });

  it('503 (Redis/encryption unavailable) is reported honestly and the user can retry', async () => {
    const calls = serve([{ status: 503, body: { detail: 'MFA enrollment requires Redis' } }, setupOk]);
    mockLogin.mockRejectedValueOnce(enrollment403);
    render(<LoginPage />);
    signIn();
    fireEvent.click(await screen.findByRole('button', { name: 'بدء تفعيل المصادقة الثنائيّة' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('غير متاحة حاليّاً');
    fireEvent.click(screen.getByRole('button', { name: 'بدء تفعيل المصادقة الثنائيّة' }));
    expect(await screen.findByTestId('mfa-enroll-secret')).toBeInTheDocument();
    expect(calls).toHaveLength(2);
  });

  it('a network failure during activate keeps the step open with a connectivity message', async () => {
    serve([setupOk, 'network']);
    await reachSetup();

    enterCode('123456');

    expect(await screen.findByRole('alert')).toHaveTextContent('تعذّر الوصول إلى خدمة المصادقة');
    expect(screen.getByTestId('mfa-enroll-secret')).toBeInTheDocument();
  });

  it('a 429 lockout is shown and returns the user to sign-in', async () => {
    serve([setupOk, { status: 429, body: { detail: 'locked' } }]);
    await reachSetup();

    enterCode('123456');

    expect(await screen.findByRole('alert')).toHaveTextContent('مقفل مؤقّتاً');
    expect(screen.queryByTestId('mfa-enroll-secret')).not.toBeInTheDocument();
  });

  it('a plain 403 without an enrollment token keeps the existing error behaviour', async () => {
    const calls = serve([]);
    mockLogin.mockRejectedValueOnce({ response: { status: 403, headers: {}, data: { detail: 'الحساب موقوف' } } });
    render(<LoginPage />);
    signIn();

    expect(await screen.findByRole('alert')).toHaveTextContent('الحساب موقوف');
    expect(screen.queryByText('تفعيل المصادقة الثنائيّة (إلزاميّ)')).not.toBeInTheDocument();
    expect(screen.getByLabelText('كلمة المرور')).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it('the existing 401 + X-MFA-Required challenge still shows the TOTP field', async () => {
    mockLogin.mockRejectedValueOnce({ response: { status: 401, headers: { 'x-mfa-required': 'true' }, data: {} } });
    render(<LoginPage />);
    signIn();

    expect(await screen.findByRole('alert')).toHaveTextContent('محميّ بالمصادقة الثنائيّة');
    expect(screen.getByText(/رمز المصادقة الثنائيّة \(TOTP\)/)).toBeInTheDocument();
  });
});
