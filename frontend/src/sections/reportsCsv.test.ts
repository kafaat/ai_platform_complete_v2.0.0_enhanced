import { describe, it, expect } from 'vitest';
import { buildCsv } from './ReportsPage';

// continuation-3 P2: أعمدة CSV صريحة — لا تنزاح عند اختلاف ترتيب المفاتيح أو نقص/زيادة مفتاح.
describe('buildCsv — explicit column alignment', () => {
  it('يحاذي القيَم بالأعمدة رغم اختلاف ترتيب المفاتيح بين الصفوف', () => {
    const csv = buildCsv([
      { a: 1, b: 2 },
      { b: 20, a: 10 }, // ترتيب مفاتيح معكوس
    ]);
    expect(csv).toBe('a,b\n1,2\n10,20');
  });

  it('مفتاح مفقود في صفٍّ لاحق → خليّة فارغة لا انزياح', () => {
    const csv = buildCsv([
      { a: 1, b: 2 },
      { a: 3 }, // ينقص b
    ]);
    expect(csv).toBe('a,b\n1,2\n3,');
  });

  it('مفتاح إضافيّ في صفٍّ لاحق يُضاف كعمود (اتّحاد المفاتيح)', () => {
    const csv = buildCsv([
      { a: 1 },
      { a: 2, c: 9 },
    ]);
    expect(csv).toBe('a,c\n1,\n2,9');
  });

  it('بيانات فارغة → نصّ فارغ', () => {
    expect(buildCsv([])).toBe('');
  });
});
