import { kongApi } from './client';
import type { IrrigationEngineeringSummary, IrrigationSystemType } from '../../lib/irrigationEngineering';

export type EvidenceLevel = 'measured' | 'commissioned' | 'manufacturer_spec' | 'user_declared' | 'estimated' | 'unknown';

export interface InteractiveCalculatorInput {
  tenantId: string;
  fieldId: string;
  seasonId?: string | null;
  systemId: string;
  systemType: 'center_pivot' | 'linear_move' | 'reel' | 'sprinkler' | 'drip' | 'pump_only' | 'valve_network';
  irrigatedAreaHa: number;
  applicationEfficiency: number;
  designFlowM3h?: number;
  measuredFlowM3h?: number;
  pipeLengthM: number;
  pipeDiameterMm?: number;
  hazenWilliamsC: number;
  elevationChangeM: number;
  terminalPressureBar?: number;
  pumpEfficiency: number;
  motorEfficiency: number;
  installedMotorPowerKw?: number;
  waterDemandMode: 'sahool' | 'manual';
  manualNetDepthMm?: number;
  cropType?: string;
  growthStage?: string;
  kc?: number;
  soilType?: string;
  tawMm?: number;
  rawMm?: number;
  depletionMm?: number;
  infiltrationRateMmH?: number;
  et0MmDay?: number;
  forecastDays: number;
  effectiveRainMm: number;
  elbows90: number;
  valves: number;
  checkValves: number;
  filters: number;
  customMinorLossM: number;
  safetyMarginM: number;
}

export interface InteractiveCalculatorResult {
  status: 'pass' | 'degraded' | 'fail' | 'incomplete';
  calculations: Record<string, number | null>;
  water_demand: Record<string, unknown>;
  hydraulics: Record<string, unknown>;
  pump_energy: Record<string, unknown>;
  feasibility: Record<string, unknown>;
  warnings: string[];
  blocking_constraints: string[];
  explanations: string[];
  assumptions: string[];
  input_quality: Record<string, string>;
  content_digest: string;
}

export async function calculateInteractiveIrrigation(input: InteractiveCalculatorInput): Promise<InteractiveCalculatorResult> {
  const { data } = await kongApi.post('/api/v1/irrigation/engineering/interactive-calculate', {
    specification: {
      tenant_id: input.tenantId,
      field_id: input.fieldId,
      season_id: input.seasonId ?? null,
      system_id: input.systemId,
      name: 'Interactive manual calculator',
      system_type: input.systemType,
      execution_mode: 'recommendation_only',
      irrigated_area_ha: input.irrigatedAreaHa,
      application_efficiency: input.applicationEfficiency,
      available_hours_per_day: 24,
      design_flow_lps: input.designFlowM3h ? input.designFlowM3h / 3.6 : null,
      measured_flow_lps: input.measuredFlowM3h ? input.measuredFlowM3h / 3.6 : null,
      length_m: input.systemType === 'center_pivot' ? 1 : null,
      mainline_length_m: input.pipeLengthM,
      mainline_internal_diameter_mm: input.pipeDiameterMm ?? null,
      hazen_williams_c: input.hazenWilliamsC,
      elevation_change_m: input.elevationChangeM,
      minor_loss_m: 0,
      required_terminal_pressure_bar: input.terminalPressureBar ?? null,
      pump_efficiency: input.pumpEfficiency,
      motor_efficiency: input.motorEfficiency,
      evidence: {},
    },
    water_demand: {
      mode: input.waterDemandMode,
      manual_net_depth_mm: input.manualNetDepthMm ?? null,
      crop: {
        crop_type: input.cropType ?? null,
        growth_stage: input.growthStage ?? null,
        kc: input.kc ?? null,
      },
      soil: {
        soil_type: input.soilType ?? null,
        taw_mm: input.tawMm ?? null,
        raw_mm: input.rawMm ?? null,
        depletion_mm: input.depletionMm ?? null,
        infiltration_rate_mm_h: input.infiltrationRateMmH ?? null,
        moisture_quality: 'user_declared',
      },
      weather: {
        et0_mm_day: input.et0MmDay ?? null,
        forecast_days: input.forecastDays,
        effective_rain_mm: input.effectiveRainMm,
        forecast_quality: 'estimated',
      },
    },
    fittings: {
      elbows_90: input.elbows90,
      valves: input.valves,
      check_valves: input.checkValves,
      filters: input.filters,
      custom_minor_loss_m: input.customMinorLossM,
    },
    safety_margin_m: input.safetyMarginM,
    installed_motor_power_kw: input.installedMotorPowerKw ?? null,
  });
  return data as InteractiveCalculatorResult;
}

// ── Engineering summary (capability graph + manual operation) ─────────────────
// Consumes POST /api/v1/irrigation/engineering/calculate which returns the full
// EngineeringResult (== IrrigationEngineeringSummary): status + blocking_constraints
// + warnings + calculations + capability_graph + manual_operation + content_digest.
// Distinct from `calculateInteractiveIrrigation` (/interactive-calculate) which
// returns the interactive breakdown, not the composite workspace summary.
export interface EngineeringCalcInput {
  tenantId: string;
  fieldId: string;
  seasonId?: string | null;
  systemId: string;
  name: string;
  systemType: IrrigationSystemType;
  irrigatedAreaHa: number;
  netDepthMm: number;
  effectiveRainMm?: number;
  applicationEfficiency?: number;
  designFlowLps?: number | null;
  measuredFlowLps?: number | null;
  lengthM?: number | null; // required for center_pivot
  mainlineLengthM?: number;
  mainlineInternalDiameterMm?: number | null;
  hazenWilliamsC?: number;
  elevationChangeM?: number;
}

export async function calculateIrrigationEngineering(
  input: EngineeringCalcInput,
): Promise<IrrigationEngineeringSummary> {
  const { data } = await kongApi.post('/api/v1/irrigation/engineering/calculate', {
    specification: {
      tenant_id: input.tenantId,
      field_id: input.fieldId,
      season_id: input.seasonId ?? null,
      system_id: input.systemId,
      name: input.name,
      system_type: input.systemType,
      irrigated_area_ha: input.irrigatedAreaHa,
      application_efficiency: input.applicationEfficiency ?? 0.8,
      design_flow_lps: input.designFlowLps ?? null,
      measured_flow_lps: input.measuredFlowLps ?? null,
      length_m: input.lengthM ?? null,
      mainline_length_m: input.mainlineLengthM ?? 0,
      mainline_internal_diameter_mm: input.mainlineInternalDiameterMm ?? null,
      hazen_williams_c: input.hazenWilliamsC ?? 140,
      elevation_change_m: input.elevationChangeM ?? 0,
    },
    water_demand: {
      net_depth_mm: input.netDepthMm,
      effective_rain_mm: input.effectiveRainMm ?? 0,
    },
  });
  return data as IrrigationEngineeringSummary;
}
