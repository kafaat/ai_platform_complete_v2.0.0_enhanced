export type SahoolUiRole = 'owner' | 'manager' | 'agronomist' | 'worker' | 'ngo_observer' | 'admin' | string | null | undefined;

export type RoleUiCapability =
  | 'view_map'
  | 'view_evidence'
  | 'create_field'
  | 'mutate_field'
  | 'create_scouting_pin'
  | 'run_backfill'
  | 'delete_field';

const MUTATION_ROLES = new Set(['owner', 'manager', 'admin', 'agronomist']);
const OBSERVER_ROLES = new Set(['ngo_observer', 'viewer', 'worker']);

export function roleCan(role: SahoolUiRole, capability: RoleUiCapability): boolean {
  if (capability === 'view_map' || capability === 'view_evidence') return true;
  const normalized = String(role ?? '').toLowerCase();
  if (OBSERVER_ROLES.has(normalized)) return false;
  if (capability === 'delete_field') return normalized === 'owner' || normalized === 'admin';
  return MUTATION_ROLES.has(normalized);
}

export function roleUiMode(role: SahoolUiRole): 'operator' | 'observer' | 'admin' {
  const normalized = String(role ?? '').toLowerCase();
  if (normalized === 'admin') return 'admin';
  if (OBSERVER_ROLES.has(normalized)) return 'observer';
  return 'operator';
}
