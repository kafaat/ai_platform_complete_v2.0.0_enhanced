// اختبارات RBAC الواجهة — تتحقّق من سياسة الوصول/التعديل/الإدارة كما تُطبَّق فعلاً
// (fail-closed: المجهول = viewer)، وحدود الأدوار الموثّقة.
import { describe, it, expect } from 'vitest';
import {
  normalizeRole,
  canAccess,
  canMutate,
  canManage,
  canCreateFarm,
  ROLE_LABEL_AR,
} from './permissions';

describe('normalizeRole', () => {
  it('يطبّع المرادفات إلى الأدوار الخمسة المعتمدة', () => {
    expect(normalizeRole('admin')).toBe('owner');
    expect(normalizeRole('expert')).toBe('agronomist');
    expect(normalizeRole('farmer')).toBe('worker');
    expect(normalizeRole('MANAGER')).toBe('manager'); // غير حسّاس لحالة الأحرف
  });

  it('fail-closed: المجهول/الفارغ/null → viewer', () => {
    expect(normalizeRole(undefined)).toBe('viewer');
    expect(normalizeRole(null)).toBe('viewer');
    expect(normalizeRole('')).toBe('viewer');
    expect(normalizeRole('superuser')).toBe('viewer');
  });
});

describe('canAccess', () => {
  it('owner/manager يصلان للصفحات الإداريّة', () => {
    expect(canAccess('owner', 'master-data')).toBe(true);
    expect(canAccess('manager', 'governance')).toBe(true);
  });

  it('agronomist/viewer يُمنعان من الصفحات الإداريّة لكن يصلان للتشغيليّة', () => {
    expect(canAccess('agronomist', 'master-data')).toBe(false);
    expect(canAccess('agronomist', 'documents')).toBe(false);
    expect(canAccess('agronomist', 'dashboard')).toBe(true);
    expect(canAccess('viewer', 'governance')).toBe(false);
    expect(canAccess('viewer', 'satellite')).toBe(true);
  });

  it('worker لا يصل للصفحات الإداريّة ولا للتقارير/التحليلات خارج نطاقه', () => {
    expect(canAccess('worker', 'master-data')).toBe(false);
    expect(canAccess('worker', 'reports')).toBe(false);
    expect(canAccess('worker', 'analytics')).toBe(false);
    // لكنّه يصل للصفحات التشغيليّة
    expect(canAccess('worker', 'tasks')).toBe(true);
    expect(canAccess('worker', 'irrigation')).toBe(true);
  });

  it('الدور المجهول يُعامَل كـviewer (fail-closed)', () => {
    expect(canAccess(undefined, 'master-data')).toBe(false);
    expect(canAccess(undefined, 'dashboard')).toBe(true);
  });
});

describe('canMutate / canManage / canCreateFarm', () => {
  it('viewer قراءة فقط؛ بقيّة الأدوار تعدّل', () => {
    expect(canMutate('viewer')).toBe(false);
    expect(canMutate(undefined)).toBe(false); // fail-closed → viewer
    expect(canMutate('worker')).toBe(true);
    expect(canMutate('agronomist')).toBe(true);
    expect(canMutate('owner')).toBe(true);
  });

  it('canManage: owner/manager فقط', () => {
    expect(canManage('owner')).toBe(true);
    expect(canManage('admin')).toBe(true); // مرادف owner
    expect(canManage('manager')).toBe(true);
    expect(canManage('agronomist')).toBe(false);
    expect(canManage('worker')).toBe(false);
    expect(canManage('viewer')).toBe(false);
  });

  it('canCreateFarm: owner فقط (يطابق RBAC الخلفيّة)', () => {
    expect(canCreateFarm('owner')).toBe(true);
    expect(canCreateFarm('admin')).toBe(true);
    expect(canCreateFarm('manager')).toBe(false);
    expect(canCreateFarm('agronomist')).toBe(false);
    expect(canCreateFarm(undefined)).toBe(false);
  });
});

describe('ROLE_LABEL_AR', () => {
  it('يوفّر تسمية عربيّة لكلّ دور من الأدوار الخمسة', () => {
    expect(ROLE_LABEL_AR.owner).toBe('مالك');
    expect(ROLE_LABEL_AR.viewer).toBe('مُشاهِد');
    expect(Object.keys(ROLE_LABEL_AR).sort()).toEqual(
      ['agronomist', 'manager', 'owner', 'viewer', 'worker'],
    );
  });
});
