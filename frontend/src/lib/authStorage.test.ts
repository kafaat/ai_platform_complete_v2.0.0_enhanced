// اختبارات authStorage — تثبّت السلوك الصحيح وتمنع تكرار الـbug الذي كان في
// websocket.ts (قراءة التوكن من localStorage بدل sessionStorage).
import { beforeEach, describe, expect, it } from 'vitest';
import { getAccessToken, getTenantId, STORAGE_KEYS } from './authStorage';

describe('authStorage', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it('يقرأ توكن الوصول من sessionStorage', () => {
    sessionStorage.setItem(STORAGE_KEYS.accessToken, 'jwt-abc');
    expect(getAccessToken()).toBe('jwt-abc');
  });

  it('يعيد null حين لا يوجد توكن', () => {
    expect(getAccessToken()).toBeNull();
  });

  // regression للـbug: توكن موجود في localStorage فقط يجب ألّا يُقرأ — مصدر
  // الحقيقة هو sessionStorage (حيث يكتب useAuth). websocket.ts كان يقرأ
  // localStorage فيرجع فارغاً ويسقط على 'demo'.
  it('لا يقرأ التوكن من localStorage (مصدر الحقيقة sessionStorage فقط)', () => {
    localStorage.setItem(STORAGE_KEYS.accessToken, 'jwt-in-wrong-store');
    expect(getAccessToken()).toBeNull();
  });

  it('يقرأ المستأجِر من sessionStorage', () => {
    sessionStorage.setItem(STORAGE_KEYS.tenantId, 'tenant-42');
    expect(getTenantId()).toBe('tenant-42');
  });

  it("يعيد 'default' حين لا يوجد مستأجِر", () => {
    expect(getTenantId()).toBe('default');
  });
});
