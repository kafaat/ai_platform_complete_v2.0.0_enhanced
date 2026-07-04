import { describe, expect, it } from 'vitest';
import { summarizeScouting } from './fieldScouting';

describe('summarizeScouting', () => {
  it('is an explicit empty state without a crop', () => {
    const s = summarizeScouting(null, []);
    expect(s.hasCrop).toBe(false);
    expect(s.total).toBe(0);
    expect(s.groups).toEqual([]);
  });

  it('groups issues by category and orders disease/pest first', () => {
    const s = summarizeScouting('wheat', [
      { code: 'wheat.weed1', category: 'weed', name_ar: 'أعشاب' },
      { code: 'wheat.rust', category: 'disease', name_ar: 'صدأ القمح' },
      { code: 'wheat.aphid', category: 'pest', name_ar: 'منّ' },
      { code: 'wheat.rot', category: 'disease', name_ar: 'تعفّن' },
    ]);
    expect(s.hasCrop).toBe(true);
    expect(s.total).toBe(4);
    expect(s.groups.map((g) => g.category)).toEqual(['disease', 'pest', 'weed']);
    expect(s.groups[0].label).toBe('أمراض');
    expect(s.groups[0].items).toHaveLength(2);
  });

  it('labels unknown categories by their raw key and sorts them last', () => {
    const s = summarizeScouting('corn', [
      { code: 'x', category: 'mystery', name_ar: 'شيء' },
      { code: 'y', category: 'pest', name_ar: 'آفة' },
    ]);
    expect(s.groups[0].category).toBe('pest');
    expect(s.groups[1].category).toBe('mystery');
    expect(s.groups[1].label).toBe('mystery');
  });
});
