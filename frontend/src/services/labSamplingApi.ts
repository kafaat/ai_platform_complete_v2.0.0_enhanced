// ═══════════════════════════════════════════════════════════════
// labSamplingApi.ts — مجال أخذ العيّنات المخبريّة ومناطق الإنتاجيّة (مُستخرَج من api.ts)
// نقاط عيّنات التربة/الماء + نتائج المختبر + مناطق الإنتاجيّة المُلهَمة بـOneSoil + خطّة
// أخذ العيّنات حسب المناطق + الموجز اليوميّ المدعوم بالذكاء. كلّها تستعمل عميل kongApi
// (بوّابة Kong) بلا mock ولا fallback مُلفّق — منصّة قرار زراعيّ. api.ts يعيد التصدير
// عبر `export *` فيبقى كلّ import من '.../services/api' يعمل. السلوك محفوظ حرفيّاً.
// ═══════════════════════════════════════════════════════════════

import { kongApi } from './apiClients';

// ── Lab Sampling: soil/water sample points + laboratory results ─────────────
// Inspired by OneSoil soil-sampling map best practice: point coordinates are first-class
// data and the map layer reads the same API as forms/reports. No fabricated fallback.
export type LabSampleKind = 'soil' | 'water';
export type LabSampleStatus = 'planned' | 'collected' | 'submitted' | 'analyzed' | 'approved';
export interface LabSampleRecord {
  sample_id: string;
  field_id: string;
  kind: LabSampleKind;
  latitude: number;
  longitude: number;
  sampled_on?: string | null;
  depth_cm_from?: number | null;
  depth_cm_to?: number | null;
  source?: string | null;
  status: LabSampleStatus;
  gps_accuracy_m?: number | null;
  ph?: number | null;
  ec_dsm?: number | null;
  organic_matter_pct?: number | null;
  nitrogen_mg_kg?: number | null;
  phosphorus_mg_kg?: number | null;
  potassium_mg_kg?: number | null;
  sar?: number | null;
  rsc_meq_l?: number | null;
  approved?: boolean;
}
export interface LabSampleCreateInput {
  field_id: string;
  kind: LabSampleKind;
  latitude: number;
  longitude: number;
  sampled_on?: string | null;
  depth_cm_from?: number | null;
  depth_cm_to?: number | null;
  source?: string | null;
  status?: LabSampleStatus;
  gps_accuracy_m?: number | null;
}
export interface SoilLabResultInput {
  sample_id: string;
  ph?: number | null;
  ec_dsm?: number | null;
  organic_matter_pct?: number | null;
  nitrogen_mg_kg?: number | null;
  phosphorus_mg_kg?: number | null;
  potassium_mg_kg?: number | null;
  cec_cmol_kg?: number | null;
  calcium_carbonate_pct?: number | null;
  texture?: string | null;
  approved?: boolean;
}
export interface SoilLabAnalysisResult {
  sample_id: string;
  approved: boolean;
  classification: Record<string, { class: string | null; note_ar?: string }>;
  nutrients: Record<string, string | number | null>;
  hazard_flags_ar: string[];
  missing_inputs: string[];
  data_complete: boolean;
  decision_usable: boolean;
}
export interface LabDecisionContext {
  soil_lab_ready_for_fertilizer: boolean;
  water_lab_available: boolean;
  blockers_ar: string[];
  warnings_ar: string[];
  recommendation_gate: 'allow' | 'needs_review' | string;
}
export const listLabSamples = (fieldId?: string): Promise<LabSampleRecord[]> =>
  kongApi
    .get<LabSampleRecord[]>('/api/v1/lab/samples', { params: fieldId ? { field_id: fieldId } : undefined })
    .then(r => Array.isArray(r.data) ? r.data : []);
export const createLabSample = (payload: LabSampleCreateInput): Promise<LabSampleRecord> =>
  kongApi.post<LabSampleRecord>('/api/v1/lab/samples', payload).then(r => r.data);
export const submitSoilLabResult = (payload: SoilLabResultInput): Promise<SoilLabAnalysisResult> =>
  kongApi.post<SoilLabAnalysisResult>('/api/v1/lab/soil-results', payload).then(r => r.data);
export const fetchLabDecisionContext = (fieldId: string): Promise<LabDecisionContext> =>
  kongApi.get<LabDecisionContext>(`/api/v1/fields/${encodeURIComponent(fieldId)}/lab-context`).then(r => r.data);


// ── OneSoil-inspired productivity zones / sampling / daily brief ───────────
export type ProductivityZoneClass = 'low' | 'medium' | 'high' | 'problem';
export type ActionPriority = 'critical' | 'high' | 'medium' | 'low';
export interface ProductivityObservationInput {
  id: string;
  area_ha: number;
  ndvi_mean?: number | null;
  ndvi_cv?: number | null;
  yield_rel?: number | null;
  soil_ec_dsm?: number | null;
  soil_ph?: number | null;
  lat?: number | null;
  lng?: number | null;
}
export interface ProductivityZoneResult {
  field_id: string;
  tenant_id?: string;
  zones: Array<{
    zone_id: string;
    zone_class: ProductivityZoneClass;
    area_ha: number;
    observation_ids: string[];
    score: number;
    confidence: number;
    limiting_factors_ar: string[];
    sampling_priority: ActionPriority;
  }>;
  summary: Record<string, { area_ha: number; count: number; area_pct: number; mean_score: number; limiting_factors_ar: string[] }>;
  total_area_ha: number;
  mean_confidence: number;
  data_sufficiency: 'sufficient' | 'limited' | string;
  source_policy?: string;
}
export interface ZoneSamplingPlanResult {
  field_id: string;
  tenant_id?: string;
  sample_points: Array<{
    sample_id: string;
    zone_id: string;
    zone_class: ProductivityZoneClass;
    latitude: number;
    longitude: number;
    depth_cm_from: number;
    depth_cm_to: number;
    priority: ActionPriority;
    reason_ar: string;
  }>;
  unplaceable_observation_ids: string[];
  count: number;
  source_policy?: string;
}
export interface DailyAiBriefResult {
  field_id?: string | null;
  tenant_id?: string;
  headline_ar: string;
  actions: Array<{
    action_id: string;
    priority: ActionPriority;
    title_ar: string;
    reason_ar: string;
    field_id?: string | null;
    zone_id?: string | null;
    source: string;
  }>;
  source_count: number;
  is_grounded: boolean;
  source_policy?: string;
}
export const buildProductivityZones = (fieldId: string, observations: ProductivityObservationInput[]): Promise<ProductivityZoneResult> =>
  kongApi
    .post<ProductivityZoneResult>(`/api/v1/fields/${encodeURIComponent(fieldId)}/productivity-zones`, { field_id: fieldId, observations })
    .then(r => r.data);
export const buildZoneSamplingPlan = (fieldId: string, observations: ProductivityObservationInput[]): Promise<ZoneSamplingPlanResult> =>
  kongApi
    .post<ZoneSamplingPlanResult>(`/api/v1/fields/${encodeURIComponent(fieldId)}/zone-sampling-plan`, { field_id: fieldId, observations })
    .then(r => r.data);
export const fetchDailyAiBrief = (fieldId: string, signals: Record<string, unknown> = {}, tasks: Record<string, unknown>[] = []): Promise<DailyAiBriefResult> =>
  kongApi
    .post<DailyAiBriefResult>(`/api/v1/fields/${encodeURIComponent(fieldId)}/daily-ai-brief`, { field_id: fieldId, signals, tasks })
    .then(r => r.data);
