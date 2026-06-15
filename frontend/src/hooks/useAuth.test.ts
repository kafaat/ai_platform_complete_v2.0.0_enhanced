// اختبارات useAuth — تثبّت أنّ حالة المصادقة المُرطَّبة (persist) تعيش في
// sessionStorage لا localStorage، فلا يبقى isAuthenticated في تبويب جديد بلا
// توكن (التوكن نفسه session-scoped). regression لانحراف التخزين.
import { beforeEach, describe, expect, it } from 'vitest';
import { useAuthStore } from './useAuth';

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
