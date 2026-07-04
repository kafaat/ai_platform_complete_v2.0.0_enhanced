import type { FieldImageryDateOption } from '../services/api';
import { summarizeImageryFreshness } from './fieldViewActionDeck';

export type FieldViewGovernanceStatus = 'ready' | 'degraded' | 'missing';
export type FieldViewGovernanceSeverity = 'ok' | 'info' | 'warn' | 'critical';
export type FieldViewGraphNodeKind = 'field' | 'imagery' | 'weather' | 'alerts' | 'tasks' | 'records' | 'agent' | 'context';

export interface FieldViewGovernanceInput {
  fieldId?: string | null;
  fieldName?: string | null;
  crop?: string | null;
  areaHa?: number | null;
  imageryDates?: FieldImageryDateOption[];
  weatherReady?: boolean;
  activeAlertsCount?: number;
  openTasksCount?: number;
  agentContextReady?: boolean;
  routeFieldIsInvalid?: boolean;
  storedFieldIsInvalid?: boolean;
}

export interface FieldViewGovernanceSource {
  id: FieldViewGraphNodeKind;
  label: string;
  status: FieldViewGovernanceStatus;
  severity: FieldViewGovernanceSeverity;
  evidence: string;
  action?: string;
}

export interface FieldViewGraphNode {
  id: string;
  kind: FieldViewGraphNodeKind;
  label: string;
  status: FieldViewGovernanceStatus;
}

export interface FieldViewGraphEdge {
  from: string;
  to: string;
  relation: 'drives' | 'explains' | 'guards' | 'enriches';
}

export interface FieldViewGovernanceResult {
  score: number;
  severity: FieldViewGovernanceSeverity;
  summary: string;
  sources: FieldViewGovernanceSource[];
  graph: { nodes: FieldViewGraphNode[]; edges: FieldViewGraphEdge[] };
}

function severityScore(source: FieldViewGovernanceSource): number {
  if (source.severity === 'critical') return 0;
  if (source.severity === 'warn') return 55;
  if (source.severity === 'info') return 78;
  return 100;
}

function overallSeverity(score: number): FieldViewGovernanceSeverity {
  if (score < 45) return 'critical';
  if (score < 70) return 'warn';
  if (score < 88) return 'info';
  return 'ok';
}

export function evaluateFieldViewGovernance(input: FieldViewGovernanceInput, nowMs = Date.now()): FieldViewGovernanceResult {
  const imagery = summarizeImageryFreshness(input.imageryDates ?? [], nowMs);
  const sources: FieldViewGovernanceSource[] = [];
  const hasField = !!input.fieldId;
  const staleImagery = imagery.newestAgeDays != null && imagery.newestAgeDays > 14;
  const hasWeakRecords = !input.crop || input.crop === '—' || !input.areaHa || input.areaHa <= 0;

  sources.push({
    id: 'field',
    label: 'الحقل النشط',
    status: hasField ? 'ready' : 'missing',
    severity: hasField ? 'ok' : 'critical',
    evidence: hasField ? `field=${input.fieldName ?? input.fieldId}` : 'لا يوجد field_id نشط',
    action: hasField ? undefined : 'اختر حقلاً قبل تشغيل التحليل',
  });

  sources.push({
    id: 'imagery',
    label: 'صور Sentinel/Timeline',
    status: imagery.total === 0 ? 'missing' : staleImagery ? 'degraded' : 'ready',
    severity: imagery.total === 0 ? 'warn' : staleImagery ? 'warn' : 'ok',
    evidence: imagery.total === 0 ? '0 scenes' : `latest=${imagery.newestDate} ready=${imagery.readyCount}/${imagery.total}`,
    action: imagery.total === 0 || staleImagery ? 'حدّث Timeline أو شغّل backfill' : undefined,
  });

  sources.push({
    id: 'weather',
    label: 'الطقس التشغيلي',
    status: input.weatherReady ? 'ready' : 'degraded',
    severity: input.weatherReady ? 'ok' : 'info',
    evidence: input.weatherReady ? 'forecast=current' : 'forecast=pending-or-fallback',
    action: input.weatherReady ? undefined : 'انتظر تحديث الطقس أو راجع مصدر المزود',
  });

  sources.push({
    id: 'alerts',
    label: 'التنبيهات والاستكشاف',
    status: typeof input.activeAlertsCount === 'number' ? 'ready' : 'degraded',
    severity: (input.activeAlertsCount ?? 0) >= 3 ? 'warn' : 'ok',
    evidence: `active=${input.activeAlertsCount ?? 0}`,
    action: (input.activeAlertsCount ?? 0) > 0 ? 'ابدأ الجولة من التنبيهات' : undefined,
  });

  sources.push({
    id: 'tasks',
    label: 'المهام والعمليات',
    status: typeof input.openTasksCount === 'number' ? 'ready' : 'degraded',
    severity: 'ok',
    evidence: `open=${input.openTasksCount ?? 0}`,
    action: (input.openTasksCount ?? 0) > 0 ? 'راجع الأعمال المفتوحة' : undefined,
  });

  sources.push({
    id: 'records',
    label: 'سجل الحقل',
    status: hasWeakRecords ? 'degraded' : 'ready',
    severity: hasWeakRecords ? 'warn' : 'ok',
    evidence: `crop=${input.crop ?? '—'} area=${input.areaHa ?? 0}`,
    action: hasWeakRecords ? 'أكمل المحصول والمساحة' : undefined,
  });

  sources.push({
    id: 'agent',
    label: 'سياق الوكيل الزراعي',
    status: input.agentContextReady === false ? 'degraded' : 'ready',
    severity: input.agentContextReady === false ? 'info' : 'ok',
    evidence: input.agentContextReady === false ? 'context-pack=partial' : 'context-pack=field-aware',
    action: input.agentContextReady === false ? 'أرسل field_id واسم الحقل مع الطلب' : undefined,
  });

  sources.push({
    id: 'context',
    label: 'سلامة FieldView',
    status: input.routeFieldIsInvalid || input.storedFieldIsInvalid ? 'degraded' : 'ready',
    severity: input.routeFieldIsInvalid || input.storedFieldIsInvalid ? 'info' : 'ok',
    evidence: `routeInvalid=${!!input.routeFieldIsInvalid} storedInvalid=${!!input.storedFieldIsInvalid}`,
    action: input.routeFieldIsInvalid || input.storedFieldIsInvalid ? 'تمت مطابقة السياق تلقائياً' : undefined,
  });

  const score = Math.round(sources.reduce((sum, source) => sum + severityScore(source), 0) / sources.length);
  const severity = overallSeverity(score);
  const weakest = sources.filter((source) => source.severity === 'critical' || source.severity === 'warn').slice(0, 2);
  const summary = weakest.length
    ? `ثقة FieldView ${score}% — يحتاج: ${weakest.map((s) => s.label).join('، ')}`
    : `ثقة FieldView ${score}% — المصادر الأساسية متناسقة`;

  const nodes: FieldViewGraphNode[] = sources.map((source) => ({ id: source.id, kind: source.id, label: source.label, status: source.status }));
  const edges: FieldViewGraphEdge[] = [
    { from: 'field', to: 'imagery', relation: 'drives' },
    { from: 'field', to: 'weather', relation: 'drives' },
    { from: 'imagery', to: 'alerts', relation: 'explains' },
    { from: 'alerts', to: 'tasks', relation: 'drives' },
    { from: 'records', to: 'agent', relation: 'enriches' },
    { from: 'context', to: 'agent', relation: 'guards' },
  ];

  return { score, severity, summary, sources, graph: { nodes, edges } };
}
