import { kongApi } from './client';

export type ManualExecutionState =
  | 'recommended'
  | 'approved'
  | 'started'
  | 'stopped'
  | 'confirmed'
  | 'verified'
  | 'reconciled'
  | 'cancelled';

export type ManualExecutionMode = 'recommendation_only' | 'manual_estimated' | 'manual_measured';

export interface ManualExecutionRecord {
  execution_id: string;
  field_id: string;
  season_id: string;
  system_id: string;
  recommendation_id: string;
  execution_mode: ManualExecutionMode;
  state: ManualExecutionState;
  target_depth_mm: number;
  target_volume_m3: number;
  nominal_flow_m3_h: number | null;
  valid_from: string;
  valid_until: string;
  approved_at?: string | null;
  started_at?: string | null;
  stopped_at?: string | null;
  confirmed_at?: string | null;
  verified_at?: string | null;
  reconciled_at?: string | null;
  completion_ratio?: number | null;
  ledger_eligible: boolean;
  as_applied_digest?: string | null;
  as_applied?: {
    actual_runtime_h?: number;
    actual_volume_m3?: number;
    actual_depth_mm?: number;
    quality?: string;
    blocking_reasons?: string[];
  } | null;
  verification?: { verification_digest?: string; status?: string } | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ManualExecutionConfirmationInput {
  started_at: string;
  stopped_at: string;
  completion_ratio: number;
  meter_start_m3?: number;
  meter_end_m3?: number;
  measured_flow_m3_h?: number;
  manual_volume_m3?: number;
  estimated_flow_m3_h?: number;
  interruptions_minutes: number;
  pressure_bar?: number;
  evidence_digests: string[];
  notes?: string;
}

export interface ManualVerificationInput {
  as_applied_digest: string;
  reviewer_id: string;
  reviewed_at: string;
  evidence_digests: string[];
  volume_verified: boolean;
  timing_verified: boolean;
  field_verified: boolean;
  notes?: string;
}

export async function listManualExecutions(fieldId: string, seasonId?: string | null): Promise<ManualExecutionRecord[]> {
  const { data } = await kongApi.get('/api/v1/irrigation/engineering/manual-executions', {
    params: { field_id: fieldId, ...(seasonId ? { season_id: seasonId } : {}) },
  });
  return Array.isArray(data) ? data : [];
}

export async function transitionManualExecution(executionId: string, targetState: ManualExecutionState): Promise<void> {
  await kongApi.post(`/api/v1/irrigation/engineering/manual-executions/${executionId}/transition`, {
    target_state: targetState,
  });
}

export async function confirmManualExecution(executionId: string, confirmation: ManualExecutionConfirmationInput): Promise<void> {
  await kongApi.post(`/api/v1/irrigation/engineering/manual-executions/${executionId}/confirm`, { confirmation });
}

export async function verifyManualExecution(executionId: string, verification: ManualVerificationInput): Promise<void> {
  await kongApi.post(`/api/v1/irrigation/engineering/manual-executions/${executionId}/verify`, { verification });
}

export async function reconcileManualExecution(executionId: string): Promise<void> {
  await kongApi.post(`/api/v1/irrigation/engineering/manual-executions/${executionId}/reconcile`);
}
