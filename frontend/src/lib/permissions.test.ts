// اختبارات permissions — تغطّي RBAC fail-closed وحدود الأدوار في الواجهة،
// تستورد الكود الفعليّ (lib/permissions) لكشف أيّ انحراف مستقبليّ.
import { describe, expect, it } from 'vitest';
import {
  canAccess,
  canCreateFarm,
  canManage,
  canMutate,
  normalizeRole,
} from './permissions';

describe('normalizeRole — fail-closed', () => {
  it('الدور المجهول/الفارغ → viewer (أقلّ صلاحيّة)', () => {
    expect(normalizeRole(undefined)).toBe('viewer');
    expect(normalizeRole(null)).toBe('viewer');
    expect(normalizeRole('')).toBe('viewer');
    expect(normalizeRole('superhacker')).toBe('viewer');
  });

  it('يطبّع المرادفات والأسماء القديمة', () => {
    expect(normalizeRole('admin')).toBe('owner');
    expect(normalizeRole('farmer')).toBe('worker');
    expect(normalizeRole('expert')).toBe('agronomist');
    expect(normalizeRole('OWNER')).toBe('owner'); // غير حسّاس لحالة الأحرف
  });
});

describe('canMutate / canManage / canCreateFarm', () => {
  it('viewer قراءة فقط (لا تعديل)', () => {
    expect(canMutate('viewer')).toBe(false);
    expect(canMutate('worker')).toBe(true);
    expect(canMutate('owner')).toBe(true);
  });

  it('الإدارة الحسّاسة: owner/manager فقط', () => {
    expect(canManage('owner')).toBe(true);
    expect(canManage('manager')).toBe(true);
    expect(canManage('agronomist')).toBe(false);
    expect(canManage('worker')).toBe(false);
    expect(canManage('viewer')).toBe(false);
  });

  it('إنشاء مزرعة: owner فقط (يطابق RBAC الخلفيّة)', () => {
    expect(canCreateFarm('owner')).toBe(true);
    expect(canCreateFarm('manager')).toBe(false);
    expect(canCreateFarm('agronomist')).toBe(false);
    expect(canCreateFarm(undefined)).toBe(false);
  });
});

describe('canAccess — حدود الصفحات', () => {
  it('الصفحات الإداريّة لا تظهر لغير owner/manager', () => {
    for (const page of ['master-data', 'documents', 'governance'] as const) {
      expect(canAccess('owner', page)).toBe(true);
      expect(canAccess('manager', page)).toBe(true);
      expect(canAccess('agronomist', page)).toBe(false);
      expect(canAccess('worker', page)).toBe(false);
      expect(canAccess('viewer', page)).toBe(false);
    }
  });

  it('worker يصل لصفحاته التشغيليّة لا الإداريّة', () => {
    expect(canAccess('worker', 'dashboard')).toBe(true);
    expect(canAccess('worker', 'tasks')).toBe(true);
    expect(canAccess('worker', 'master-data')).toBe(false);
  });

  it('الدور المجهول (viewer) لا يصل للصفحات الإداريّة', () => {
    expect(canAccess('???', 'governance')).toBe(false);
    expect(canAccess('???', 'dashboard')).toBe(true);
  });
});
