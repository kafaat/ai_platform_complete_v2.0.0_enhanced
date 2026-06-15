// اختبارات تنسيق التاريخ — التسامح مع القيم الغائبة/غير الصالحة (→ «—»)
// واحترام opts المُمرَّر بدل الافتراضيّ.
import { describe, it, expect } from 'vitest';
import { fmtDateAr } from './dates';

describe('fmtDateAr', () => {
  it('يُرجِع «—» للقيم الغائبة/الفارغة', () => {
    expect(fmtDateAr()).toBe('—');
    expect(fmtDateAr(null)).toBe('—');
    expect(fmtDateAr('')).toBe('—');
  });

  it('يُرجِع «—» لتاريخ غير صالح', () => {
    expect(fmtDateAr('ليس تاريخاً')).toBe('—');
    expect(fmtDateAr('2026-13-45')).toBe('—');
  });

  it('ينسّق تاريخاً صالحاً بنصّ غير فارغ ولا يساوي «—»', () => {
    const out = fmtDateAr('2026-06-15');
    expect(out).not.toBe('—');
    expect(typeof out).toBe('string');
    expect(out.length).toBeGreaterThan(0);
  });

  it('يحترم opts المُمرَّر (إضافة السنة تُغيّر الناتج)', () => {
    const base = fmtDateAr('2026-06-15');
    const withYear = fmtDateAr('2026-06-15', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
    expect(withYear).not.toBe(base);
  });
});
