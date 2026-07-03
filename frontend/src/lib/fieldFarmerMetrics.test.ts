import { describe, expect, it } from 'vitest';
import { buildFarmerMetrics, worstFarmerStatus } from './fieldFarmerMetrics';

describe('buildFarmerMetrics', () => {
  it('derives four metrics from real signals with documented thresholds', () => {
    const m = buildFarmerMetrics({
      ndvi: 0.72,
      soilMoisturePct: 40,
      nitrogenStatus: 'adequate',
      weather: { tempMaxC: 30, windMs: 3, rainMm: 0 },
    });
    expect(m.map((x) => x.key)).toEqual(['health', 'water', 'nutrition', 'weather']);
    expect(m[0].status).toBe('good');
    expect(m[0].value).toContain('0.72');
    expect(m[1].status).toBe('good');
    expect(m[2].status).toBe('good');
    expect(m[3].status).toBe('good');
    expect(worstFarmerStatus(m)).toBe('good');
  });

  it('marks missing signals as unknown (no fabricated values)', () => {
    const m = buildFarmerMetrics({});
    expect(m.every((x) => x.status === 'unknown')).toBe(true);
    expect(m.every((x) => x.value === '—')).toBe(true);
    expect(worstFarmerStatus(m)).toBe('unknown');
  });

  it('flags low NDVI, dry soil, N deficit, and multi-risk weather', () => {
    const m = buildFarmerMetrics({
      ndvi: 0.2,
      soilMoisturePct: 12,
      nitrogenStatus: 'deficit',
      weather: { tempMaxC: 44, windMs: 12, rainMm: 0 },
    });
    expect(m[0].status).toBe('risk');
    expect(m[1].status).toBe('risk');
    expect(m[2].status).toBe('risk');
    expect(m[3].status).toBe('risk');
    expect(worstFarmerStatus(m)).toBe('risk');
  });

  it('treats a single weather risk as watch, two as risk', () => {
    expect(buildFarmerMetrics({ weather: { tempMaxC: 43, windMs: 2, rainMm: 0 } })[3].status).toBe('watch');
    expect(buildFarmerMetrics({ weather: { tempMaxC: 43, windMs: 11, rainMm: 0 } })[3].status).toBe('risk');
  });
});
