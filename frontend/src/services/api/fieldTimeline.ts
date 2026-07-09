// SAHOOL UI-32 — Field Workspace timeline API domain module
// Backend-owned unified timeline. The frontend never fabricates timeline events.

import { kongApi } from './client';

export interface FieldTimelineEvent {
  event_id?: string;
  event_type?: string;
  category?: string;
  occurred_at?: string;
  title_ar?: string;
  description_ar?: string;
  payload?: Record<string, unknown>;
  actor_id?: string | number | null;
}

export interface FieldUnifiedTimelineResponse {
  field_id: string;
  season_id?: string | null;
  events: FieldTimelineEvent[];
  total_events?: number;
  categories?: Record<string, number>;
  degraded?: boolean;
  note_ar?: string;
  error?: string;
  [key: string]: unknown;
}

export interface FieldUnifiedTimelineParams {
  limit?: number;
  newest_first?: boolean;
  category?: string;
  season_id?: string | null;
}

export const getFieldUnifiedTimeline = (
  fieldId: string,
  params?: FieldUnifiedTimelineParams,
): Promise<FieldUnifiedTimelineResponse> =>
  kongApi.get<FieldUnifiedTimelineResponse>(`/api/v1/fields/${fieldId}/unified-timeline`, { params }).then(r => r.data);
