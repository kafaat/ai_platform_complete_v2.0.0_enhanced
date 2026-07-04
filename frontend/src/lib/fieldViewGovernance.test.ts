import { describe, expect, it } from 'vitest';
import { evaluateFieldViewGovernance } from './fieldViewGovernance';

describe('fieldViewGovernance', () => {
  it('builds an explainable source graph for the active field', () => {
    const result = evaluateFieldViewGovernance({
      fieldId: 'f1', fieldName: 'الشمال', crop: 'wheat', areaHa: 12,
      imageryDates: [{ date: '2026-07-01', has_cog: true, cloud_pct: 10 }],
      weatherReady: true, activeAlertsCount: 0, openTasksCount: 1, agentContextReady: true,
    }, Date.parse('2026-07-04T00:00:00Z'));
    expect(result.score).toBeGreaterThanOrEqual(88);
    expect(result.graph.nodes.map((n) => n.id)).toContain('imagery');
    expect(result.graph.edges.some((e) => e.from === 'context' && e.to === 'agent')).toBe(true);
  });

  it('downgrades confidence when records and imagery are incomplete', () => {
    const result = evaluateFieldViewGovernance({ fieldId: 'f1', imageryDates: [], weatherReady: false });
    expect(result.score).toBeLessThan(88);
    expect(result.sources.find((s) => s.id === 'records')?.severity).toBe('warn');
    expect(result.sources.find((s) => s.id === 'imagery')?.status).toBe('missing');
  });
});
