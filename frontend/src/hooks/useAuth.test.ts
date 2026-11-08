// اختبارات useAuth — تثبّت أنّ حالة المصادقة المُرطَّبة (persist) تعيش في
// sessionStorage لا localStorage، فلا يبقى isAuthenticated في تبويب جديد بلا
// توكن (التوكن نفسه session-scoped). regression لانحراف التخزين.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { logout as apiLogout } from '../services/api';
import { useAuthStore } from './useAuth';

// S7 — نداء الخادم مُستبدَل (لا شبكة)؛ بقيّة الواجهة حقيقيّة.
vi.mock('../services/api', async (orig) => ({
  ...(await orig<typeof import('../services/api')>()),
  logout: vi.fn(() => Promise.resolve({ message: 'ok' })),
}));

describe('useAuth persistence', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    useAuthStore.getState().logout();
  });

  it('يحفظ حالة المصادقة في sessionStorage لا localStorage', () => {
    useAuthStore.getState().loginDemo();

    // الحالة المُرطَّبة (persist) يجب أن تكون في sessionStorage فقط.
    const persisted = sessionStorage.getItem('sahool-auth');
    expect(persisted).not.toBeNull();
    expect(localStorage.getItem('sahool-auth')).toBeNull();
    // والبنية المحفوظة تعكس حالة مُصادَقة فعليّة (لا علَم معلّق بلا سياق).
    expect(JSON.parse(persisted as string).state.isAuthenticated).toBe(true);
  });

  it('لا يُسرّب isAuthenticated إلى localStorage (لا حالة مُصادَقة بلا توكن)', () => {
    useAuthStore.getState().loginDemo();

    const persisted = localStorage.getItem('sahool-auth');
    expect(persisted).toBeNull();
    // مصدر الحقيقة للتوكن أيضاً sessionStorage.
    expect(sessionStorage.getItem('sahool_access_token')).not.toBeNull();
  });
});

// S7 (تدقيق 2026-11-01) — الخروج كان محلّيّاً فقط: التوكن وكوكي البلاطات (HttpOnly) يبقيان
// صالحَين حتى انتهائهما. الآن يُبلَّغ الخادم (/auth/logout) أفضل-جهد، والحالة تُمسَح دائماً.
describe('useAuth logout — server-side revocation (S7)', () => {
  const signedIn = () => {
    sessionStorage.setItem('sahool_access_token', 'real.jwt.token');
    sessionStorage.setItem('sahool_tenant_id', 't1');
    useAuthStore.setState({
      token: 'real.jwt.token',
      tenantId: 't1',
      user: { email: 'a@b.c', role: 'farmer', tenant_id: 't1' },
      isAuthenticated: true,
      isDemoMode: false,
    });
  };

  beforeEach(() => {
    sessionStorage.clear();
    vi.mocked(apiLogout).mockClear();
  });

  it('يستدعي /auth/logout بتوكن الجلسة ويمسح الحالة المحلّيّة', async () => {
    signedIn();
    await useAuthStore.getState().logout();

    expect(apiLogout).toHaveBeenCalledTimes(1);
    expect(apiLogout).toHaveBeenCalledWith('real.jwt.token');
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().token).toBeNull();
    expect(sessionStorage.getItem('sahool_access_token')).toBeNull();
  });

  it('فشل الخادم لا يُبقي جلسة محلّيّة ولا يرمي', async () => {
    signedIn();
    vi.mocked(apiLogout).mockRejectedValueOnce(new Error('network down'));

    await expect(useAuthStore.getState().logout()).resolves.toBeUndefined();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(sessionStorage.getItem('sahool_access_token')).toBeNull();
  });

  it('لا ينتظر الشبكة: الحالة تُمسَح قبل ردّ الخادم', () => {
    signedIn();
    vi.mocked(apiLogout).mockReturnValueOnce(new Promise(() => {})); // خادم مُعلَّق

    void useAuthStore.getState().logout();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(sessionStorage.getItem('sahool_access_token')).toBeNull();
  });

  it('وضع التجريب لا يُنادي الخادم (توكن وهميّ)', async () => {
    useAuthStore.getState().loginDemo();
    await useAuthStore.getState().logout();
    expect(apiLogout).not.toHaveBeenCalled();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
