import { kongApi } from './client';
import type { DecisionReviewCandidate } from '../../lib/approvalsConsole';
import type { IrrigationRecommendationResponse } from '../../hooks/useFieldIrrigationRecommendation';

export interface ManualWorkflowCandidate extends Omit<DecisionReviewCandidate, 'review_state'> {
  review_state: 'pending_approval' | 'approved';
  review?: ApprovedIrrigationReview | null;
  execution_plan?: { execution_plan_id: string; decision_id: string; review_id: string; candidate_lineage_id: string; decision_value_digest: string; plan_state: string; plan_digest: string } | null;
}

export interface ManualIrrigationIntent {
  season_id: string; system_id: string; irrigated_area_ha: number; application_efficiency: number;
  source_reference: string; observed_at: string; valid_from: string; valid_until: string;
}

export interface ApprovedIrrigationReview {
  state: 'approved';
  previous_state: 'pending_approval';
  reviewed_by: string;
  reviewed_at: string;
  decision_id: string;
  review_id: string;
  candidate_lineage_id: string;
  decision_value_digest: string;
}

export interface ManualPlanSource {
  schema_version: 'manual-irrigation-source/v1';
  net_depth_mm: number;
  application_efficiency: number;
  irrigated_area_ha: number;
  specification_digest: string;
  specification: { evidence_level: string; source_reference: string; observed_at: string };
  water_truth: { canonical: { ledger_date: string; operational_eligible: boolean }; applied_water_status: string };
  field_id: string;
  season_id: string;
  system_id: string;
  target_depth_mm: number;
  target_volume_m3: number;
  water_truth_digest: string;
  valid_from: string;
  valid_until: string;
}

const sha256 = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
const nonempty = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
const positive = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0;

/** Only server-returned, version-bound inputs may populate an execution plan.
 * Existing simple candidates omit this source: they remain blocked, never backfilled
 * from browser guesses, water balance zeros, or pasted JSON. */
export function manualPlanSource(candidate: ManualWorkflowCandidate, fieldId: string, seasonId: string): ManualPlanSource | null {
  const value = candidate.decision_value;
  const source = value?.manual_execution_source as Partial<ManualPlanSource> | undefined;
  const recommendation = value?.recommendation as { should_irrigate?: unknown; target_refill_mm?: unknown } | undefined;
  if (candidate.decision_type !== 'irrigation' || candidate.field_id !== fieldId || value?.season_id !== seasonId
    || !source || source.schema_version !== 'manual-irrigation-source/v1' || source.field_id !== fieldId || source.season_id !== seasonId || !nonempty(source.system_id)
    || !positive(source.target_depth_mm) || !positive(source.target_volume_m3) || !sha256(source.water_truth_digest)
    || !nonempty(source.valid_from) || !nonempty(source.valid_until)
    || !Number.isFinite(Date.parse(source.valid_from)) || !Number.isFinite(Date.parse(source.valid_until))
    || Date.parse(source.valid_until) <= Date.parse(source.valid_from) || Date.parse(source.valid_until) <= Date.now()
    || recommendation?.should_irrigate !== true || !positive(recommendation.target_refill_mm)
    || source.net_depth_mm !== recommendation.target_refill_mm || !positive(source.application_efficiency)
    || source.application_efficiency > 1 || !positive(source.irrigated_area_ha) || !sha256(source.specification_digest)
    || source.specification?.evidence_level !== 'user_declared' || !nonempty(source.specification.source_reference)
    || source.water_truth?.canonical?.operational_eligible !== true || source.water_truth.applied_water_status !== 'recorded'
    || Math.abs(source.target_depth_mm - source.net_depth_mm / source.application_efficiency) > 1e-8
    || Math.abs(source.target_volume_m3 - source.target_depth_mm * source.irrigated_area_ha * 10) > 1e-8) return null;
  return source as ManualPlanSource;
}

export async function submitIrrigationCandidate(fieldId: string, intent: ManualIrrigationIntent): Promise<IrrigationRecommendationResponse> {
  const { data } = await kongApi.post(`/api/v1/fields/${encodeURIComponent(fieldId)}/irrigation-recommendation`, { submit_to_decision: true, manual_execution: intent });
  return data;
}

