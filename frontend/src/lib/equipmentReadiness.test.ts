import { describe, expect, it } from 'vitest';
import { readEquipmentReadiness as read } from './equipmentReadiness';

function fixture() {
  return {
    assets: [{ equipment_id: 'pump-a', name: 'Pump A' }],
    intelligence: {
      schema_version: 'equipment_intelligence.v2', readiness: 'unknown', total_assets: 1,
      unavailable: 0, assessment_coverage: 0, service_due: 0, service_not_due: 0,
      service_not_evaluated: 1,
      assessments: [{ asset_id: 'pump-a', status: 'not_evaluated', basis: null as string | null,
        constraints: ['maintenance_policy_missing'] }],
    },
  };
}

describe('server-owned equipment assessment', () => {
  it('preserves missing policy as unknown', () => {
    expect(read(fixture()).assets[0].status).toBe('not_evaluated');
  });
  it('rejects a legacy array instead of inventing an empty summary', () => {
    expect(() => read([])).toThrow();
  });
  it('rejects a mismatched asset identity', () => {
    const payload = fixture();
    payload.intelligence.assessments[0].asset_id = 'pump-b';
    expect(() => read(payload)).toThrow();
  });
  it('rejects an unsupported ready claim', () => {
    const payload = fixture();
    payload.intelligence.readiness = 'ready';
    expect(() => read(payload)).toThrow();
  });
  it('rejects contradictory counts', () => {
    const payload = fixture();
    payload.intelligence.service_due = 1;
    expect(() => read(payload)).toThrow();
  });
  it('preserves a server-recorded scheduled date basis', () => {
    const payload = fixture();
    Object.assign(payload.intelligence, { readiness: 'attention_required', assessment_coverage: 1,
      service_due: 1, service_not_evaluated: 0 });
    Object.assign(payload.intelligence.assessments[0], { status: 'due', basis: 'next_service_date', constraints: [] });
    expect(read(payload).assets[0].basis).toBe('next_service_date');
  });
});
