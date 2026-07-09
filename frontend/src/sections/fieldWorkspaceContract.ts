// Field Workspace Operating Contract — UI-14/15
// The workspace is always anchored to a real field_id and an optional season_id.
// It must not fabricate readiness, timeline events, or recommendations.

export type FieldWorkspaceTab =
  | 'overview'
  | 'map'
  | 'season'
  | 'imagery'
  | 'weather'
  | 'irrigation'
  | 'operations'
  | 'recommendations'
  | 'reports';

export interface FieldWorkspaceContext {
  fieldId: string;
  seasonId?: string | null;
  source: 'route' | 'selected-field' | 'unknown';
}

export const FIELD_WORKSPACE_TABS: Array<{
  id: FieldWorkspaceTab;
  label_ar: string;
  requires_field: boolean;
  requires_season: boolean;
  degraded_safe: boolean;
}> = [
  { id: 'overview', label_ar: 'نظرة عامة', requires_field: true, requires_season: false, degraded_safe: true },
  { id: 'map', label_ar: 'الخريطة', requires_field: true, requires_season: false, degraded_safe: true },
  { id: 'season', label_ar: 'الموسم', requires_field: true, requires_season: false, degraded_safe: true },
  { id: 'imagery', label_ar: 'الصور والمؤشرات', requires_field: true, requires_season: false, degraded_safe: true },
  { id: 'weather', label_ar: 'الطقس', requires_field: true, requires_season: false, degraded_safe: true },
  { id: 'irrigation', label_ar: 'الري', requires_field: true, requires_season: true, degraded_safe: true },
  { id: 'operations', label_ar: 'العمليات', requires_field: true, requires_season: true, degraded_safe: true },
  { id: 'recommendations', label_ar: 'التوصيات', requires_field: true, requires_season: true, degraded_safe: true },
  { id: 'reports', label_ar: 'التقارير', requires_field: true, requires_season: false, degraded_safe: true },
];

export function normalizeWorkspaceTab(value: string | null | undefined): FieldWorkspaceTab {
  return FIELD_WORKSPACE_TABS.some((tab) => tab.id === value)
    ? (value as FieldWorkspaceTab)
    : 'overview';
}
