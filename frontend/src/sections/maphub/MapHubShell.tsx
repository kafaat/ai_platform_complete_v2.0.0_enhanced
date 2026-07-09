import type { ReactNode } from 'react';

export type MapHubShellRegion =
  | 'field-list'
  | 'map-canvas'
  | 'layer-manager'
  | 'field-drawer'
  | 'season-timeline'
  | 'quick-actions'
  | 'operational-overlays';

export const MAPHUB_SHELL_REGIONS: readonly MapHubShellRegion[] = [
  'field-list',
  'map-canvas',
  'layer-manager',
  'field-drawer',
  'season-timeline',
  'quick-actions',
  'operational-overlays',
] as const;

export const MAPHUB_STRANGLER_PHASES = [
  {
    id: 'ui5-shell',
    label: 'Shell wrapper only',
    rule: 'Wrap the existing MapHub with stable semantic shell boundaries without moving behavior.',
  },
  {
    id: 'ui6-controls',
    label: 'Extract controls',
    rule: 'Move layer controls, presets, and quick actions behind props while preserving the old MapHub entrypoint.',
  },
  {
    id: 'ui7-canvas',
    label: 'Extract canvas',
    rule: 'Move map canvas orchestration into a focused MapCanvas component after guard coverage exists.',
  },
  {
    id: 'ui8-field-drawer',
    label: 'Extract field context panels',
    rule: 'Move Field Drawer, timelines, and action panels after field_id + season_id contracts are stable.',
  },
] as const;

export function MapHubShell({ children }: { children: ReactNode }) {
  return (
    <section
      data-testid="maphub-shell"
      data-sahool-shell="farm-command-center-map"
      aria-label="مركز الخرائط التشغيلي"
    >
      {children}
    </section>
  );
}
