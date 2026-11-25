import { beforeEach, describe, expect, it, vi } from 'vitest';
import { calculateReservoirBoosterNetwork, type IrrigationNetworkInput } from './irrigationNetworkCalculator';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('./client', () => ({ kongApi: { post } }));

function input(fieldId: string, wellFlowsM3h: number[]): IrrigationNetworkInput {
  return {
    tenantId: 'synthetic-farm', fieldId, seasonId: 'synthetic-wheat',
    requiredGrossVolumeM3: 3000, wellFlowsM3h,
    reservoirCapacityM3: 3500, reservoirCurrentM3: 3000, reservoirMinimumM3: 500,
    boosterFlowM3h: 200, boosterPumpEfficiency: 0.78, boosterMotorEfficiency: 0.92,
    pipeLengthM: 1000, pipeDiameterMm: 250, hazenWilliamsC: 140,
    elevationChangeM: 0, minorLossM: 0, safetyMarginM: 5,
    systemType: 'center_pivot', systemFlowM3h: 200, systemPressureBar: 3.2,
    radiusM: Math.sqrt(500000 / Math.PI),
  };
}

beforeEach(() => { post.mockReset(); post.mockResolvedValue({ data: {} }); });

describe('independent reservoir networks', () => {
  it('uses separate field-scoped calculation slots for six wells and two ponds and boosters', async () => {
    await calculateReservoirBoosterNetwork(input('a', [80, 90, 100]));
    await calculateReservoirBoosterNetwork(input('b', [40, 50, 60]));
    const a = post.mock.calls[0][1];
    const b = post.mock.calls[1][1];
    expect(new Set([...a.wells, ...b.wells].map(w => w.well_id)).size).toBe(6);
    expect(a.reservoir.reservoir_id).not.toBe(b.reservoir.reservoir_id);
    expect(a.booster.pump_id).not.toBe(b.booster.pump_id);
    expect(a.field_id).toBe('a');
    expect(b.field_id).toBe('b');
  });

  it('preserves invalid well input for server rejection rather than shifting other well slots', async () => {
    await calculateReservoirBoosterNetwork(input('a', [80, -1, 100]));
    const wells = post.mock.calls[0][1].wells;
    expect(wells).toHaveLength(3);
    expect(wells[1]).toMatchObject({ well_id: 'well:a:2', available_flow_m3_h: -1 });
    expect(wells[2]).toMatchObject({ well_id: 'well:a:3', available_flow_m3_h: 100 });
  });
});
