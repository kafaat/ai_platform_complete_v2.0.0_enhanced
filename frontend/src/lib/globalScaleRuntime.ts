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

// The phase8 endpoint constants were removed: no server route serves them
// (services/sahool-platform/api/gis_phase8_global_scale.py has functions, no decorators)
// and nothing called them (WEB-ENDPOINT-CONSTANTS-WITHOUT-SERVER-HANDLER-01).

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
