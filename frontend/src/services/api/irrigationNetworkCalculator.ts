import { kongApi } from './client';

export type NetworkIrrigationSystemType =
  | 'none'
  | 'center_pivot'
  | 'linear_move'
  | 'reel'
  | 'sprinkler'
  | 'drip'
  | 'valve_network';

export interface IrrigationNetworkInput {
  tenantId: string;
  fieldId: string;
  seasonId?: string | null;
  requiredGrossVolumeM3: number;
  wellFlowsM3h: number[];
  reservoirCapacityM3: number;
  reservoirCurrentM3: number;
  reservoirMinimumM3: number;
  boosterFlowM3h: number;
  boosterHeadM?: number;
  boosterMotorKw?: number;
  boosterPumpEfficiency: number;
  boosterMotorEfficiency: number;
  pipeLengthM: number;
  pipeDiameterMm: number;
  hazenWilliamsC: number;
  elevationChangeM: number;
  minorLossM: number;
  safetyMarginM: number;
  systemType: NetworkIrrigationSystemType;
  systemName?: string;
  systemFlowM3h?: number;
  systemPressureBar?: number;
  radiusM?: number;
  operatingArcDeg?: number;
  machineLengthM?: number;
  travelLengthM?: number;
  hoseLengthM?: number;
  hoseDiameterMm?: number;
  zoneCount?: number;
  concurrentZones?: number;
  emitterCount?: number;
  emitterFlowLph?: number;
  sprinklerCount?: number;
  sprinklerFlowM3h?: number;
  wettedAreaHa?: number;
}

export interface IrrigationNetworkResult {
  status: 'pass' | 'degraded' | 'fail' | 'incomplete';
  machine_mode: 'selected' | 'none';
  selected_machines: Array<Record<string, unknown>>;
  pivot_mode: 'selected' | 'none';
  selected_pivots: Array<Record<string, unknown>>;
  reservoir_balance: Record<string, number | null>;
  booster: Record<string, number | null>;
  segments: Array<Record<string, unknown>>;
  scenarios: Array<Record<string, unknown>>;
  warnings: string[];
  blocking_constraints: string[];
  content_digest: string;
}

export async function calculateReservoirBoosterNetwork(input: IrrigationNetworkInput): Promise<IrrigationNetworkResult> {
  const machineId = `machine:${input.fieldId}:1`;
  const hasMachine = input.systemType !== 'none';
  const irrigationMachines = hasMachine ? [{
    machine_id: machineId,
    name: input.systemName || 'نظام ري الحقل',
    field_id: input.fieldId,
    system_type: input.systemType,
    enabled: true,
    design_flow_m3_h: input.systemFlowM3h,
    required_inlet_pressure_bar: input.systemPressureBar,
    radius_m: input.systemType === 'center_pivot' ? input.radiusM : undefined,
    operating_arc_deg: input.systemType === 'center_pivot' ? (input.operatingArcDeg ?? 360) : undefined,
    machine_length_m: input.systemType === 'linear_move' ? input.machineLengthM : undefined,
    travel_length_m: input.systemType === 'linear_move' ? input.travelLengthM : undefined,
    hose_length_m: input.systemType === 'reel' ? input.hoseLengthM : undefined,
    hose_internal_diameter_mm: input.systemType === 'reel' ? input.hoseDiameterMm : undefined,
    zone_count: ['drip', 'valve_network'].includes(input.systemType) ? input.zoneCount : undefined,
    concurrent_zones: ['drip', 'valve_network'].includes(input.systemType) ? input.concurrentZones : undefined,
    emitter_count: input.systemType === 'drip' ? input.emitterCount : undefined,
    emitter_flow_lph: input.systemType === 'drip' ? input.emitterFlowLph : undefined,
    sprinkler_count: input.systemType === 'sprinkler' ? input.sprinklerCount : undefined,
    sprinkler_flow_m3_h: input.systemType === 'sprinkler' ? input.sprinklerFlowM3h : undefined,
    wetted_area_ha: input.wettedAreaHa,
  }] : [];

  const { data } = await kongApi.post('/api/v1/irrigation/engineering/network-calculate', {
    tenant_id: input.tenantId,
    field_id: input.fieldId,
    season_id: input.seasonId ?? null,
    required_gross_volume_m3: input.requiredGrossVolumeM3,
    wells: input.wellFlowsM3h.filter(v => v >= 0).map((flow, i) => ({ well_id: `well-${i + 1}`, available_flow_m3_h: flow, enabled: flow > 0 })),
    reservoir: {
      reservoir_id: `reservoir:${input.fieldId}`,
      capacity_m3: input.reservoirCapacityM3,
      current_volume_m3: input.reservoirCurrentM3,
      minimum_operating_volume_m3: input.reservoirMinimumM3,
      evaporation_loss_m3_h: 0,
      seepage_loss_m3_h: 0,
    },
    booster: {
      pump_id: `booster:${input.fieldId}`,
      design_flow_m3_h: input.boosterFlowM3h,
      design_head_m: input.boosterHeadM ?? null,
      installed_motor_power_kw: input.boosterMotorKw ?? null,
      pump_efficiency: input.boosterPumpEfficiency,
      motor_efficiency: input.boosterMotorEfficiency,
      suction_loss_m: 1,
    },
    segments: [{
      segment_id: 'mainline-1',
      from_node: `reservoir:${input.fieldId}`,
      to_node: hasMachine ? machineId : `field:${input.fieldId}`,
      length_m: input.pipeLengthM,
      internal_diameter_mm: input.pipeDiameterMm,
      hazen_williams_c: input.hazenWilliamsC,
      elevation_change_m: input.elevationChangeM,
      minor_loss_m: input.minorLossM,
    }],
    irrigation_machines: irrigationMachines,
    requested_machine_ids: hasMachine ? [machineId] : [],
    pivots: [],
    requested_pivot_ids: [],
    safety_margin_m: input.safetyMarginM,
  });
  return data as IrrigationNetworkResult;
}
