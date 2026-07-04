import { describe, expect, it } from 'vitest';
import { groupRanked, monthOfIso, ratingColor, type RotationSuggestResponse } from './plantingAdvisor';

const cand = (candidate: string, rating: string): RotationSuggestResponse['ranked'] extends (infer T)[] | undefined ? T : never => ({
  previous_crop: 'القمح',
  candidate_crop: candidate,
  rating,
  rating_ar: rating === 'good' ? 'جيّد' : rating === 'acceptable' ? 'مقبول' : 'تجنّب',
  reasons_ar: ['سبب'],
});

describe('groupRanked — server ratings as-is', () => {
  it('groups good/acceptable/avoid and ignores unknown ratings honestly', () => {
    const g = groupRanked({
      supported: true,
      ranked: [cand('عدس', 'good'), cand('ذرة', 'acceptable'), cand('قمح', 'avoid'), cand('غريب', 'mystery')],
    });
    expect(g.good.map((c) => c.candidate_crop)).toEqual(['عدس']);
    expect(g.acceptable).toHaveLength(1);
    expect(g.avoid).toHaveLength(1);
  });
  it('is empty for unsupported/missing responses', () => {
    expect(groupRanked({ supported: false, message_ar: 'غير معروف' }).good).toEqual([]);
    expect(groupRanked(null).avoid).toEqual([]);
  });
});

describe('ratingColor + monthOfIso', () => {
  it('colors by server rating with neutral fallback', () => {
    expect(ratingColor('good')).toBe('#86efac');
    expect(ratingColor('avoid')).toBe('#fca5a5');
    expect(ratingColor('weird')).toBe('#64748b');
  });
  it('parses month from ISO honestly', () => {
    expect(monthOfIso('2026-07-04')).toBe(7);
    expect(monthOfIso('2026-13-04')).toBeNull();
    expect(monthOfIso(null)).toBeNull();
    expect(monthOfIso('garbage')).toBeNull();
  });
});
