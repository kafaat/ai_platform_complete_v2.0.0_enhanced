// Sahool Field Operating Contract
// Central UI/product primitives for Field Operating System behavior.
// This file intentionally contains no network calls; it is safe to import from
// React, tests, mobile contract docs, and future form/schema adapters.

export type ProductMode = 'basic_farm' | 'precision' | 'enterprise' | 'government_ngo' | 'demo';

export type SahoolRole = 'owner' | 'manager' | 'agronomist' | 'worker' | 'government_supervisor';

export type FieldState =
  | 'draft'
  | 'boundary_pending'
  | 'boundary_invalid'
  | 'boundary_validated'
  | 'active'
  | 'archived';

export type SeasonState = 'planned' | 'active' | 'completed' | 'reconciled' | 'archived';

export type TaskState =
  | 'draft'
  | 'open'
  | 'assigned'
  | 'in_progress'
  | 'completed'
  | 'verified'
  | 'outcome_recorded';

export type RecommendationState =
  | 'generated'
  | 'shown'
  | 'accepted'
  | 'task_created'
  | 'executed'
  | 'outcome_recorded'
  | 'learned';

export type SyncStatus = 'local_pending' | 'syncing' | 'synced' | 'failed' | 'conflict';

export type CompletenessStatus = 'complete' | 'partial' | 'missing' | 'not_available' | 'stale';

export type UiPanelState = 'loading_state' | 'empty_state' | 'error_state' | 'stale_state' | 'degraded_state';

export type LayerCategory =
  | 'base_map'
  | 'field'
  | 'imagery'
  | 'weather'
  | 'soil'
  | 'irrigation'
  | 'assets'
  | 'operations'
  | 'economics';

export type LayerRenderType = 'tile' | 'feature' | 'marker' | 'vector' | 'heatmap' | 'line' | 'polygon';

export interface ProductOperatingContract {
  feature_id: string;
  product_mode: ProductMode[];
  roles: SahoolRole[];
  ui_component: string;
  domain_hook: string;
  api_contract: string;
  backend_route: string;
  data_owner: string;
  states: UiPanelState[];
  tests_or_guards: string[];
}

export interface LayerContract {
  id: string;
  label: string;
  category: LayerCategory;
  render_type: LayerRenderType;
  source_service: string;
  source_endpoint?: string;
  legend: string;
  opacity_supported: boolean;
  freshness: 'live' | 'hourly' | 'daily' | 'scene_date' | 'revision' | 'static' | 'unknown';
  confidence: 'required' | 'optional' | 'not_applicable';
  requires_field: boolean;
  requires_season: boolean;
  default_enabled: boolean;
  compare_enabled: boolean;
  states: UiPanelState[];
  allowed_product_modes: ProductMode[];
  allowed_roles: SahoolRole[];
  why_this: string;
  primary_actions: string[];
}

export interface ConfidenceDeduction {
  code: string;
  label: string;
  points: number;
}

export interface ConfidenceBudget {
  base_confidence: number;
  confidence: number;
  deductions: ConfidenceDeduction[];
}

export interface ReadinessInput {
  active_valid_boundary: boolean;
  active_season: boolean;
  crop_selected: boolean;
  planting_or_start_date: boolean;
  irrigation_method: boolean;
  weather_available: boolean;
  latest_imagery_fresh: boolean;
  soil_confidence_known: boolean;
  open_task_state_known: boolean;
  sensors_declared: boolean;
}

export interface ReadinessResult {
  score: number;
  complete: string[];
  warnings: string[];
  next_actions: string[];
}

export const FIELD_ANALYTICS_READY_STATES: FieldState[] = ['boundary_validated', 'active'];

export const REQUIRED_PANEL_STATES: UiPanelState[] = [
  'loading_state',
  'empty_state',
  'error_state',
  'stale_state',
  'degraded_state',
];

export const STATE_MACHINES = {
  field: ['draft', 'boundary_pending', 'boundary_invalid', 'boundary_validated', 'active', 'archived'] as const,
  season: ['planned', 'active', 'completed', 'reconciled', 'archived'] as const,
  task: ['draft', 'open', 'assigned', 'in_progress', 'completed', 'verified', 'outcome_recorded'] as const,
  recommendation: ['generated', 'shown', 'accepted', 'task_created', 'executed', 'outcome_recorded', 'learned'] as const,
};

