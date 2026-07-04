// Decision Runtime Console — يعكس محرّك توزيع القرار المحروس المُخزَّن (dispatch
// decisions/queue/ledger + policies) في الواجهة — كان 20 مساراً بلا أيّ قارئ (P0
// في تدقيق المستخدم). صدق: الحالات (blocked/pending_approval/ready) والخروق
// والأسباب كلّها من الخادم؛ الميزة خلف علم SAHOOL_DECISION_DISPATCH (404 ⇒ حالة
// «غير مفعّلة» صادقة)؛ والكونسول قراءة + معاينة dry-run فقط — التنفيذ الفعليّ يبقى
// عبر مسار الموافقات/المشغِّل (فلسفة v58: mutating يتطلّب موافقة).

export interface DispatchDecision {
  decision_id: string;
  recommendation_id: string;
  action_type: string;
  field_id: string | null;
  state: 'blocked' | 'pending_approval' | 'ready' | string;
  risk_level: string;
  required_approvals: number;
  approvals_collected: number;
  halt_breaches: unknown[];
  warn_breaches: unknown[];
  reason_ar: string | null;
  exec_status: string | null;
  created_at: string | null;
}

export interface DispatchQueueResponse {
  queued: DispatchDecision[];
  count: number;
  disabled?: boolean;
}

export interface DispatchDecisionsResponse {
  decisions?: DispatchDecision[];
  count?: number;
  disabled?: boolean;
}

export interface LedgerEntry {
  ledger_id: string;
  decision_id: string | null;
  action_type: string | null;
  field_id: string | null;
  channel: string | null;
  outcome: string | null;
  note_ar: string | null;
  recorded_at: string | null;
}

export interface DecisionLedgerResponse {
  ledger: LedgerEntry[];
  count: number;
  disabled?: boolean;
}

export interface DecisionPolicy {
  policy_id: string;
  name: string;
  scope: Record<string, unknown>;
  effect: Record<string, unknown>;
  priority: number;
  enabled: boolean;
  created_at: string | null;
}

export interface DecisionPoliciesResponse {
  policies: DecisionPolicy[];
  count: number;
  disabled?: boolean;
}

/** طلب المعاينة (dry-run) — نفس عقد الخادم؛ risk مجهول يعامله الخادم CRITICAL. */
export interface DispatchEvaluateInput {
  recommendation_id: string;
  action_type: string;
  risk_level: string;
  field_id?: string | null;
  approvals_collected?: number;
  has_governing_data?: boolean;
  pesticide_phi_satisfied?: boolean | null;
  zone_factor_calibrated?: boolean;
}

export interface DispatchAudit {
  state?: string;
  halt_breaches?: unknown[];
  warn_breaches?: unknown[];
  required_approvals?: number;
  approvals_collected?: number;
  reason_ar?: string | null;
  dry_run?: boolean;
  [k: string]: unknown;
}

const STATE_AR: Record<string, string> = {
  blocked: 'محجوب',
  pending_approval: 'بانتظار موافقة',
  ready: 'جاهز',
};

export function dispatchStateLabel(state: string | null | undefined): string {
  return state ? (STATE_AR[state] ?? state) : '—';
}

export function dispatchStateColor(state: string | null | undefined): string {
  if (state === 'ready') return '#86efac';
  if (state === 'pending_approval') return '#fde68a';
  if (state === 'blocked') return '#fca5a5';
  return '#64748b';
}

export interface DecisionsOverview {
  total: number;
  blocked: number;
  pendingApproval: number;
  ready: number;
}

/** عدّادات حالات القرارات من الخادم كما هي — حالة غريبة تُحصى في total فقط. */
export function summarizeDecisions(decisions: DispatchDecision[] | null | undefined): DecisionsOverview {
  const o: DecisionsOverview = { total: 0, blocked: 0, pendingApproval: 0, ready: 0 };
  for (const d of decisions ?? []) {
    o.total += 1;
    if (d.state === 'blocked') o.blocked += 1;
    else if (d.state === 'pending_approval') o.pendingApproval += 1;
    else if (d.state === 'ready') o.ready += 1;
  }
  return o;
}
