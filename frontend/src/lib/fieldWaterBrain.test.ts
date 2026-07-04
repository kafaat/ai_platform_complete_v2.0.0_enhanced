import { describe, expect, it } from 'vitest';
import { evaluateWaterBrain } from './fieldWaterBrain';

describe('evaluateWaterBrain', () => {
  it('is unknown and defers to the water twin without a moisture reading', () => {
    const r = evaluateWaterBrain({ forecastRainMm: 0, tempMaxC: 38 });
    expect(r.decision).toBe('unknown');
    expect(r.confidence).toBe(0);
    expect(r.reason).toContain('التوأم المائيّ');
  });

  it('irrigates now on low moisture with no rain', () => {
    const r = evaluateWaterBrain({ soilMoisturePct: 15, forecastRainMm: 0, tempMaxC: 30 });
    expect(r.decision).toBe('irrigate_now');
    expect(r.confidence).toBe(90);
  });

  it('defers when significant rain is forecast even if soil is dry', () => {
    const r = evaluateWaterBrain({ soilMoisturePct: 12, forecastRainMm: 18, tempMaxC: 35 });
    expect(r.decision).toBe('defer');
    expect(r.reason).toContain('مطر');
  });

  it('defers on adequate moisture', () => {
    expect(evaluateWaterBrain({ soilMoisturePct: 42, forecastRainMm: 0 }).decision).toBe('defer');
  });

  it('brings irrigation forward when mid-moisture meets high heat', () => {
    expect(evaluateWaterBrain({ soilMoisturePct: 28, forecastRainMm: 0, tempMaxC: 30 }).decision).toBe('soon');
    expect(evaluateWaterBrain({ soilMoisturePct: 28, forecastRainMm: 0, tempMaxC: 43 }).decision).toBe('irrigate_now');
  });
});
