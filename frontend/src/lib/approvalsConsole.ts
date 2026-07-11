// Approvals Console — يوحّد الموافقات البشريّة المعلّقة في شاشة مدير واحدة:
// (١) طلبات أدوات وكيل AI المعلّقة (v58) و(٢) قرارات التوزيع المحروسة بحالة
// pending_approval و(٣، WX-10.8) مرشّحات القرار الآمِرة المعلّقة. صدق: الموافِق المسجَّل
// هو هويّة البوّابة الموثوقة (SEC-3.1) لا حقل body؛ والأدلّة تُلخَّص بلا تسلسل الحمولة كاملةً.

import type { DispatchDecision } from './decisionRuntime';

export interface PendingAgentApproval {
  id?: string;
  tool?: string;
  risk?: string;
  status?: string;
  params?: Record<string, unknown>;
  capability?: string;
  tenant_id?: string;
  requested_at?: string;
}

export interface PendingApprovalsResponse {
  pending: PendingAgentApproval[];
  count: number;
  disabled?: boolean;
}

export interface DecisionReviewCandidate {
  decision_id: string;
  field_id?: string | null;
  decision_type?: string | null;
  region?: string | null;
  stage: 'candidate';
  decision_value?: Record<string, unknown> | null;
  confidence?: number | null;
  review_state: 'pending_approval';
  candidate_lineage_id: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DecisionReviewQueueResponse {
  authoritative: true;
  persisted: true;
  items: DecisionReviewCandidate[];
  count: number;
}

export interface DecisionReviewInput {
  decisionId: string;
  action: 'approve' | 'reject';
  reason: string;
  candidateLineageId: string;
  idempotencyKey: string;
}

export interface DecisionReviewResult {
  authoritative: true;
  persisted: true;
  decision_id: string;
  previous_state: 'pending_approval';
  state: 'approved' | 'rejected';
  review_id: string;
  reviewed_by: string;
  reviewed_at: string;
  candidate_lineage_id: string;
  replay?: boolean;
}

const RISK_COLOR: Record<string, string> = {
  low: '#86efac',
  medium: '#fde68a',
  high: '#fdba74',
  critical: '#fca5a5',
};

export function riskColor(risk: string | null | undefined): string {
  return risk ? (RISK_COLOR[risk.toLowerCase()] ?? '#64748b') : '#64748b';
}

export function approvalKey(a: PendingAgentApproval): string {
  return a.id || a.tool || 'approval';
}

export function pendingDispatchDecisions(decisions: DispatchDecision[] | null | undefined): DispatchDecision[] {
  return (decisions ?? []).filter((d) => d.state === 'pending_approval');
}

export function paramsSummary(params: Record<string, unknown> | null | undefined, limit = 4): string {
  const keys = Object.keys(params ?? {});
  if (keys.length === 0) return '—';
  const shown = keys.slice(0, limit).join('، ');
  return keys.length > limit ? `${shown} … (+${keys.length - limit})` : shown;
}

/** Safe, concise evidence preview. Never serializes the full candidate payload into the UI. */
export function candidateEvidenceSummary(value: Record<string, unknown> | null | undefined): string {
  if (!value) return 'لا توجد خلاصة أدلة';
  const ci = value.crop_intelligence;
  if (ci && typeof ci === 'object') {
    const record = ci as Record<string, unknown>;
    const label = record.summary ?? record.recommendation ?? record.stage ?? record.status;
    if (typeof label === 'string' && label.trim()) return label.trim().slice(0, 180);
  }
  const limitations = value.limitations;
  if (Array.isArray(limitations) && limitations.length > 0) {
    return `قيود: ${limitations.slice(0, 3).map(String).join('، ')}`.slice(0, 180);
  }
  return `حقول الدليل: ${paramsSummary(value, 5)}`;
}

export function newReviewIdempotencyKey(decisionId: string): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  return `review-ui-${decisionId}-${uuid ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
}
