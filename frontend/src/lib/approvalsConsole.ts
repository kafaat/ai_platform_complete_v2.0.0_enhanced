// Approvals Console — يوحّد الموافقات البشريّة المعلّقة في شاشة مدير واحدة:
// (١) طلبات أدوات وكيل AI المعلّقة (v58: الوكيل لا يُنفّذ mutating بلا موافقة —
//     كانت مرئيّة فقط داخل رسالة المحادثة التي أنشأتها) و(٢) قرارات التوزيع
// المحروسة بحالة pending_approval. صدق: الموافِق المسجَّل هو هويّة البوّابة
// الموثوقة (SEC-3.1) لا حقل body؛ والمخاطر تُلوَّن للقيم المعروفة فقط.

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

const RISK_COLOR: Record<string, string> = {
  low: '#86efac',
  medium: '#fde68a',
  high: '#fdba74',
  critical: '#fca5a5',
};

export function riskColor(risk: string | null | undefined): string {
  return risk ? (RISK_COLOR[risk.toLowerCase()] ?? '#64748b') : '#64748b';
}

/** معرّف عرض ثابت للطلب — id ثمّ tool (نفس منطق ChatbotPage) ثمّ «طلب». */
export function approvalKey(a: PendingAgentApproval): string {
  return a.id || a.tool || 'approval';
}

/** قرارات التوزيع المنتظِرة موافقة فقط — من حالة الخادم كما هي. */
export function pendingDispatchDecisions(decisions: DispatchDecision[] | null | undefined): DispatchDecision[] {
  return (decisions ?? []).filter((d) => d.state === 'pending_approval');
}

/** ملخّص وسائط مقتضب للعرض (المفاتيح فقط — القيم قد تكون حسّاسة/طويلة). */
export function paramsSummary(params: Record<string, unknown> | null | undefined, limit = 4): string {
  const keys = Object.keys(params ?? {});
  if (keys.length === 0) return '—';
  const shown = keys.slice(0, limit).join('، ');
  return keys.length > limit ? `${shown} … (+${keys.length - limit})` : shown;
}
