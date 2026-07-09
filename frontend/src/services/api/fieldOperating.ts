// ═══════════════════════════════════════════════════════════════
// SAHOOL UI-4 — Field Operating API contracts
// Readiness / Data Completeness / Unified Timeline / Priority Queue
//
// هذه طبقة عقود أمامية فقط فوق endpoints موجودة/مخططة. لا تُلفّق بيانات؛
// عند الفشل يرمي العميل الخطأ كي تعرض الواجهة empty/error/degraded state.
// ═══════════════════════════════════════════════════════════════

import { kongApi } from './client';

export type CompletenessStatus = 'complete' | 'partial' | 'missing' | 'unknown' | 'stale';

export interface FieldReadinessItem {
  key: string;
  label_ar?: string;
  status: CompletenessStatus;
  weight?: number;
  reason_ar?: string;
  action_label_ar?: string;
  action_route?: string;
}

export interface FieldReadinessResponse {
  field_id: string;
  score: number;
  calibrated?: boolean;
  items: FieldReadinessItem[];
  missing?: string[];
  warnings?: string[];
  note_ar?: string;
}

export interface FieldDataCompletenessResponse {
  field_id: string;
  score?: number;
  level?: string;
  present?: string[];
  missing?: string[];
  recommended_actions?: Array<Record<string, unknown>>;
  note_ar?: string;
  [key: string]: unknown;
}

export type { FieldTimelineEvent, FieldUnifiedTimelineParams, FieldUnifiedTimelineResponse } from './fieldTimeline';


export const getFieldUnifiedTimeline = (
  fieldId: string,
  params?: import('./fieldTimeline').FieldUnifiedTimelineParams,
): Promise<import('./fieldTimeline').FieldUnifiedTimelineResponse> =>
  // UI-32: compatibility wrapper; domain module and this stable route stay explicit.
  kongApi.get<import('./fieldTimeline').FieldUnifiedTimelineResponse>(`/api/v1/fields/${fieldId}/unified-timeline`, { params }).then(r => r.data);

export interface PriorityQueueItem {
  id: string;
  type: 'alert' | 'recommendation' | 'task' | 'weather_window' | 'imagery' | 'scouting' | 'sensor' | 'equipment' | string;
  title_ar: string;
  field_id?: string;
  season_id?: string;
  severity?: 'low' | 'medium' | 'high' | 'critical' | string;
  due_at?: string;
  confidence?: number;
  yield_impact?: number;
  action?: Record<string, unknown>;
  reasons?: string[];
}

export interface PriorityQueueResponse {
  scope: 'farm' | 'field';
  farm_id?: string;
  field_id?: string;
  items: PriorityQueueItem[];
  degraded?: boolean;
  warning_ar?: string;
}

export const getFieldReadiness = (fieldId: string): Promise<FieldReadinessResponse> =>
  kongApi.get<FieldReadinessResponse>(`/api/v1/fields/${fieldId}/readiness`).then(r => r.data);

export const getFieldDataCompleteness = (fieldId: string): Promise<FieldDataCompletenessResponse> =>
  kongApi.get<FieldDataCompletenessResponse>(`/api/v1/fields/${fieldId}/data-completeness`).then(r => r.data);

export const getFarmPriorityQueue = (farmId: string): Promise<PriorityQueueResponse> =>
  kongApi.get<PriorityQueueResponse>(`/api/v1/farms/${farmId}/priority-queue`).then(r => r.data);

export const getFieldPriorityQueue = (fieldId: string): Promise<PriorityQueueResponse> =>
  kongApi.get<PriorityQueueResponse>(`/api/v1/fields/${fieldId}/priority-queue`).then(r => r.data);
