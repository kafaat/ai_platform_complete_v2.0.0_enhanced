export type CollaborationEventType = 'presence' | 'cursor' | 'geometry_patch' | 'annotation' | 'commit' | 'rollback';

export interface CollaborationEventPayload {
  sessionId: string;
  fieldId: string;
  userId: string;
  eventType: CollaborationEventType;
  revision: number;
  payload: Record<string, unknown>;
}

export interface OgcConformanceManifest {
  conformsTo: string[];
  endpoints: Record<string, string>;
  status: string;
}

export interface DistributedRasterPlanRequest {
  scenes: Array<{ scene_id: string; field_id: string; area_ha: number; cloud_cover?: number }>;
  operations?: string[];
  preferredRuntime?: 'dask' | 'ray' | 'celery' | 'local';
}

export interface DigitalTwinScenarioRequest {
  baseline: Record<string, number>;
  scenario: Record<string, number>;
}

export interface AutonomousRecommendation {
  recommendation_id: string;
  domain: string;
  action: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
  confidence: number;
  requires_human_approval: boolean;
  rationale: string[];
  evidence: Record<string, unknown>;
}

// No `/api/v1` paths here: every one of them had no server handler and no caller
// (WEB-ENDPOINT-CONSTANTS-WITHOUT-SERVER-HANDLER-01). A new `/api/v1` constant must
// match a route in route_inventory.generated.json; see
// tests_v9/test_frontend_api_v1_literal_has_server_route.py.
export const enterpriseGisPhase7Endpoints = {
  collaborationSocket: (sessionId: string) => `/ws/gis/collaboration/${sessionId}`,
  ogcLanding: '/ogc',
  ogcConformance: '/ogc/conformance',
};

export function buildCollaborationWsUrl(baseWsUrl: string, sessionId: string, token?: string): string {
  const url = new URL(enterpriseGisPhase7Endpoints.collaborationSocket(sessionId), baseWsUrl);
  if (token) url.searchParams.set('token', token);
  return url.toString();
}

export function summarizeRecommendationPriority(recommendations: AutonomousRecommendation[]): 'none' | 'medium' | 'high' | 'critical' {
  if (recommendations.some((r) => r.priority === 'critical')) return 'critical';
  if (recommendations.some((r) => r.priority === 'high')) return 'high';
  if (recommendations.some((r) => r.priority === 'medium')) return 'medium';
  return 'none';
}

export function isOgcReady(manifest: OgcConformanceManifest): boolean {
  return manifest.status.includes('ready') && manifest.conformsTo.length >= 2;
}
