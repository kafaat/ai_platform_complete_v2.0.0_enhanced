import { describe, expect, it } from 'vitest';
import { classifyZoneLabel, precisionAgricultureEndpoints } from './precisionAgriculture';

describe('precisionAgriculture contracts', () => {
  it('publishes Phase 6 endpoint contracts', () => {
    expect(precisionAgricultureEndpoints.boundaryExtract).toContain('/phase6/boundaries/extract');
    expect(precisionAgricultureEndpoints.digitalTwinSnapshot).toContain('/digital-twin/snapshot');
  });

  it('classifies zone labels for UI badges', () => {
    expect(classifyZoneLabel('stress')).toBe('stress');
    expect(classifyZoneLabel('high_potential')).toBe('high');
    expect(classifyZoneLabel('unknown')).toBe('other');
  });
});
