import type { ReactNode } from 'react';
import { roleCan, roleUiMode, type SahoolUiRole } from './roleUiContract';

export type RoleAwareMapSurfaceProps = {
  role: SahoolUiRole;
  children: ReactNode;
};

/**
 * UI-13 seam: exposes role mode to the map surface without hiding data silently.
 * Fine-grained buttons continue to use canMutate/roleCan; this wrapper makes the
 * mode visible to tests and future design-system variants.
 */
export function RoleAwareMapSurface({ role, children }: RoleAwareMapSurfaceProps) {
  const mode = roleUiMode(role);
  return (
    <section
      data-testid="maphub-role-aware-surface"
      data-sahool-region="role-aware-map-surface"
      data-role-mode={mode}
      data-can-create-field={roleCan(role, 'create_field') ? 'true' : 'false'}
      data-can-create-scouting-pin={roleCan(role, 'create_scouting_pin') ? 'true' : 'false'}
    >
      {children}
    </section>
  );
}
