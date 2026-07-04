import type { PageId } from '../App';

export type CoveragePriority = 'P0' | 'P1' | 'P2' | 'P3';
export type CoverageRole = 'fieldview_user' | 'manager_console' | 'admin_console' | 'expert_console' | 'internal_only';
export type CoverageState = 'covered' | 'partial' | 'waived_internal' | 'not_ready';

export interface CoverageSurface {
  kind: 'page' | 'fieldview_card' | 'panel' | 'hook_only' | 'admin_page' | 'expert_page' | 'waiver';
  name: string;
  routeId?: PageId;
  component?: string;
}

export interface BackendCoverageLayer {
  id: string;
  label: string;
  priority: CoveragePriority;
  role: CoverageRole;
  state: CoverageState;
  endpoints: string[];
  hooks: string[];
  surfaces: CoverageSurface[];
  owner: 'fieldview' | 'admin' | 'decision' | 'agronomy' | 'gis' | 'economics' | 'runtime' | 'marketplace';
  gap?: string;
  nextAction?: string;
  waiverReason?: string;
}

export const BACKEND_COVERAGE_REGISTRY: BackendCoverageLayer[] = [
  {
    id: 'admin-runtime-ops',
    label: 'Admin Runtime Ops / DLQ / Scheduler / Queue',
    priority: 'P0',
    role: 'admin_console',
    state: 'covered',
    owner: 'admin',
    endpoints: [
      '/api/v1/admin/readiness',
      '/api/v1/admin/events/dead-letter',
      '/api/v1/admin/outbox/dead-letter',
      '/api/v1/admin/security/denials',
      '/api/v1/automation/runs',
      '/api/v1/automation/scheduler-status',
      '/api/v1/queue/status',
    ],
    hooks: ['useAdminReadiness', 'useAdminEventsDeadLetter', 'useAdminOutboxDeadLetter', 'useSecurityDenials', 'useAutomationRuns', 'useSchedulerStatus', 'useQueueStatus'],
    surfaces: [{ kind: 'admin_page', name: 'AdminRuntimePage', routeId: 'admin-runtime', component: 'AdminRuntimePage' }],
  },
  {
    id: 'decision-runtime',
    label: 'Decision Dispatch / Policies / Ledger / Outcome',
    priority: 'P0',
    role: 'manager_console',
    state: 'covered',
    owner: 'decision',
    endpoints: [
      '/api/v1/decision/dispatch/queue',
      '/api/v1/decision/dispatch/decisions',
      '/api/v1/decision/dispatch/evaluate',
      '/api/v1/decision/policies',
      '/api/v1/decision/ledger',
      '/api/v1/outcome/measure',
    ],
    hooks: ['useDispatchQueue', 'useDispatchDecisions', 'useEvaluateDispatch', 'useDecisionPolicies', 'useDecisionLedger', 'useMeasureOutcome'],
    surfaces: [{ kind: 'page', name: 'DecisionRuntimePage', routeId: 'decision-runtime', component: 'DecisionRuntimePage' }],
  },
  {
    id: 'yemen-calendar-local-knowledge',
    label: 'Yemen calendar / astronomical timing / agricultural proverbs',
    priority: 'P1',
    role: 'fieldview_user',
    state: 'covered',
    owner: 'agronomy',
    endpoints: [
      '/api/v1/calendars/today',
      '/api/v1/calendars/lunar-mansions',
      '/api/v1/calendars/himyarite-months',
      '/api/v1/agricultural-proverbs/for-date',
    ],
    hooks: ['useCalendarToday', 'useProverbsForDate'],
    surfaces: [{ kind: 'fieldview_card', name: 'YemeniCalendarCard', component: 'YemeniCalendarCard' }],
  },
  {
    id: 'crop-cards-variety-intelligence',
    label: 'Crop cards / variety intelligence / disease and salinity watch',
    priority: 'P1',
    role: 'fieldview_user',
    state: 'covered',
    owner: 'agronomy',
    endpoints: [
      '/api/v1/crop-cards',
      '/api/v1/crop-cards/crop/{crop}',
      '/api/v1/crop-cards/variety/{variety}/disease-watch',
      '/api/v1/crop-cards/variety/{variety}/expected-harvest',
      '/api/v1/crop-cards/variety/{variety}/salinity-suitability',
    ],
    hooks: ['useCropCardsIndex', 'useCropCard', 'useVarietyDiseaseWatch', 'useVarietyExpectedHarvest', 'useVarietySalinity'],
    surfaces: [{ kind: 'fieldview_card', name: 'CropKnowledgeCard', component: 'CropKnowledgeCard' }],
  },
  {
    id: 'boundary-governance',
    label: 'Boundary AI / topology governance / human review',
    priority: 'P1',
    role: 'expert_console',
    state: 'covered',
    owner: 'gis',
    endpoints: [
      '/api/v1/fields/{field_id}/boundary/score',
      '/api/v1/fields/{field_id}/boundary/review',
      '/api/v1/fields/{field_id}/boundary/clean',
      '/api/v1/fields/{field_id}/boundary-graph',
    ],
    hooks: ['useBoundaryGraph', 'useScoreBoundary', 'useReviewBoundary', 'useCleanBoundary'],
    surfaces: [{ kind: 'fieldview_card', name: 'BoundaryReviewCard', component: 'BoundaryReviewCard' }],
  },
  {
    id: 'farm-ledger-economics',
    label: 'Farm ledger / budgets / revenues / profitability / variance',
    priority: 'P1',
    role: 'manager_console',
    state: 'covered',
    owner: 'economics',
    endpoints: [
      '/api/v1/farm-ledger/summary',
      '/api/v1/farm-ledger/operations',
      '/api/v1/farm-ledger/budgets',
      '/api/v1/farm-ledger/revenues',
      '/api/v1/farm-ledger/profitability/{season}',
      '/api/v1/farm-ledger/variance/{season}',
      '/api/v1/farm-ledger/economic-state/{season}',
      '/api/v1/economics/break-even',
    ],
    hooks: ['useFarmLedgerSummary', 'useRecordLedgerOperation', 'useUpsertBudgetLines', 'useRecordRevenue', 'useSeasonProfitability', 'useSeasonVariance', 'useSeasonEconomicState', 'useBreakEven'],
    surfaces: [
      { kind: 'fieldview_card', name: 'FieldEconomicsCard', component: 'FieldEconomicsCard' },
      { kind: 'fieldview_card', name: 'SeasonProfitabilityCard', component: 'SeasonProfitabilityCard' },
      { kind: 'fieldview_card', name: 'LedgerEntryCard', component: 'LedgerEntryCard' },
      { kind: 'page', name: 'EconomicsDashboard', routeId: 'economics', component: 'EconomicsDashboard' },
    ],
  },
  {
    id: 'traceability-harvest-lots',
    label: 'Harvest lots / custody events / input traceability',
    priority: 'P2',
    role: 'manager_console',
    state: 'covered',
    owner: 'agronomy',
    endpoints: [
      '/api/v1/harvest-lots',
      '/api/v1/harvest-lots/{id}/traceability',
      '/api/v1/fields/{field_id}/input-traceability',
    ],
    hooks: ['useHarvestLots', 'useLotTraceability', 'useFieldInputTraceability'],
    surfaces: [
      { kind: 'fieldview_card', name: 'HarvestTraceabilityCard', component: 'HarvestTraceabilityCard' },
      { kind: 'fieldview_card', name: 'TraceabilityCard', component: 'TraceabilityCard' },
    ],
  },
  {
    id: 'crop-planning-rotation-planting',
    label: 'Crop planning / planting windows / rotation / GDD',
    priority: 'P1',
    role: 'fieldview_user',
    state: 'covered',
    owner: 'agronomy',
    endpoints: [
      '/api/v1/planting/check',
      '/api/v1/planting/window',
      '/api/v1/rotation/suggest',
      '/api/v1/rotation/evaluate',
      '/api/v1/crops/{crop}/operations-calendar',
      '/api/v1/gdd/track',
    ],
    hooks: ['usePlantingCheck', 'useRotationSuggest', 'useCropOperationsCalendar', 'useGddTrack'],
    surfaces: [
      { kind: 'fieldview_card', name: 'PlantingAdvisorCard', component: 'PlantingAdvisorCard' },
      { kind: 'fieldview_card', name: 'FieldObjectivePanel', component: 'FieldObjectivePanel' },
    ],
  },
  {
    id: 'climate-risk-analogs',
    label: 'Climate analogs / seasonal risk / chill hours / water sensitivity',
    priority: 'P1',
    role: 'expert_console',
    state: 'covered',
    owner: 'agronomy',
    endpoints: [
      '/api/v1/water-sensitivity/calendar',
      '/api/v1/seasonal-risk/calendar',
      '/api/v1/seasonal-risk/chill-hours',
      '/api/v1/climate-analogs/list',
    ],
    hooks: ['useWaterSensitivityCalendar', 'useSeasonalRiskCalendar', 'useChillHoursEstimate', 'useClimateAnalogRegions'],
    surfaces: [{ kind: 'fieldview_card', name: 'ClimateRiskCard', component: 'ClimateRiskCard' }],
  },
  {
    id: 'water-harvesting-irrigation-methods',
    label: 'Water harvesting / irrigation method advisor',
    priority: 'P2',
    role: 'expert_console',
    state: 'covered',
    owner: 'agronomy',
    endpoints: [
      '/api/v1/water-harvesting/potential',
      '/api/v1/water-harvesting/methods',
      '/api/v1/water-harvesting/method-guide',
      '/api/v1/irrigation-method',
    ],
    hooks: ['useWaterHarvestPotential', 'useWaterHarvestingMethods', 'useWaterHarvestMethodGuide', 'useIrrigationMethodProfiles'],
    surfaces: [{ kind: 'fieldview_card', name: 'WaterHarvestingCard', component: 'WaterHarvestingCard' }],
  },
  {
    id: 'seed-propagation-postharvest-coffee',
    label: 'Propagation / postharvest / Yemeni coffee knowledge',
    priority: 'P2',
    role: 'fieldview_user',
    state: 'covered',
    owner: 'agronomy',
    endpoints: [
      '/api/v1/propagation/crop',
      '/api/v1/postharvest/best-practices',
      '/api/v1/coffee/guide',
      '/api/v1/coffee/varieties',
      '/api/v1/coffee/pests',
    ],
    hooks: ['useCropPropagation', 'usePostharvestBestPractices', 'useCoffeeGuide', 'useCoffeeVarieties', 'useCoffeePests'],
    surfaces: [{ kind: 'fieldview_card', name: 'AgroKnowledgeCard', component: 'AgroKnowledgeCard' }],
  },
  {
    id: 'advanced-gis-ogc-stac-cog',
    label: 'Advanced GIS / OGC / STAC / COG expert tooling',
    priority: 'P2',
    role: 'expert_console',
    state: 'covered',
    owner: 'gis',
    endpoints: [
      '/api/v1/gis/*',
      '/api/v1/ogc/*',
      '/api/v1/stac/*',
      '/api/v1/cog/*',
    ],
    hooks: ['useGisTools', 'useNlGis', 'useGisStacLanding', 'useGisStacCollections', 'useGisStacItems', 'useGisOgcConformance', 'useGisOgcCollections', 'useGisTileCachePlan'],
    surfaces: [
      { kind: 'expert_page', name: 'GisExpertPage', routeId: 'gis-expert', component: 'GisExpertPage' },
      { kind: 'expert_page', name: 'GisToolsPage', routeId: 'gis-tools', component: 'GisToolsPage' },
      { kind: 'expert_page', name: 'NlGisPage', routeId: 'nl-gis', component: 'NlGisPage' },
    ],
  },
  {
    id: 'soil-lab-salinity-ipm',
    label: 'Soil/lab/salinity/IPM diagnostics',
    priority: 'P2',
    role: 'expert_console',
    state: 'covered',
    owner: 'agronomy',
    endpoints: [
      '/api/v1/lab/*',
      '/api/v1/soil/*',
      '/api/v1/ipm/*',
      '/api/v1/pest/*',
      '/api/v1/diagnose',
      '/api/v1/salinity/assess',
    ],
    hooks: ['useFieldSoilMoisture', 'useSoilNRecommendation', 'useScoutingTaxonomy', 'useScoutingPins', 'useDiagnose', 'useDiagnosisSymptoms', 'useIpmPests', 'useIpmPlan', 'useIpmCropPests', 'useSalinityAssess'],
    surfaces: [
      { kind: 'page', name: 'LabSamplingPage', routeId: 'lab-sampling', component: 'LabSamplingPage' },
      { kind: 'page', name: 'ScoutingView', routeId: 'scouting', component: 'ScoutingView' },
      { kind: 'page', name: 'PestEscalationPage', routeId: 'pest-escalation', component: 'PestEscalationPage' },
      { kind: 'fieldview_card', name: 'DiagnosticsCard', component: 'DiagnosticsCard' },
    ],
  },
  {
    id: 'simulation-crop-twin-scenarios',
    label: 'Simulation / crop twin / scenario comparison / replay',
    priority: 'P2',
    role: 'manager_console',
    state: 'covered',
    owner: 'decision',
    endpoints: [
      '/api/v1/scenario/*',
      '/api/v1/simulation/*',
      '/api/v1/crop-twin/*',
      '/api/v1/replay/*',
    ],
    hooks: ['useScenarioCompare', 'useReplaySeason', 'useScenarioTemperature', 'useScenarioRainfall', 'useScenarioPlantingDate', 'useScenarioWaterTwin'],
    surfaces: [
      { kind: 'fieldview_card', name: 'WhatIfScenariosCard', component: 'WhatIfScenariosCard' },
      { kind: 'page', name: 'ScenarioComparePage', routeId: 'scenario-compare', component: 'ScenarioComparePage' },
      { kind: 'page', name: 'ReplayMapPage', routeId: 'replay-map', component: 'ReplayMapPage' },
    ],
  },
  {
    id: 'zones-vra-soil-sampling',
    label: 'Productivity zones / VRA / soil sampling planner',
    priority: 'P1',
    role: 'expert_console',
    state: 'covered',
    owner: 'gis',
    endpoints: [
      '/api/v1/fields/{field_id}/productivity-zones',
      '/api/v1/fields/{field_id}/prescriptions',
      '/api/v1/fields/{field_id}/soil-sampling-plan',
    ],
    hooks: ['useFieldPrescriptions'],
    surfaces: [
      { kind: 'panel', name: 'ProductivityZonesPanel', component: 'ProductivityZonesPanel' },
      { kind: 'panel', name: 'VraPrescriptionPanel', component: 'VraPrescriptionPanel' },
      { kind: 'panel', name: 'SoilSamplingPlannerPanel', component: 'SoilSamplingPlannerPanel' },
      { kind: 'page', name: 'PrescriptionBuilderPage', routeId: 'prescriptions', component: 'PrescriptionBuilderPage' },
    ],
  },
  {
    id: 'collaboration-approvals-sharing-rbac',
    label: 'Collaboration / approvals / sharing / RBAC visibility',
    priority: 'P2',
    role: 'manager_console',
    state: 'partial',
    owner: 'runtime',
    endpoints: [
      '/api/v1/sharing/*',
      '/api/v1/approvals/*',
      '/api/v1/invitations/*',
      '/api/v1/rbac/*',
    ],
    hooks: ['useInvitations', 'useCreateShareLink'],
    surfaces: [{ kind: 'panel', name: 'SharingPanel', component: 'SharingPanel' }],
    gap: 'Sharing exists, but approvals and RBAC decision gates are not unified in the manager console.',
    nextAction: 'Add Approvals Console and connect high-risk Objective Engine actions to approval state.',
  },
  {
    id: 'phase-runtime-registry-sync',
    label: 'Phase runtime / registry / worker sync',
    priority: 'P2',
    role: 'internal_only',
    state: 'waived_internal',
    owner: 'runtime',
    endpoints: [
      '/api/v1/phase9/*',
      '/api/v1/phase10/*',
      '/api/v1/phase11/*',
      '/api/v1/phase12/*',
      '/api/v1/runtime/*',
    ],
    hooks: [],
    surfaces: [{ kind: 'waiver', name: 'Internal runtime only' }],
    waiverReason: 'Runtime/worker orchestration endpoints must remain internal; only aggregated health belongs in AdminRuntimePage.',
  },
  {
    id: 'marketplace-plugins-ecosystem',
    label: 'Marketplace / plugins / ecosystem extension points',
    priority: 'P3',
    role: 'manager_console',
    state: 'not_ready',
    owner: 'marketplace',
    endpoints: ['/api/v1/marketplace/*', '/api/v1/plugins/*', '/api/v1/ecosystem/*'],
    hooks: [],
    surfaces: [],
    gap: 'Backend surface is experimental; exposing it now would create a product promise before permission, billing, and sandbox policies are finalized.',
    nextAction: 'Keep behind not_ready waiver until plugin sandbox policy, billing guard, and tenant isolation tests exist.',
  },
];

