export interface FertilizerScenarioForm {
  input_basis: 'synthetic' | 'operator_supplied';
  source_ref: string;
  nutrient_basis: 'N' | 'P2O5' | 'K2O';
  target_yield_t_ha: string;
  uptake_kg_per_t: string;
  soil_supply_kg_ha: string;
  fertilizer_grade_pct: string;
  use_efficiency: string;
}

type NumericKey = 'target_yield_t_ha' | 'uptake_kg_per_t' | 'soil_supply_kg_ha' |
  'fertilizer_grade_pct' | 'use_efficiency';

export type FertilizerScenarioInput = Omit<FertilizerScenarioForm, NumericKey> &
  Record<NumericKey, number>;

export interface FertilizerEstimate {
  crop_demand_kg_ha: number;
  net_nutrient_kg_ha: number;
  nutrient_to_apply_kg_ha: number;
  product_kg_ha: number;
}

export interface FertilizerScenarioResponse {
  status?: string;
  inputs?: FertilizerScenarioInput;
  estimate?: FertilizerEstimate;
  source_ref_verified?: boolean;
  lab_supported?: boolean;
  execution_authorized?: boolean;
  local_compliance_evaluated?: boolean;
}

export function buildFertilizerScenario(form: FertilizerScenarioForm): FertilizerScenarioInput | null {
  const source_ref = form.source_ref.trim();
  if (!source_ref || source_ref.length > 500) return null;
  const parse = (text: string): number | null => {
    if (!text.trim()) return null;
    const value = Number(text);
    return Number.isFinite(value) && value >= 0 ? value : null;
  };
  const target_yield_t_ha = parse(form.target_yield_t_ha);
  const uptake_kg_per_t = parse(form.uptake_kg_per_t);
  const soil_supply_kg_ha = parse(form.soil_supply_kg_ha);
  const fertilizer_grade_pct = parse(form.fertilizer_grade_pct);
  const use_efficiency = parse(form.use_efficiency);
  if (target_yield_t_ha === null || uptake_kg_per_t === null || soil_supply_kg_ha === null ||
    fertilizer_grade_pct === null || fertilizer_grade_pct < 1 || fertilizer_grade_pct > 100 ||
    use_efficiency === null || use_efficiency < 0.1 || use_efficiency > 1) return null;
  return { input_basis: form.input_basis, source_ref, nutrient_basis: form.nutrient_basis,
    target_yield_t_ha, uptake_kg_per_t, soil_supply_kg_ha, fertilizer_grade_pct, use_efficiency };
}

export function acceptedFertilizerEstimate(
  response: FertilizerScenarioResponse | undefined,
  input: FertilizerScenarioInput,
): FertilizerEstimate | null {
  if (response?.status !== 'estimated' || response.source_ref_verified !== false ||
    response.lab_supported !== false || response.execution_authorized !== false ||
    response.local_compliance_evaluated !== false || !response.inputs || !response.estimate) return null;
  const echo = response.inputs;
  if (!(Object.keys(input) as (keyof FertilizerScenarioInput)[]).every(key => echo[key] === input[key])) return null;
  const result = response.estimate;
  if (![result.crop_demand_kg_ha, result.net_nutrient_kg_ha,
    result.nutrient_to_apply_kg_ha, result.product_kg_ha].every(n => Number.isFinite(n) && n >= 0)) return null;
  return result;
}