export const PRODUCT_MODES: Record<ProductMode, { labelAr: string; defaultSurfaces: string[] }> = {
  basic_farm: {
    labelAr: 'نمط المزرعة الأساسي',
    defaultSurfaces: ['fields', 'seasons', 'weather', 'tasks', 'simple_reports'],
  },
  precision: {
    labelAr: 'نمط الزراعة الدقيقة',
    defaultSurfaces: ['imagery', 'zones', 'sensors', 'equipment', 'vra', 'advanced_recommendations'],
  },
  enterprise: {
    labelAr: 'نمط المؤسسات',
    defaultSurfaces: ['teams', 'rbac', 'audit', 'economics', 'integrations', 'sla'],
  },
  government_ngo: {
    labelAr: 'نمط الحكومة والمنظمات',
    defaultSurfaces: ['regional_maps', 'aggregate_indicators', 'program_reports', 'compliance'],
  },
  demo: {
    labelAr: 'نمط العرض التجريبي',
    defaultSurfaces: ['sample_data', 'guided_tours', 'simulated_layers'],
  },
};

export const MAP_CLUTTER_RULES = {
  max_default_operational_layers: 3,
  critical_tasks_always_visible: true,
  stale_alerts_auto_archive: true,
  sensor_clustering_enabled: true,
  equipment_live_only_in_equipment_mode: true,
};

export const MAP_LAYER_PRESETS: Record<string, string[]> = {
  health: ['field_boundaries', 'truecolor', 'ndvi', 'stress_zones', 'scouting_tasks'],
  irrigation: ['field_boundaries', 'irrigation_sectors', 'et0', 'soil_moisture', 'irrigation_tasks'],
  operations: ['field_boundaries', 'tasks', 'equipment', 'alerts'],
  weather: ['field_boundaries', 'wind', 'rain', 'temperature', 'operation_windows'],
  scouting: ['field_boundaries', 'observations', 'photos', 'scouting_routes'],
  economics: ['field_boundaries', 'crop_colors', 'cost_overlay', 'yield_overlay', 'profit_overlay'],
};

export const DATA_COMPLETENESS_CATEGORIES = [
  'boundary',
  'season',
  'crop',
  'soil',
  'irrigation',
  'imagery',
  'weather',
  'sensors',
  'equipment',
  'tasks',
  'scouting',
  'economics',
  'reports',
] as const;

export const UNIFIED_FIELD_TIMELINE_EVENTS = [
  'planting',
  'satellite_image',
  'weather_risk',
  'sensor_alert',
  'recommendation',
  'task_created',
  'task_completed',
  'task_verified',
  'scouting_observation',
  'irrigation',
  'spraying',
  'fertilization',
  'harvest',
  'outcome_recorded',
  'report_generated',
] as const;

const READINESS_WEIGHTS: Array<[keyof ReadinessInput, number, string, string]> = [
  ['active_valid_boundary', 20, 'حدود الحقل صالحة', 'تحقق من حدود الحقل'],
  ['active_season', 15, 'موسم نشط', 'أضف موسمًا نشطًا'],
  ['crop_selected', 10, 'المحصول محدد', 'اختر المحصول'],
  ['planting_or_start_date', 10, 'تاريخ البداية موجود', 'أضف تاريخ الزراعة أو بداية الموسم'],
  ['irrigation_method', 10, 'طريقة الري محددة', 'حدد طريقة الري'],
  ['weather_available', 10, 'الطقس متاح', 'تحقق من خدمة الطقس'],
  ['latest_imagery_fresh', 10, 'آخر صورة قمرية حديثة', 'حدّث صور الأقمار الصناعية'],
  ['soil_confidence_known', 8, 'ثقة التربة معروفة', 'أكمل بيانات التربة أو اتركها غير معروفة بوضوح'],
  ['open_task_state_known', 4, 'حالة المهام معروفة', 'راجع المهام المفتوحة'],
  ['sensors_declared', 3, 'حالة الحساسات معروفة', 'أضف حساسًا أو عرّف الحقل كبدون حساسات'],
];

export function calculateFieldReadiness(input: ReadinessInput): ReadinessResult {
  let score = 0;
  const complete: string[] = [];
  const warnings: string[] = [];
  const next_actions: string[] = [];

  for (const [key, weight, doneLabel, actionLabel] of READINESS_WEIGHTS) {
    if (input[key]) {
      score += weight;
      complete.push(doneLabel);
    } else {
      warnings.push(doneLabel.replace('موجود', 'ناقص').replace('محددة', 'غير محددة').replace('صالحة', 'غير صالحة أو غير مؤكدة'));
      next_actions.push(actionLabel);
    }
  }

  return { score, complete, warnings, next_actions };
}

export function buildConfidenceBudget(base_confidence: number, deductions: ConfidenceDeduction[]): ConfidenceBudget {
  const deductionTotal = deductions.reduce((sum, deduction) => sum + deduction.points, 0);
  const confidence = Math.max(0, Math.min(1, base_confidence - deductionTotal));
  return { base_confidence, confidence, deductions };
}

export function canRunFieldAnalytics(state: FieldState): boolean {
  return FIELD_ANALYTICS_READY_STATES.includes(state);
}

export function hasRequiredPanelStates(states: UiPanelState[]): boolean {
  return REQUIRED_PANEL_STATES.every((state) => states.includes(state));
}
