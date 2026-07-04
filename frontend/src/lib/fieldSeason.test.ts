import { describe, expect, it } from 'vitest';
import { summarizeSeason } from './fieldSeason';

describe('summarizeSeason', () => {
  it('is unavailable with an honest reason when the endpoint says so', () => {
    const s = summarizeSeason({ available: false, reason_ar: 'لا يوجد تاريخ بذار للموسم النشط', crop: 'قمح' });
    expect(s.available).toBe(false);
    expect(s.reason).toContain('بذار');
    expect(s.crop).toBe('قمح');
    expect(s.stageName).toBeNull();
  });

  it('returns an empty summary for null input (no fabrication)', () => {
    const s = summarizeSeason(null);
    expect(s.available).toBe(false);
    expect(s.progressPct).toBeNull();
    expect(s.stages).toEqual([]);
  });

  it('computes stage, progress and next stage from a live timeline', () => {
    const s = summarizeSeason({
      available: true,
      crop: 'قمح',
      days_after_sowing: 60,
      current_stage_kc: 1.15,
      current_stage: { name_ar: 'التطوّر' },
      timeline: [
        { name_ar: 'الإنبات', day_start: 0, day_end: 20, status: 'past' },
        { name_ar: 'التطوّر', day_start: 20, day_end: 80, status: 'current' },
        { name_ar: 'منتصف الموسم', day_start: 80, day_end: 120, status: 'upcoming' },
      ],
    });
    expect(s.available).toBe(true);
    expect(s.stageName).toBe('التطوّر');
    expect(s.kc).toBe(1.15);
    expect(s.progressPct).toBe(50); // 60 / 120
    expect(s.nextStageName).toBe('منتصف الموسم');
    expect(s.stages).toHaveLength(3);
  });
});