export async function loadManualCandidates(fieldId: string, seasonId: string): Promise<ManualWorkflowCandidate[]> {
  const { data } = await kongApi.get('/api/v1/decisions/review-queue', { params: { field_id: fieldId, season_id: seasonId } });
  if (data?.authoritative !== true || data?.persisted !== true || !Array.isArray(data.items) || data.count !== data.items.length) {
    throw new Error('لم يؤكد الخادم قائمة قرارات موثوقة.');
  }
  return data.items.filter((item: ManualWorkflowCandidate) => item.decision_type === 'irrigation'
    && item.field_id === fieldId && item.decision_value?.season_id === seasonId && item.stage === 'candidate' && ['pending_approval', 'approved'].includes(item.review_state));
}

export async function approveManualCandidate(candidate: ManualWorkflowCandidate): Promise<ApprovedIrrigationReview> {
  if (!sha256(candidate.decision_value_digest) || !nonempty(candidate.candidate_lineage_id)
    || candidate.review_state !== 'pending_approval') throw new Error('نسخة القرار غير مربوطة بالمراجعة.');
  const { data } = await kongApi.post(`/api/v1/decisions/${encodeURIComponent(candidate.decision_id)}/review`, {
    action: 'approve', expected_state: 'pending_approval', reason: 'مراجعة الري اليدوي من مساحة الحقل',
    candidate_lineage_id: candidate.candidate_lineage_id,
    decision_value_digest: candidate.decision_value_digest,
    idempotency_key: `manual-review:${candidate.decision_id}:${candidate.decision_value_digest}`,
  });
  if (!validatedReview(candidate, data)) throw new Error('لم يؤكد الخادم اعتماد هذه النسخة.');
  return data;
}

export function validatedReview(candidate: ManualWorkflowCandidate, data: ApprovedIrrigationReview | null | undefined): data is ApprovedIrrigationReview {
  return data?.state === 'approved' && data.previous_state === 'pending_approval' && data.decision_id === candidate.decision_id
    && data.candidate_lineage_id === candidate.candidate_lineage_id && data.decision_value_digest === candidate.decision_value_digest
    && sha256(data.decision_value_digest) && nonempty(data.review_id) && nonempty(data.reviewed_by) && nonempty(data.reviewed_at);
}

export async function createManualPlan(candidate: ManualWorkflowCandidate, review: ApprovedIrrigationReview, fieldId: string, seasonId: string): Promise<string> {
  const source = manualPlanSource(candidate, fieldId, seasonId);
  if (!source || !validatedReview(candidate, review) || Date.parse(source.valid_until) <= Date.now() || review.decision_id !== candidate.decision_id
    || review.candidate_lineage_id !== candidate.candidate_lineage_id || review.decision_value_digest !== candidate.decision_value_digest) {
    throw new Error('مصدر خطة الري غير مكتمل أو انتهت صلاحيته.');
  }
  const { specification: _spec, water_truth: _water, ...constraints } = source;
  const { valid_from, valid_until } = source;
  const { data } = await kongApi.post(`/api/v1/decisions/${encodeURIComponent(candidate.decision_id)}/execution-plan`, {
    review_id: review.review_id, candidate_lineage_id: review.candidate_lineage_id,
    operation_type: 'manual_irrigation', planned_start: valid_from, planned_end: valid_until,
    constraints, idempotency_key: `manual-plan:${candidate.decision_id}:${review.review_id}`,
  });
  if (data?.state !== 'planned' || data.decision_id !== candidate.decision_id || data.review_id !== review.review_id
    || data.candidate_lineage_id !== review.candidate_lineage_id || !sha256(data.plan_digest) || !nonempty(data.execution_plan_id)) {
    throw new Error('لم يؤكد الخادم خطة ري محفوظة.');
  }
  return data.execution_plan_id;
}

export async function createManualExecutionFromPlan(executionPlanId: string): Promise<{ execution_id: string; state: string; execution_plan_id: string }> {
  const { data } = await kongApi.post('/api/v1/irrigation/engineering/manual-executions', {
    execution_plan_id: executionPlanId, mode: 'manual_measured', idempotency_key: `manual-execution:${executionPlanId}:manual_measured`,
  });
  if (!nonempty(data?.execution_id) || !['recommended', 'approved', 'started', 'stopped', 'confirmed', 'verified', 'reconciled', 'cancelled'].includes(data.state) || data.execution_plan_id !== executionPlanId) {
    throw new Error('لم يؤكد الخادم إنشاء التنفيذ.');
  }
  return data;
}
