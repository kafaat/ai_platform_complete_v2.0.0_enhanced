import { describe, expect, it } from 'vitest';
import { buildFertilizerScenario, acceptedFertilizerEstimate } from './fertilizerScenario';

const form = {
  input_basis: 'synthetic' as const, source_ref: 'synthetic:wheat-season-1',
  nutrient_basis: 'N' as const, target_yield_t_ha: '6', uptake_kg_per_t: '25',
  soil_supply_kg_ha: '30', fertilizer_grade_pct: '46', use_efficiency: '0.75',
};

describe('manual 4R fertilizer scenario', () => {
  it('sends explicit assumptions to the existing API without a field or invented values', () => {
    expect(buildFertilizerScenario(form)).toEqual({
      ...form, target_yield_t_ha: 6, uptake_kg_per_t: 25, soil_supply_kg_ha: 30,
      fertilizer_grade_pct: 46, use_efficiency: 0.75,
    });
    expect(buildFertilizerScenario({ ...form, soil_supply_kg_ha: '' })).toBeNull();
    expect(buildFertilizerScenario({ ...form, soil_supply_kg_ha: '0' })?.soil_supply_kg_ha).toBe(0);
    expect(buildFertilizerScenario({ ...form, source_ref: ' ' })).toBeNull();
  });

  it('displays only a matching, explicitly non-authoritative server estimate', () => {
    const input = buildFertilizerScenario(form)!;
    const result = {
      status: 'estimated', inputs: input,
      estimate: { crop_demand_kg_ha: 150, net_nutrient_kg_ha: 120,
        nutrient_to_apply_kg_ha: 160, product_kg_ha: 347.83 },
      source_ref_verified: false, lab_supported: false,
      execution_authorized: false, local_compliance_evaluated: false,
    };
    expect(acceptedFertilizerEstimate(result, input)).toEqual(result.estimate);
    expect(acceptedFertilizerEstimate({ ...result, execution_authorized: true }, input)).toBeNull();
    expect(acceptedFertilizerEstimate({ ...result, inputs: { ...input, soil_supply_kg_ha: 0 } }, input)).toBeNull();
    expect(acceptedFertilizerEstimate({ ...result, estimate: { ...result.estimate, product_kg_ha: Infinity } }, input)).toBeNull();
    expect(acceptedFertilizerEstimate(undefined, input)).toBeNull();
  });
});
