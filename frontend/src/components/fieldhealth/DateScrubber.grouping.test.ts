import { describe, expect, it } from 'vitest';
import { groupPointsByMonth } from './DateScrubber';
import type { ScrubberPoint } from './DateScrubber';

// يبني سلسلة ~سنتين بإعادة زيارة ٥ أيّام (يحاكي Sentinel-2) لاختبار التجميع.
function twoYearSeries(n: number): ScrubberPoint[] {
  const out: ScrubberPoint[] = [];
  const start = new Date('2024-06-01T00:00:00Z').getTime();
  for (let i = 0; i < n; i++) {
    const d = new Date(start + i * 5 * 86400000).toISOString().slice(0, 10);
    out.push({ date: d, value: 0.5, cloud: (i * 37) % 100 });
  }
  return out;
}

describe('groupPointsByMonth', () => {
  it('يقلّص سلسلة سنتين (~146) إلى ممثّل شهريّ واحد لكلّ شهر', () => {
    const pts = twoYearSeries(146);
    const grouped = groupPointsByMonth(pts);
    // سنتان ≈ 24-25 شهراً — أقلّ بكثير من 146.
    expect(grouped.length).toBeLessThan(30);
    expect(grouped.length).toBeGreaterThan(20);
    // لا تكرار شهر.
    const months = grouped.map((p) => p.date.slice(0, 7));
    expect(new Set(months).size).toBe(months.length);
  });

  it('يختار الأقلّ غيوماً ممثّلاً لكلّ شهر', () => {
    const pts: ScrubberPoint[] = [
      { date: '2025-03-02', value: 0.4, cloud: 80 },
      { date: '2025-03-12', value: 0.5, cloud: 10 }, // الأوضح
      { date: '2025-03-22', value: 0.6, cloud: 55 },
    ];
    const grouped = groupPointsByMonth(pts);
    expect(grouped).toHaveLength(1);
    expect(grouped[0].date).toBe('2025-03-12');
    expect(grouped[0].cloud).toBe(10);
  });

  it('يُرجِع الممثّلين مفروزين تصاعديّاً زمنيّاً', () => {
    const pts = twoYearSeries(146);
    const grouped = groupPointsByMonth(pts);
    const dates = grouped.map((p) => p.date);
    const sorted = [...dates].sort();
    expect(dates).toEqual(sorted);
  });

  it('cloud=null يُعامَل كأسوأ (لا يُختار ما لم يوجد بديل)', () => {
    const pts: ScrubberPoint[] = [
      { date: '2025-05-04', value: 0.4, cloud: null },
      { date: '2025-05-14', value: 0.5, cloud: 30 }, // يُفضَّل
    ];
    const grouped = groupPointsByMonth(pts);
    expect(grouped[0].date).toBe('2025-05-14');
  });

  it('يتجاهل النقاط بلا تاريخ صالح', () => {
    const pts: ScrubberPoint[] = [
      { date: '', value: 0.4, cloud: 10 },
      { date: '2025-07-09', value: 0.5, cloud: 20 },
    ];
    const grouped = groupPointsByMonth(pts);
    expect(grouped).toHaveLength(1);
    expect(grouped[0].date).toBe('2025-07-09');
  });
});
