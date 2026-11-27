import { getAuthScope } from '../../lib/authStorage';
import { kongApi } from './client';

export type InspectionExecutionState = 'queued' | 'delivering' | 'accepted' | 'verified_success' | 'blocked';
export type InspectionExecution = {
  execution_request_id: string;
  field_id: string;
  decision_id: string;
  task_id: string | null;
  pin_id?: string;
  assigned_to?: string;
  assignee_name?: string | null;
  due_at?: string;
  state: InspectionExecutionState;
  can_receive: boolean;
  can_verify: boolean;
  verification_reason?: unknown;
  reason?: unknown;
  outcome_id?: string | null;
};
export type InspectionExecutionInbox = {
  field_id: string;
  items: InspectionExecution[];
  truncated: boolean;
  limit: number;
};
export type InspectionRequestScope = { authScope: string; signal?: AbortSignal };
export type InspectionExecutionReceipt = {
  state: 'accepted'; persisted: true; replayed: boolean;
  execution_request_id: string; task_id: string; field_id: string;
  receipt_id: string; physical_execution_verified: false;
};
export type InspectionOutcomeReceipt = {
  state: 'verified_success'; persisted: true; replayed: boolean;
  execution_request_id: string; task_id: string; outcome_id: string;
  evidence_snapshot_id: string; verified_at: string;
};

const states = new Set(['queued', 'delivering', 'accepted', 'verified_success', 'blocked']);
const invalid = () => new Error('تعذّر التحقق من استجابة خدمة مهام التفتيش.');
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw invalid();
  return value as Record<string, unknown>;
}
function text(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}
function current(scope: InspectionRequestScope) {
  if (!scope.authScope || getAuthScope() !== scope.authScope || scope.signal?.aborted) {
    throw new Error('تغيّرت الجلسة؛ أعد فتح مهام الحقل.');
  }
}
function config(scope: InspectionRequestScope) {
  current(scope);
  return { expectedAuthScope: scope.authScope, signal: scope.signal };
}
function fieldPath(fieldId: string) {
  if (!text(fieldId)) throw invalid();
  return '/api/v1/inspection-executions/fields/' + encodeURIComponent(fieldId);
}

export async function getInspectionExecutions(fieldId: string, scope: InspectionRequestScope): Promise<InspectionExecutionInbox> {
  const response = await kongApi.get<unknown>(fieldPath(fieldId), {
    ...config(scope), params: { limit: 50 },
  });
  current(scope);
  const data = object(response.data);
  if (data.field_id !== fieldId || !Array.isArray(data.items) || typeof data.truncated !== 'boolean' ||
      !Number.isInteger(data.limit) || Number(data.limit) < 1 || Number(data.limit) > 100 || data.items.length > Number(data.limit)) throw invalid();
  const seen = new Set<string>();
  const items = data.items.map(value => {
    const row = object(value);
    if (!text(row.execution_request_id) || seen.has(row.execution_request_id) || row.field_id !== fieldId ||
        !text(row.decision_id) || !states.has(String(row.state)) ||
        typeof row.can_receive !== 'boolean' || typeof row.can_verify !== 'boolean' ||
        !(row.task_id === null || text(row.task_id)) ||
        (row.state === 'accepted' && !text(row.task_id)) ||
        (row.can_verify && (row.state !== 'accepted' || !text(row.task_id))) ||
        (row.can_receive && !['queued', 'delivering'].includes(String(row.state))) ||
        (row.state === 'verified_success' && (!text(row.task_id) || !text(row.outcome_id)))) throw invalid();
    for (const key of ['pin_id', 'assigned_to', 'due_at']) {
      if (row[key] !== undefined && !text(row[key])) throw invalid();
    }
    if (row.assignee_name !== undefined && row.assignee_name !== null && typeof row.assignee_name !== 'string') throw invalid();
    seen.add(row.execution_request_id);
    return row as InspectionExecution;
  });
  return { field_id: fieldId, items, truncated: data.truncated, limit: Number(data.limit) };
}

export async function receiveInspectionExecution(fieldId: string, requestId: string, scope: InspectionRequestScope): Promise<InspectionExecutionReceipt> {
  if (!text(requestId)) throw invalid();
  const response = await kongApi.post<unknown>(
    fieldPath(fieldId) + '/requests/' + encodeURIComponent(requestId) + '/receive', {}, config(scope),
  );
  current(scope);
  const data = object(response.data);
  if (data.state !== 'accepted' || data.persisted !== true || typeof data.replayed !== 'boolean' ||
      data.execution_request_id !== requestId || data.field_id !== fieldId || !text(data.task_id) ||
      !text(data.receipt_id) || data.physical_execution_verified !== false) throw invalid();
  return data as InspectionExecutionReceipt;
}

export async function verifyInspectionExecution(fieldId: string, taskId: string, requestId: string, scope: InspectionRequestScope): Promise<InspectionOutcomeReceipt> {
  if (!text(taskId) || !text(requestId)) throw invalid();
  const response = await kongApi.post<unknown>(
    fieldPath(fieldId) + '/tasks/' + encodeURIComponent(taskId) + '/verify', {}, config(scope),
  );
  current(scope);
  const data = object(response.data);
  if (data.state !== 'verified_success' || data.persisted !== true || typeof data.replayed !== 'boolean' ||
      data.execution_request_id !== requestId || data.task_id !== taskId || !text(data.outcome_id) ||
      !text(data.evidence_snapshot_id) || !text(data.verified_at)) throw invalid();
  return data as InspectionOutcomeReceipt;
}

export function inspectionReason(value: unknown): string | undefined {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && 'code' in value && typeof value.code === 'string') return value.code;
  return undefined;
}
export function inspectionErrorStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null)?.response?.status;
}
export function inspectionInboxHidden(error: unknown): boolean {
  const response = (error as { response?: { data?: { detail?: unknown } } } | null)?.response;
  const status = inspectionErrorStatus(error);
  return status === 401 || status === 403 ||
    (status === 503 && inspectionReason(response?.data?.detail) === 'field_inspection_execution_disabled');
}