export function coverageSummary(layers: BackendCoverageLayer[] = BACKEND_COVERAGE_REGISTRY) {
  return layers.reduce<Record<CoverageState, number>>((acc, layer) => {
    acc[layer.state] += 1;
    return acc;
  }, { covered: 0, partial: 0, waived_internal: 0, not_ready: 0 });
}

export function criticalCoverageGaps(layers: BackendCoverageLayer[] = BACKEND_COVERAGE_REGISTRY) {
  return layers.filter((layer) => ['P0', 'P1'].includes(layer.priority) && layer.state !== 'covered' && layer.state !== 'waived_internal');
}

export function endpointCoverageMap(layers: BackendCoverageLayer[] = BACKEND_COVERAGE_REGISTRY) {
  return new Map(layers.flatMap((layer) => layer.endpoints.map((endpoint) => [endpoint, layer] as const)));
}

export function layerForEndpoint(endpoint: string, layers: BackendCoverageLayer[] = BACKEND_COVERAGE_REGISTRY) {
  return layers.find((layer) => layer.endpoints.some((pattern) => {
    if (pattern.endsWith('/*')) return endpoint.startsWith(pattern.slice(0, -1));
    const re = new RegExp(`^${pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\\\{[^/]+\\\}/g, '[^/]+')}$`);
    return re.test(endpoint);
  })) ?? null;
}
