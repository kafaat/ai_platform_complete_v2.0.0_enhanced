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

export const enterpriseGisPhase7Endpoints = {
  collaborationSession: '/api/v1/gis/collaboration/sessions',
  collaborationEvents: (sessionId: string) => `/api/v1/gis/collaboration/sessions/${sessionId}/events`,
  collaborationSocket: (sessionId: string) => `/ws/gis/collaboration/${sessionId}`,
  ogcLanding: '/ogc',
  ogcConformance: '/ogc/conformance',
  distributedRasterPlan: '/api/v1/gis/raster/distributed/plan',
  distributedRasterJobs: '/api/v1/gis/raster/distributed/jobs',
  digitalTwinScenario: '/api/v1/digital-twin/scenarios/simulate',
  autonomousRecommendations: '/api/v1/recommendations/autonomous',
  planetScaleReadiness: '/api/v1/gis/readiness/planet-scale',
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
