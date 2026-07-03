import { describe, expect, it } from 'vitest';
import { evaluateFieldViewGovernance } from './fieldViewGovernance';
import { buildFieldViewDecisionScript } from './fieldViewDecisionScript';

describe('buildFieldViewDecisionScript', () => {
  it('يبني سكربت قرار مضغوط من حوكمة FieldView', () => {
    const governance = evaluateFieldViewGovernance({ fieldId: 'F-1', crop: 'wheat', areaHa: 12, weatherReady: true, agentContextReady: true }, Date.parse('2026-07-04T00:00:00Z'));
    const script = buildFieldViewDecisionScript(governance);
    expect(script.steps.length).toBe(governance.sources.length);
    expect(script.compactMarkdown).toContain('FieldView Decision Script');
    expect(script.selfReview.some((line) => line.startsWith('SCORE:'))).toBe(true);
  });
});
