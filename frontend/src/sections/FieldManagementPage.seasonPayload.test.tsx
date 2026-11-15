// v26 workstream 01/04: the season form payload reaches POST /seasons whole (zero kept, absent
// sent as null), and a simulation with no yield estimate shows «—», never "0 – 0".
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

const apiFields = vi.hoisted(() => ({
  fields: [{ field_id: 'fld_1', name: 'حقل القمح', crop: 'wheat', area_ha: 2 }],
}));
const captured = vi.hoisted(() => ({ onSave: null as null | ((d: unknown) => Promise<void>) }));
const post = vi.hoisted(() => vi.fn());
const sim = vi.hoisted(() => ({ data: undefined as unknown }));

vi.mock('../components/AddSeasonWithStages', () => ({
  default: ({ onSave }: { onSave: (d: unknown) => Promise<void> }) => {
    captured.onSave = onSave;
    return <section aria-label="season-form" />;
  },
}));
vi.mock('../components/AddFieldWithMap', () => ({ default: () => null }));
vi.mock('../components/FieldDetailPanel', () => ({ default: () => null }));
vi.mock('../components/fieldsetup/FieldSetupWizard', () => ({ default: () => null }));
vi.mock('../components/FieldIndicatorMap', () => ({ default: () => null }));
vi.mock('../services/api', async (orig) => {
  const real = await orig<typeof import('../services/api')>();
  return { ...real, kongApi: { ...real.kongApi, post } };
});
vi.mock('../services/websocket', () => ({ toastStore: { add: vi.fn() } }));
vi.mock('../hooks/useApi', () => ({
  useFields: () => ({ data: apiFields, isLoading: false, isError: false, refetch: vi.fn() }),
  useSimulateSeason: () => ({
    mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, isError: false, data: sim.data,
  }),
}));
vi.mock('../hooks/useAuth', () => ({ useAuthStore: () => ({ user: { role: 'owner' } }) }));
vi.mock('../lib/fieldMapView', () => ({ saveFieldMapView: vi.fn() }));

import FieldManagementPage from './FieldManagementPage';

// What AddSeasonWithStages hands to onSave (its own `+x || undefined` mapping).
const FORM = {
  field_id: 'fld_1', crops: ['wheat'], cultivar: 'wheat_aziz',
  land_leveling_date: '2026-10-01', plowing_date: '2026-10-05',
  sowing_date: '2026-10-10', season_end: '', seed_rate_kg_ha: 120,
  irrigation_type: 'drip', custom_stages: [],
  target_yield_kg_ha: 0, actual_yield_kg_ha: undefined, plant_density: 0,
  row_spacing_cm: undefined, seed_variety_source: undefined, maturity: 'medium',
  tillage_type: 'conventional', notes_ar: undefined,
};

async function saveSeason(data: unknown) {
  render(<FieldManagementPage />);
  fireEvent.click(screen.getAllByText('موسم زراعي')[0]);
  expect(captured.onSave).toBeTypeOf('function');
  await act(async () => { await captured.onSave!(data); });
}

beforeEach(() => {
  cleanup();
  captured.onSave = null;
  post.mockReset();
  sim.data = undefined;
});

describe('FieldManagementPage season payload', () => {
  it('forwards the seven agronomic fields, keeps zero and sends null for absent values', async () => {
    post.mockResolvedValueOnce({ data: { season_id: 'ssn_1' } });
    await saveSeason(FORM);
    expect(post).toHaveBeenCalledTimes(1);
    const [url, body] = post.mock.calls[0];
    expect(url).toBe('/api/v1/fields/fld_1/seasons');
    expect(body).toMatchObject({
      target_yield_kg_ha: 0,
      plant_density: 0,
      actual_yield_kg_ha: null,
      row_spacing_cm: null,
      seed_variety_source: null,
      maturity: 'medium',
      tillage_type: 'conventional',
      land_leveling_date: '2026-10-01',
      plowing_date: '2026-10-05',
      season_end: null,
    });
  });

  it('shows «—» for a simulation without a yield estimate, not a zero range', async () => {
    sim.data = {
      season_id: 'ssn_1', crop: 'wheat', crop_recognized: true, days_simulated: 20,
      gdd_total: 0, gdd_to_maturity: 1500, maturity_reached: false, lai_max: 0,
      biomass_kg_ha: 0, yield_kg_ha: null, yield_low_kg_ha: null, yield_high_kg_ha: null,
      water_need_mm: 80, water_supply_mm: null, water_stress_factor: 1, confidence: 0,
      rationale_ar: 'x', assumptions_ar: [], warnings_ar: [], sim_ran_at: '2026-11-12',
      yield_status: 'unavailable_missing_gdd', limitations: ['NO_GDD_EVIDENCE_NO_YIELD_ESTIMATE'],
    };
    post.mockResolvedValueOnce({ data: { season_id: 'ssn_1' } });
    await saveSeason(FORM);
    expect(screen.getByText(/unavailable_missing_gdd/)).toBeInTheDocument();
    expect(screen.queryByText('0 – 0')).toBeNull();
  });
});
