import { describe, expect, it } from 'vitest';
import {
  buildCoffeeSiteParams,
  buildGerminationParams,
  buildMoistureCheckParams,
  buildSowingDepthParams,
  buildStorageCheckParams,
  coffeeRatingColor,
  moistureStatusColor,
} from './agroCalculators';

describe('buildGerminationParams — عدّ عيّنة إنبات', () => {
  it('builds integer counts and keeps them verbatim', () => {
    const r = buildGerminationParams({ sprouted: '86', total: '100' });
    expect(r).toEqual({ ok: true, payload: { sprouted: 86, total: 100 } });
  });
  it('rejects sprouted > total, negatives, non-integers and empties with Arabic reasons', () => {
    expect(buildGerminationParams({ sprouted: 101, total: 100 })).toMatchObject({ ok: false, error: expect.stringContaining('يتجاوز') });
    expect(buildGerminationParams({ sprouted: -1, total: 100 }).ok).toBe(false);
    expect(buildGerminationParams({ sprouted: 5.5, total: 100 })).toMatchObject({ ok: false, error: expect.stringContaining('صحيحة') });
    expect(buildGerminationParams({ sprouted: 10, total: 0 }).ok).toBe(false);
    expect(buildGerminationParams({ sprouted: '', total: '100' })).toMatchObject({ ok: false, error: expect.stringContaining('مطلوب') });
  });
});

describe('buildStorageCheckParams — قاعدة المئة (°م تُحوَّل إلى °ف للخادم)', () => {
  it('converts Celsius to Fahrenheit for the server rule', () => {
    const r = buildStorageCheckParams({ tempC: 20, humidityPct: '45' });
    expect(r).toEqual({ ok: true, payload: { temp_f: 68, humidity_pct: 45 } });
  });
  it('rejects out-of-range humidity and unreal temperatures', () => {
    expect(buildStorageCheckParams({ tempC: 20, humidityPct: 120 })).toMatchObject({ ok: false, error: expect.stringContaining('100') });
    expect(buildStorageCheckParams({ tempC: 200, humidityPct: 40 }).ok).toBe(false);
    expect(buildStorageCheckParams({ tempC: 'abc', humidityPct: 40 }).ok).toBe(false);
  });
});

describe('buildSowingDepthParams — عمق البذر', () => {
  it('accepts a positive seed size and defaults precision to false', () => {
    const r = buildSowingDepthParams({ seedSizeMm: '4.5' });
    expect(r).toEqual({ ok: true, payload: { seed_size_mm: 4.5, precision: false } });
  });
  it('rejects zero/negative/unreal sizes instead of silently sending them', () => {
    expect(buildSowingDepthParams({ seedSizeMm: 0 })).toMatchObject({ ok: false, error: expect.stringContaining('موجب') });
    expect(buildSowingDepthParams({ seedSizeMm: -3 }).ok).toBe(false);
    expect(buildSowingDepthParams({ seedSizeMm: 500 }).ok).toBe(false);
  });
});

describe('buildMoistureCheckParams — رطوبة الحبوب قبل التخزين', () => {
  it('trims the crop name and keeps measured moisture', () => {
    const r = buildMoistureCheckParams({ crop: ' قمح ', moisturePct: '11.5' });
    expect(r).toEqual({ ok: true, payload: { crop: 'قمح', moisture_pct: 11.5 } });
  });
  it('rejects missing crop and impossible moisture', () => {
    expect(buildMoistureCheckParams({ crop: '  ', moisturePct: 12 })).toMatchObject({ ok: false, error: expect.stringContaining('المحصول') });
    expect(buildMoistureCheckParams({ crop: 'قمح', moisturePct: 0 }).ok).toBe(false);
    expect(buildMoistureCheckParams({ crop: 'قمح', moisturePct: 101 }).ok).toBe(false);
  });
});

describe('buildCoffeeSiteParams — ارتفاع موقع البنّ', () => {
  it('accepts a realistic Yemeni highland altitude', () => {
    expect(buildCoffeeSiteParams({ altitudeM: 1800 })).toEqual({ ok: true, payload: { altitude_m: 1800 } });
  });
  it('rejects negative or impossible altitudes', () => {
    expect(buildCoffeeSiteParams({ altitudeM: -5 })).toMatchObject({ ok: false, error: expect.stringContaining('سالب') });
    expect(buildCoffeeSiteParams({ altitudeM: 9000 }).ok).toBe(false);
    expect(buildCoffeeSiteParams({ altitudeM: '' }).ok).toBe(false);
  });
});

describe('status colors — honest mapping (known server statuses only)', () => {
  it('colors known statuses and returns null for unknown ones', () => {
    expect(moistureStatusColor('safe')).toBe('#86efac');
    expect(moistureStatusColor('unsafe')).toBe('#fca5a5');
    expect(moistureStatusColor('weird-new-status')).toBeNull();
    expect(moistureStatusColor(undefined)).toBeNull();
    expect(coffeeRatingColor('optimal')).toBe('#86efac');
    expect(coffeeRatingColor('marginal')).toBe('#fdba74');
    expect(coffeeRatingColor('unknown')).toBeNull();
  });
});
