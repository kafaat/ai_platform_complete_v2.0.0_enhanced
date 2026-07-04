import { describe, expect, it } from 'vitest';
import {
  buildPlantingPayload,
  buildRainfallPayload,
  buildTemperaturePayload,
  buildWaterTwinPayload,
  cropKeyFromLabel,
  fmtDelta,
  fmtNum,
  mmToCubicMeters,
} from './whatIfScenarios';

describe('buildTemperaturePayload — WhatIfTempRequest strict validation', () => {
  const base = { crop: 'wheat', stage: 'mid', tMinC: '12', tMaxC: '28', tempShiftC: '2' };
  it('builds server-shaped payload; server defaults (lat/elev/doy) omitted when not entered', () => {
    const r = buildTemperaturePayload({ ...base, rainMm: '5' });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.payload).toEqual({
        crop: 'wheat', stage: 'mid', t_min_c: 12, t_max_c: 28, temp_shift_c: 2, rain_mm: 5,
      });
      expect('latitude_deg' in r.payload).toBe(false); // لا نكرّر افتراضات الخادم محلّيّاً
    }
  });
  it('rejects inverted temps, zero shift, and bad optional site fields with Arabic reasons', () => {
    expect(buildTemperaturePayload({ ...base, tMinC: '30', tMaxC: '20' })).toMatchObject({ ok: false, error: expect.stringContaining('أعلى من القصوى') });
    expect(buildTemperaturePayload({ ...base, tempShiftC: 0 })).toMatchObject({ ok: false, error: expect.stringContaining('لا سيناريو') });
    expect(buildTemperaturePayload({ ...base, latitudeDeg: '120' }).ok).toBe(false);
    expect(buildTemperaturePayload({ ...base, stage: 'bogus' }).ok).toBe(false);
  });
});

describe('buildRainfallPayload — WhatIfRainRequest', () => {
  const base = { crop: 'sorghum', stage: 'development', tMinC: 15, tMaxC: 32, rainBaselineMm: '40', rainScenarioMm: '20' };
  it('builds payload with baseline/scenario rain', () => {
    const r = buildRainfallPayload(base);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.payload).toEqual({
        crop: 'sorghum', stage: 'development', t_min_c: 15, t_max_c: 32,
        rain_baseline_mm: 40, rain_scenario_mm: 20,
      });
    }
  });
  it('rejects negative rain and identical baseline/scenario (no fabricated delta)', () => {
    expect(buildRainfallPayload({ ...base, rainScenarioMm: '-3' })).toMatchObject({ ok: false, error: expect.stringContaining('سالباً') });
    expect(buildRainfallPayload({ ...base, rainScenarioMm: '40' })).toMatchObject({ ok: false, error: expect.stringContaining('متساويتان') });
  });
});

describe('buildPlantingPayload — WhatIfPlantingRequest (GDD crops only)', () => {
  const base = { crop: 'wheat', horizonDays: '30', baselineTMinC: '10', baselineTMaxC: '24', scenarioTMinC: '14', scenarioTMaxC: '29' };
  it('expands declared constant assumption into daily series of the requested length', () => {
    const r = buildPlantingPayload(base);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.payload.crop).toBe('wheat');
      expect(r.payload.temps_baseline).toHaveLength(30);
      expect(r.payload.temps_scenario).toHaveLength(30);
      expect(r.payload.temps_baseline[0]).toEqual({ t_min_c: 10, t_max_c: 24 });
      expect(r.payload.temps_scenario[29]).toEqual({ t_min_c: 14, t_max_c: 29 });
    }
  });
  it('rejects crops the server would 422 on, and out-of-range horizons', () => {
    expect(buildPlantingPayload({ ...base, crop: 'dates' })).toMatchObject({ ok: false, error: expect.stringContaining('غير مدعوم') });
    expect(buildPlantingPayload({ ...base, horizonDays: '0' }).ok).toBe(false);
    expect(buildPlantingPayload({ ...base, horizonDays: '400' }).ok).toBe(false);
  });
});

describe('buildWaterTwinPayload — WaterTwinRequest (delay/scale transforms)', () => {
  const base = {
    tawMm: '120', rawMm: '66', initialDepletionMm: '20', horizonDays: '10',
    dailyEtcMm: '6', dailyRainMm: '0', irrigationDepthMm: '30', irrigationIntervalDays: '5',
  };
  it('builds delay payload with irrigation every K days in the baseline schedule', () => {
    const r = buildWaterTwinPayload({ ...base, kind: 'delay', delayDays: '3' });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.payload).toMatchObject({ taw_mm: 120, raw_mm: 66, initial_depletion_mm: 20, scenario_kind: 'delay', delay_days: 3 });
      expect(r.payload.days).toHaveLength(10);
      const irrigated = r.payload.days.map((d, i) => (d.irrigation_mm > 0 ? i + 1 : null)).filter(Boolean);
      expect(irrigated).toEqual([5, 10]); // ريّة كلّ ٥ أيّام
      expect(r.payload.days[0]).toEqual({ etc_mm: 6, rain_mm: 0, irrigation_mm: 0 });
      expect('scale_factor' in r.payload).toBe(false);
    }
  });
  it('builds scale payload; rejects the no-op factor 1.0 and soil state the server would 422 on', () => {
    const r = buildWaterTwinPayload({ ...base, kind: 'scale', scaleFactor: '0.8' });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.payload).toMatchObject({ scenario_kind: 'scale', scale_factor: 0.8 });
    expect(buildWaterTwinPayload({ ...base, kind: 'scale', scaleFactor: '1' })).toMatchObject({ ok: false, error: expect.stringContaining('لا يغيّر') });
    expect(buildWaterTwinPayload({ ...base, kind: 'delay', delayDays: 2, rawMm: '200' })).toMatchObject({ ok: false, error: expect.stringContaining('TAW') });
    expect(buildWaterTwinPayload({ ...base, kind: 'delay', delayDays: 2, initialDepletionMm: '500' }).ok).toBe(false);
  });
});

describe('honest display helpers', () => {
  it('fmtNum/fmtDelta render missing as «—» (no fabricated zero); mm→m³ needs a real area', () => {
    expect(fmtNum(null)).toBe('—');
    expect(fmtNum(undefined)).toBe('—');
    expect(fmtNum(3.456)).toBe('3.46');
    expect(fmtDelta(2.5)).toBe('+2.5');
    expect(fmtDelta(-1.25)).toBe('-1.25');
    expect(fmtDelta(null)).toBe('—');
    expect(mmToCubicMeters(30, 2)).toBe(600); // 30مم × 2هكتار = 600 م³ — تحويل حتميّ
    expect(mmToCubicMeters(30, null)).toBeNull(); // لا مساحة ⇒ لا تخمين
    expect(mmToCubicMeters(null, 2)).toBeNull();
  });
  it('cropKeyFromLabel maps Arabic field labels without guessing unknowns', () => {
    expect(cropKeyFromLabel('قمح صلب')).toBe('wheat');
    expect(cropKeyFromLabel('ذرة رفيعة بيضاء')).toBe('sorghum');
    expect(cropKeyFromLabel('ذرة شاميّة')).toBe('maize');
    expect(cropKeyFromLabel('مانجو')).toBeNull();
    expect(cropKeyFromLabel(null)).toBeNull();
  });
});
