import { describe, expect, it } from 'vitest';

import { captureTime } from './captureTime';

describe('captureTime — وقت الالتقاط لا يُحوَّل ولا يُختلَق', () => {
  it('طابع UTC ⇒ ساعة موسومة صراحةً بـUTC', () => {
    const t = captureTime('2026-08-04T10:37:21.000Z', '2026-08-04');
    expect(t.label).toBe('10:37 UTC');
    expect(t.isoDate).toBe('2026-08-04');
    expect(t.mismatch).toBe(false);
  });

  it('غياب الطابع ⇒ لا ساعة (البطاقة تعرض التاريخ وحده)', () => {
    expect(captureTime(null, '2026-08-04').label).toBeNull();
    expect(captureTime(undefined, '2026-08-04').label).toBeNull();
    expect(captureTime('', '2026-08-04').label).toBeNull();
  });

  it('نصّ غير صالح ⇒ لا يُخترَع منه شيء', () => {
    expect(captureTime('not-a-date', '2026-08-04')).toEqual({
      label: null,
      isoDate: null,
      mismatch: false,
    });
  });

  it('طابع بلا منطقة زمنيّة ليس UTC مُثبَتاً ⇒ تاريخ بلا ادّعاء ساعة', () => {
    const t = captureTime('2026-08-04T10:37:21', '2026-08-04');
    expect(t.label).toBeNull();
    expect(t.isoDate).toBe('2026-08-04');
  });

  it('الساعة لا تنزلق مع توقيت المتصفّح — وهو العطل الذي يخفيه خادم UTC', () => {
    // 23:40Z يقع في اليوم التالي بتوقيت +03:00 وفي اليوم نفسه بـUTC. القراءة النصّيّة
    // تُعطي القيمة نفسها تحت أيّ TZ، بخلاف getHours() على كائن Date.
    const t = captureTime('2026-08-04T23:40:00Z', '2026-08-04');
    expect(t.label).toBe('23:40 UTC');
    expect(t.isoDate).toBe('2026-08-04');
    expect(t.mismatch).toBe(false);
  });

  it('تناقض التاريخ يُعلَن ولا يُبتلَع', () => {
    // البطاقة تقول 2026-08-04 والشاهد يقول 2026-08-03 ⇒ التاريخ اشتُقّ من مصدر آخر.
    const t = captureTime('2026-08-03T21:40:00Z', '2026-08-04');
    expect(t.isoDate).toBe('2026-08-03');
    expect(t.mismatch).toBe(true);
  });

  it('بلا تاريخ بطاقة ⇒ لا ادّعاء تناقض', () => {
    expect(captureTime('2026-08-03T21:40:00Z').mismatch).toBe(false);
    expect(captureTime('2026-08-03T21:40:00Z', null).mismatch).toBe(false);
  });

  it('إزاحة غير صفريّة ⇒ لا وسم UTC كاذب', () => {
    const t = captureTime('2026-08-04T13:37:00+03:00', '2026-08-04');
    expect(t.label).toBeNull();
    expect(t.isoDate).toBe('2026-08-04');
  });
});
