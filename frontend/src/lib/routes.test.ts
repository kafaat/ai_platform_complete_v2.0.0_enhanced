// اختبارات سجلّ المسارات — يركّز على منطق شارة النضج (Maturity) المُضاف،
// وعلى ثبات بنية المعلومات (لا فقدان قسم/عنصر)، دون تثبيت تسميات بصريّة هشّة.
import { describe, it, expect } from 'vitest';
import {
  NAV_SECTIONS,
  ALL_ROUTES,
  MATURITY_META,
  maturityBadge,
  type Maturity,
} from './routes';

describe('maturityBadge', () => {
  it('يُعيد null للأساسيّ الناضج/غير المُصنَّف (لا ضوضاء بصريّة)', () => {
    expect(maturityBadge(undefined)).toBeNull();
    expect(maturityBadge('stable')).toBeNull();
  });

  it('يُعيد بيانات عرض لـalpha/beta (تسمية + لونان)', () => {
    const beta = maturityBadge('beta');
    const alpha = maturityBadge('alpha');
    expect(beta).toEqual(MATURITY_META.beta);
    expect(alpha).toEqual(MATURITY_META.alpha);
    for (const m of [beta, alpha]) {
      expect(typeof m?.label).toBe('string');
      expect(m?.fg).toMatch(/^#/);
      expect(m?.bg).toMatch(/^#/);
    }
  });
});

describe('NAV_SECTIONS — تصنيف النضج', () => {
  it('قيم maturity (إن وُجدت) ضمن الاتّحاد المسموح فقط', () => {
    const allowed: Maturity[] = ['alpha', 'beta', 'stable'];
    for (const r of ALL_ROUTES) {
      if (r.maturity !== undefined) expect(allowed).toContain(r.maturity);
    }
  });

  it('لا شارة «جديد» العشوائيّة باقية في حقول badge (اُستبدلت بالنضج)', () => {
    expect(ALL_ROUTES.some((r) => r.badge === 'جديد')).toBe(false);
  });

  it('قسم «الذكاء المتقدّم» موجود ويُجمّع صفحات سهول الفريدة (كلّها مصنّفة نضجاً)', () => {
    const advanced = NAV_SECTIONS.find((s) => s.id === 'advanced');
    expect(advanced).toBeDefined();
    expect(advanced!.items.length).toBeGreaterThan(0);
    // كلّ عناصر القسم متقدّمة ⇒ beta أو alpha (لا stable، لا غياب تصنيف).
    for (const item of advanced!.items) {
      expect(['beta', 'alpha']).toContain(item.maturity);
    }
  });

  it('الصفحات الأساسيّة (لوحة المعلومات/الإعدادات) مصنّفة stable', () => {
    const byId = (id: string) => ALL_ROUTES.find((r) => r.id === id);
    expect(byId('dashboard')?.maturity).toBe('stable');
    expect(byId('settings')?.maturity).toBe('stable');
  });
});
