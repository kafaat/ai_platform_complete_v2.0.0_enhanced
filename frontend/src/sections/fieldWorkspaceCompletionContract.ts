// SAHOOL UI-34 — Field Workspace completion contract
// This is a static contract for the completed workspace surface; it is not a data source.

export const FIELD_WORKSPACE_COMPLETION_CONTRACT = {
  context: ['field_id', 'season_id'],
  tabs: ['overview', 'map', 'season', 'imagery', 'weather', 'irrigation', 'operations', 'recommendations', 'reports'],
  backendOwnedReads: [
    '/api/v1/fields/{field_id}/readiness',
    '/api/v1/fields/{field_id}/data-completeness',
    '/api/v1/fields/{field_id}/unified-timeline',
    '/api/v1/fields/{field_id}/priority-queue',
    '/api/v1/fields/{field_id}/available-dates',
    '/api/v1/fields/{field_id}/imagery/timeline',
    '/api/v1/fields/{field_id}/weather/operation-windows',
    '/api/v1/fields/{field_id}/weather/disease-risk',
    '/api/v1/fields/{field_id}/weather/irrigation-advice',
    '/api/v1/irrigation/schedules?field_id={field_id}',
  ],
  noFrontendFabrication: ['timeline-events', 'recommendations', 'reports', 'irrigation-plans', 'imagery-dates'],
} as const;
