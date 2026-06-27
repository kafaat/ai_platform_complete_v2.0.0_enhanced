import { buildCollaborationWsUrl, enterpriseGisPhase7Endpoints, isOgcReady, summarizeRecommendationPriority } from './enterpriseGisPhase7';

describe('enterprise GIS phase 7 contracts', () => {
  it('builds collaboration websocket urls with token', () => {
    const url = buildCollaborationWsUrl('wss://api.sahool.local', 's1', 'abc');
    expect(url).toContain('/ws/gis/collaboration/s1');
    expect(url).toContain('token=abc');
  });

  it('summarizes recommendation priority', () => {
    expect(summarizeRecommendationPriority([{ recommendation_id: 'r1', domain: 'weather', action: 'block', priority: 'critical', confidence: 0.9, requires_human_approval: false, rationale: [], evidence: {} }])).toBe('critical');
  });

  it('detects OGC readiness', () => {
    expect(isOgcReady({ status: 'ready_for_external_conformance_tests', conformsTo: ['features', 'tiles'], endpoints: {} })).toBe(true);
  });

  it('keeps endpoint registry stable', () => {
    expect(enterpriseGisPhase7Endpoints.ogcConformance).toBe('/ogc/conformance');
  });
});
