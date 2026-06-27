export type RegionRole = 'primary-control-plane' | 'active-edge' | 'warm-standby';

export type GlobalTopologyRequest = {
  home_region: string;
  satellite_regions: string[];
  tenants: number;
  fields: number;
  data_residency?: 'tenant_region' | 'country' | string;
};

export type LoadMatrixRequest = {
  fields: number;
  target_tiles_per_day: number;
  concurrent_users: number;
};

export type DisasterRecoveryTier = 'standard' | 'enterprise' | 'mission_critical';

export const globalScaleRuntimeEndpoints = {
  topology: '/api/v1/gis/cloud-native/phase8/global/topology',
  loadMatrix: '/api/v1/gis/cloud-native/phase8/load/matrix',
  loadResults: '/api/v1/gis/cloud-native/phase8/load/results',
  disasterRecovery: '/api/v1/gis/cloud-native/phase8/disaster-recovery/plan',
  errorBudget: '/api/v1/gis/cloud-native/phase8/slo/error-budget',
  costGuardrails: '/api/v1/gis/cloud-native/phase8/cost/guardrails',
  releaseGate: '/api/v1/gis/cloud-native/phase8/release-gate',
} as const;

export function releaseGateBadge(ready: boolean, blockers: string[]): 'ready' | 'blocked' | 'needs-review' {
  if (ready) return 'ready';
  if (blockers.includes('security') || blockers.includes('dr') || blockers.includes('load')) return 'blocked';
  return 'needs-review';
}

export function errorBudgetColor(status: string): 'green' | 'amber' | 'red' {
  if (status === 'healthy') return 'green';
  if (status === 'watch') return 'amber';
  return 'red';
}
