// تحقّق V74-UI — مساعِدات رسم الأدلّة (منطق نقيّ، بلا React).

import { describe, it, expect } from 'vitest';
import { evidenceNodes, supportingEvidenceCount, type EvidenceGraph } from './evidenceGraph';

const GRAPH: EvidenceGraph = {
  schema: 'sahool.evidence_graph/1',
  field_id: 'f-1',
  nodes: [
    { id: 'field', type: 'field', label: 'الحقل' },
    { id: 'evidence:soil_baseline', type: 'soil_baseline', label: 'خطّ أساس التربة', source: 'soilgrids' },
    { id: 'evidence:terrain', type: 'terrain', label: 'التضاريس', source: 'copernicus_dem' },
    { id: 'recommendation', type: 'recommendation', label: 'توصية' },
  ],
  edges: [
    { from: 'field', to: 'evidence:soil_baseline', rel: 'has_evidence' },
    { from: 'evidence:soil_baseline', to: 'recommendation', rel: 'supports' },
    { from: 'evidence:terrain', to: 'recommendation', rel: 'supports' },
  ],
  knowledge_gaps: [{ key: 'weather_window', label: 'نافذة الطقس', reason: 'no_weather_window_supplied' }],
  summary: { node_count: 4, edge_count: 3, evidence_count: 2, gap_count: 1, has_recommendation: true },
};

describe('evidenceGraph helpers', () => {
  it('evidenceNodes excludes field and recommendation', () => {
    const ev = evidenceNodes(GRAPH);
    expect(ev.map((n) => n.id)).toEqual(['evidence:soil_baseline', 'evidence:terrain']);
    expect(evidenceNodes(null)).toEqual([]);
  });

  it('supportingEvidenceCount counts supports edges', () => {
    expect(supportingEvidenceCount(GRAPH)).toBe(2);
    expect(supportingEvidenceCount(undefined)).toBe(0);
  });
});
