import { describe, expect, it } from 'vitest';
import { num } from './MyFieldsPage';

// حارس انحدار: عمود NDVI في «حقولي» كان يعرض «0.00» لحقل بلا مؤشّر محسوب،
// لأنّ Number('') يساوي 0 لا NaN — فقيمة غائبة تتحوّل صفراً مضلِّلاً. هذه
// الاختبارات تثبّت أنّ الغائب/الفارغ ⇒ null (يُعرَض «—») وأنّ الصفر الحقيقيّ يبقى 0.
describe('MyFieldsPage num() — مؤشّر غائب ≠ صفر', () => {
  it('returns null for missing values (undefined/null/empty) — لا صفر مضلِّل', () => {
    expect(num(undefined)).toBeNull();
    expect(num(null)).toBeNull();
    expect(num('')).toBeNull();
    expect(num('   ')).toBeNull();
  });

  it('preserves a genuine zero (NDVI=0 قراءة حقيقيّة)', () => {
    expect(num(0)).toBe(0);
    expect(num('0')).toBe(0);
    expect(num('0.00')).toBe(0);
  });

  it('parses real numeric values (number or string)', () => {
    expect(num(0.72)).toBeCloseTo(0.72);
    expect(num('115.5')).toBeCloseTo(115.5);
  });

  it('returns null for non-numeric junk and non-finite', () => {
    expect(num('abc')).toBeNull();
    expect(num(Number.NaN)).toBeNull();
    expect(num(Infinity)).toBeNull();
  });
});
