// SAHOOL UI-26 — Field Workspace Irrigation API contracts
// يعرض نصائح/جداول محفوظة فقط؛ لا يحسب ريّاً من الواجهة.

import { kongApi } from './client';

export interface FieldIrrigationAdvice {
  recommended_mm?: number | null;
  urgency?: 'none' | 'low' | 'moderate' | 'high' | string;
  timing_ar?: string;
  et0?: number | null;
  kc?: number | null;
  rationale_ar?: string;
  field_id: string;
  crop?: string | null;
  stage?: string;
  source?: string;
}

export interface FieldIrrigationSchedule {
  schedule_id: string;
  field_id?: string | null;
  valve_id?: string | null;
  name: string;
  start_time: string;
  duration_min: number;
  days_of_week?: number[] | null;
  water_target_mm?: number | null;
  enabled: boolean;
  last_run_at?: string | null;
}

export const getFieldIrrigationAdvice = (fieldId: string): Promise<FieldIrrigationAdvice> =>
  kongApi.get<FieldIrrigationAdvice>(`/api/v1/fields/${fieldId}/weather/irrigation-advice`).then(r => r.data);

export const getFieldIrrigationSchedules = (fieldId: string): Promise<FieldIrrigationSchedule[]> =>
  kongApi.get<FieldIrrigationSchedule[]>('/api/v1/irrigation/schedules', { params: { field_id: fieldId } }).then(r => (Array.isArray(r.data) ? r.data : []));
