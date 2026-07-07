// تحقّق V65-UI — مساعِدات عرض بطاقة ذكاء الحقل (منطق نقيّ، بلا React).
// صدق: الحاضر يُعرَض بقيمته، المفقود بسببه؛ التصنيفات/النِّسَب حتميّة.

import { describe, it, expect } from 'vitest';
import {
  completenessPct,
  conditionDriverAr,
  isPresent,
  missingReasonAr,
  ndviLabelAr,
  ndviLabelTone,
  type CardSection,
} from './fieldIntelligenceCard';

describe('fieldIntelligenceCard helpers', () => {
  it('isPresent distinguishes present vs missing', () => {
    expect(isPresent({ status: 'present' } as CardSection)).toBe(true);
    expect(isPresent({ status: 'missing', reason: 'x' } as CardSection)).toBe(false);
    expect(isPresent(null)).toBe(false);
  });

  it('completenessPct clamps to 0..100', () => {
    expect(completenessPct(0.5)).toBe(50);
    expect(completenessPct(undefined)).toBe(0);
    expect(completenessPct(1.5)).toBe(100);
    expect(completenessPct(-1)).toBe(0);
  });

  it('ndviLabelAr maps GEOGLAM-style labels', () => {
    expect(ndviLabelAr('above_historical')).toContain('فوق');
    expect(ndviLabelAr('below_historical')).toContain('تحت');
    expect(ndviLabelAr('near_historical')).toContain('قرب');
    expect(ndviLabelAr(undefined)).toBe('—');
  });

  it('ndviLabelTone differs by direction', () => {
    expect(ndviLabelTone('above_historical')).not.toBe(ndviLabelTone('below_historical'));
  });

  it('missingReasonAr surfaces provider-unavailable honestly and passes unknown through', () => {
    expect(missingReasonAr('no_provider_status_supplied')).toContain('raster');
    expect(missingReasonAr('no_condition_signals')).toContain('تشخيص');
    expect(missingReasonAr('no_soil_baseline_supplied')).toContain('التربة');
    expect(missingReasonAr('some_new_reason')).toBe('some_new_reason');
    expect(missingReasonAr(undefined)).toBe('غير متاح');
  });

  it('conditionDriverAr maps drivers and passes unknown through honestly', () => {
    expect(conditionDriverAr('salinity_limited')).toContain('ملوحة');
    expect(conditionDriverAr('heat_limited')).toContain('حرارة');
    expect(conditionDriverAr('some_future_driver')).toBe('some_future_driver');
    expect(conditionDriverAr(undefined)).toBe('—');
  });
});
