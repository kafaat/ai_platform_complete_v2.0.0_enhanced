import type { FieldViewGovernanceResult, FieldViewGovernanceSource } from './fieldViewGovernance';

export type DecisionScriptStepKind = 'read' | 'inspect' | 'act' | 'review';

export interface FieldViewDecisionScriptStep {
  id: string;
  kind: DecisionScriptStepKind;
  title: string;
  evidence: string;
  startMs: number;
  endMs: number;
  gate: 'pass' | 'warn' | 'block';
}

export interface FieldViewDecisionScript {
  title: string;
  compactMarkdown: string;
  steps: FieldViewDecisionScriptStep[];
  selfReview: string[];
}

function gate(source: FieldViewGovernanceSource): 'pass' | 'warn' | 'block' {
  if (source.severity === 'critical') return 'block';
  if (source.severity === 'warn') return 'warn';
  return 'pass';
}

function kind(source: FieldViewGovernanceSource): DecisionScriptStepKind {
  if (source.id === 'field' || source.id === 'context') return 'read';
  if (source.id === 'imagery' || source.id === 'weather') return 'inspect';
  if (source.id === 'alerts' || source.id === 'tasks') return 'act';
  return 'review';
}

export function buildFieldViewDecisionScript(result: FieldViewGovernanceResult): FieldViewDecisionScript {
  const steps = result.sources.map((source, index): FieldViewDecisionScriptStep => {
    const startMs = index * 1000;
    return {
      id: `step-${source.id}`,
      kind: kind(source),
      title: source.label,
      evidence: source.evidence,
      startMs,
      endMs: startMs + 900,
      gate: gate(source),
    };
  });
  const blockers = steps.filter((step) => step.gate === 'block');
  const warnings = steps.filter((step) => step.gate === 'warn');
  const selfReview = [
    blockers.length ? `BLOCK: ${blockers.map((s) => s.title).join('، ')}` : 'لا توجد بوابة حظر.',
    warnings.length ? `WARN: ${warnings.map((s) => s.title).join('، ')}` : 'لا توجد بوابات تحذير عالية.',
    `SCORE: ${result.score}%`,
    'لا تُصدر توصية تنفيذية إن كان field_id أو الصور أو السجل ناقصاً دون توضيح السبب.',
  ];
  const compactMarkdown = [
    `# FieldView Decision Script`,
    `summary: ${result.summary}`,
    ...steps.map((step) => `- [${step.gate}] ${step.title}: ${step.evidence}`),
    `self_review: ${selfReview.join(' | ')}`,
  ].join('\n');
  return { title: 'FieldView Decision Script', compactMarkdown, steps, selfReview };
}
