import { describe, expect, it } from 'vitest';
import { buildZoneVraReadiness } from './fieldZoneVra';

describe('buildZoneVraReadiness', () => {
  it('blocks the whole path when no field is active', () => {
    const r = buildZoneVraReadiness({ hasField: false, imageryReadyCount: 3, prescriptionCount: 2 });
    expect(r.canBuildZones).toBe(false);
    expect(r.steps.every((s) => s.status === 'blocked')).toBe(true);
    expect(r.summary).toContain('اختر حقلاً');
  });

  it('blocks zones/action when the field has no ready imagery', () => {
    const r = buildZoneVraReadiness({ hasField: true, imageryReadyCount: 0, prescriptionCount: 0 });
    expect(r.canBuildZones).toBe(false);
    expect(r.steps.find((s) => s.key === 'field')?.status).toBe('ready');
    expect(r.steps.find((s) => s.key === 'zone')?.status).toBe('blocked');
    expect(r.steps.find((s) => s.key === 'action')?.status).toBe('blocked');
  });

  it('is ready to build zones + create a prescription with imagery and no saved rx', () => {
    const r = buildZoneVraReadiness({ hasField: true, imageryReadyCount: 4, prescriptionCount: 0 });
    expect(r.canBuildZones).toBe(true);
    expect(r.steps.find((s) => s.key === 'zone')?.status).toBe('ready');
    expect(r.steps.find((s) => s.key === 'action')?.status).toBe('ready');
  });

  it('marks the action done and exportable when prescriptions exist', () => {
    const r = buildZoneVraReadiness({ hasField: true, imageryReadyCount: 4, prescriptionCount: 3 });
    expect(r.steps.find((s) => s.key === 'action')?.status).toBe('done');
    expect(r.steps.find((s) => s.key === 'action')?.hint).toContain('3');
    expect(r.summary).toContain('مكتمل');
  });
});
