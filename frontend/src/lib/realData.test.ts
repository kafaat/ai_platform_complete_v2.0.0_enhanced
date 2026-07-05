import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { isRealData, filterRealData, hasDemoData } from './realData';

describe('realData — single source of truth for the demo guard', () => {
  it('treats missing flag as real; only explicit real_data:false is demo', () => {
    expect(isRealData({})).toBe(true);
    expect(isRealData({ real_data: true })).toBe(true);
    expect(isRealData({ real_data: false })).toBe(false);
    expect(isRealData(null)).toBe(false);
    expect(isRealData(undefined)).toBe(false);
  });

  it('filterRealData drops only explicit demo rows', () => {
    const rows = [{ id: 1 }, { id: 2, real_data: false }, { id: 3, real_data: true }];
    expect(filterRealData(rows).map((r) => r.id)).toEqual([1, 3]);
    expect(filterRealData(null)).toEqual([]);
  });

  it('hasDemoData detects any demo row', () => {
    expect(hasDemoData([{ real_data: false }])).toBe(true);
    expect(hasDemoData([{}, { real_data: true }])).toBe(false);
    expect(hasDemoData(null)).toBe(false);
  });
});

// حارس: الشاشات القراريّة الحسّاسة للديمو تستعمل المصدر الموحّد (لا تُعيد تعريف القاعدة).
describe('demo-sensitive screens route the rule through lib/realData', () => {
  const screens = ['../sections/FieldRanking.tsx', '../sections/ProblemFields.tsx'];
  for (const rel of screens) {
    it(`${rel} imports and uses isRealData`, () => {
      const src = readFileSync(resolve(__dirname, rel), 'utf8');
      expect(src).toContain("from '../lib/realData'");
      expect(src).toContain('isRealData(');
    });
  }

  it('FieldRanking surfaces a demo badge when demo rows are excluded', () => {
    const src = readFileSync(resolve(__dirname, '../sections/FieldRanking.tsx'), 'utf8');
    expect(src).toContain('hasDemoData(');
    expect(src).toContain('DemoBadge');
  });
});
