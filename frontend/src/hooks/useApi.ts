// SAHOOL v9.0 — src/hooks/useApi.ts — React Query hooks شاملة
import {
  useQuery, useMutation,
  UseQueryResult, UseMutationResult,
} from '@tanstack/react-query';
import {
  kongApi, indicatorsApi, vegetationApi,
  weatherApi, soilApi, authApi, rasterApi,
} from '../services/api';
import { useAuthStore } from './useAuth';

// ── Query Keys ─────────────────────────────────────────────────
export const QK = {
  indicators:       (fid: string)        => ['indicators', fid],
  indicatorsCatalog:                        ['indicators', 'catalog'],
  allFieldsNdvi:    (tid: string)        => ['vegetation', 'all', tid],
  ndviCurrent:      (fid: string)        => ['vegetation', 'ndvi', fid],
  timeseries:       (fid: string, d: number) => ['vegetation', 'ts', fid, d],
  weatherForecast:  (lat: number, lon: number) => ['weather', 'forecast', lat, lon],
  weatherWofost:    (lat: number, lon: number, days: number) => ['weather', 'wofost', lat, lon, days],
  weatherHistory:   (lat: number, lon: number, days: number) => ['weather', 'history', lat, lon, days],
  soilParams:       (fid: string)        => ['soil', 'params', fid],
  soilNRec:         (fid: string)        => ['soil', 'nrec', fid],
  fields:           (tid: string)        => ['fields', tid],
  tasks:            (fid?: string)       => ['tasks', fid ?? 'all'],
  alerts:           (tid: string)        => ['alerts', tid],
  indicatorGrid:    (fid: string, index: string, date: string) => ['indicator-grid', fid, index, date],
  health:                                   ['health', 'all'],
} as const;

// ── Types ──────────────────────────────────────────────────────
export interface ServiceHealth {
  name:    string;
  status:  'ok' | 'error' | 'unknown';
  latency: number;
}

export interface TimeseriesPoint {
  date: string; ndvi: number; evi?: number;
  savi?: number; ndwi?: number; lai?: number; cwsi?: number;
}

export interface Task {
  task_id: string; field_id: string; field_name?: string;
  task_type: string; priority: number; recommended_date: string;
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled';
  estimated_duration_min: number; estimated_cost_usd: number;
  notes?: string; photo_url?: string; tenant_id: string;
}

export interface AgentResponse {
  response_ar: string; response_en?: string;
  structured_data?: Record<string, unknown>;
  actions_triggered: string[]; confidence: number;
  sources: string[]; processing_time_ms: number;
}

export interface GuardrailsResult {
  allowed: boolean;
  overall_risk: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  requires_human_approval: boolean;
  arabic_explanation: string;
  diff?: Record<string, unknown>;
}

// ── Indicator Grid (raster-service per-pixel grid) ──────────────
export type GridIndex = 'ndvi' | 'ndmi' | 'ndwi' | 'salinity';

export interface IndicatorGridZone {
  id: string;
  severity: 'low' | 'medium' | 'high';
  mean: number;
  cells: [number, number][];
}

export interface IndicatorGridResponse {
  field_id: string;
  index: string;
  date: string;
  bbox: [number, number, number, number]; // [minlon, minlat, maxlon, maxlat]
  rows: number;
  cols: number;
  grid: (number | null)[][]; // rows x cols; null = nodata/outside field
  stats: { min: number; max: number; mean: number };
  zones: IndicatorGridZone[];
  source: string;
  real_data: boolean;
}

// ── Service Health ─────────────────────────────────────────────
const SERVICES = [
  { name:'auth-service',       api: authApi,        path:'/readyz'       },
  { name:'indicators-service', api: indicatorsApi,  path:'/readyz'       },
  { name:'vegetation-service', api: vegetationApi,  path:'/readyz'       },
  { name:'weather-service',    api: weatherApi,     path:'/readyz'       },
  { name:'soil-service',       api: soilApi,        path:'/readyz'       },
  { name:'supervisor-agent',   api: kongApi,        path:'/api/agent/health'      },
  { name:'notification-agent', api: kongApi,        path:'/health'       },
];

async function checkAll(): Promise<ServiceHealth[]> {
  return Promise.all(
    SERVICES.map(async s => {
      const t0 = Date.now();
      try {
        await s.api.get(s.path, { timeout: 4000 });
        return { name: s.name, status: 'ok' as const, latency: Date.now() - t0 };
      } catch {
        return { name: s.name, status: 'error' as const, latency: Date.now() - t0 };
      }
    })
  );
}

// ── Health ─────────────────────────────────────────────────────
export function useAllServicesHealth(): UseQueryResult<ServiceHealth[]> {
  return useQuery({
    queryKey:        QK.health,
    queryFn:         checkAll,
    staleTime:       30_000,
    refetchInterval: 60_000,
    retry:           false,
  });
}

// ── NDVI & Vegetation ─────────────────────────────────────────
export function useCurrentNDVI(fieldId: string) {
  return useQuery({
    queryKey: QK.ndviCurrent(fieldId),
    queryFn:  () => vegetationApi.get(`/v1/ndvi/current/${fieldId}`).then(r => r.data),
    staleTime:10 * 60_000,
    enabled:  !!fieldId,
  });
}

export function useVegetationTimeseries(fieldId: string, days = 30) {
  return useQuery<{ timeseries: TimeseriesPoint[]; count: number }>({
    queryKey: QK.timeseries(fieldId, days),
    queryFn:  () => vegetationApi
      .get(`/v1/timeseries/${fieldId}`, { params: { days } })
      .then(r => r.data),
    staleTime:15 * 60_000,
    enabled:  !!fieldId,
  });
}

export function useAllFieldsNdvi() {
  const { user } = useAuthStore();
  const tid = (user as any)?.tenant_id ?? 'default';
  return useQuery({
    queryKey: QK.allFieldsNdvi(tid),
    queryFn:  () => vegetationApi.get('/v1/all_fields', { params: { tenant_id: tid } }).then(r => r.data),
    staleTime:10 * 60_000,
  });
}

export function useAnalyzeVegetation() {
  return useMutation<unknown, Error, { fieldId: string; dateFrom?: string }>({
    mutationFn: ({ fieldId, dateFrom }) =>
      vegetationApi.post('/v1/analyze', null, {
        params: { field_id: fieldId, ...(dateFrom ? { date_from: dateFrom } : {}) }
      }).then(r => r.data),
  });
}

// ── Indicators ────────────────────────────────────────────────
export function useIndicators(fieldId: string) {
  return useQuery({
    queryKey: QK.indicators(fieldId),
    queryFn:  () => indicatorsApi.get(`/v1/indicators/${fieldId}`).then(r => r.data),
    staleTime:5 * 60_000,
    enabled:  !!fieldId,
  });
}

// Real per-pixel indicator grid from raster-service (Sentinel-2 / Element84).
export function useIndicatorGrid(
  fieldId: string,
  index: GridIndex,
  date: string = 'latest',
  grid = 32,
) {
  return useQuery<IndicatorGridResponse>({
    queryKey: QK.indicatorGrid(fieldId, index, date),
    queryFn:  () => rasterApi
      .get(`/v1/fields/${fieldId}/indicator-grid`, { params: { index, date, grid } })
      .then(r => r.data),
    staleTime: 10 * 60_000,
    enabled:   !!fieldId,
    retry:     false,
  });
}

export function useIndicatorsCatalog() {
  return useQuery({
    queryKey: QK.indicatorsCatalog,
    queryFn:  () => indicatorsApi.get('/indicators/catalog').then(r => r.data),
    staleTime:60 * 60_000,
  });
}

// ── Weather ───────────────────────────────────────────────────
export function useWeatherForecast(lat = 15.05, lon = 45.55) {
  return useQuery({
    queryKey:        QK.weatherForecast(lat, lon),
    queryFn:         () => weatherApi.get('/weather/forecast', { params: { lat, lon } }).then(r => r.data),
    staleTime:       30 * 60_000,
    refetchInterval: 60 * 60_000,
  });
}

export function useWeatherWofost(lat = 15.05, lon = 45.55, days = 14) {
  return useQuery({
    queryKey: QK.weatherWofost(lat, lon, days),
    queryFn:  () => weatherApi.get('/weather/wofost_format', { params: { lat, lon, days } }).then(r => r.data),
    staleTime:60 * 60_000,
  });
}

export function useWeatherHistory(lat = 15.05, lon = 45.55, days = 30) {
  return useQuery({
    queryKey: QK.weatherHistory(lat, lon, days),
    queryFn:  () => weatherApi.get('/weather/historical', { params: { lat, lon, days } }).then(r => r.data),
    staleTime:30 * 60_000,
  });
}

// ── Soil ──────────────────────────────────────────────────────
export function useSoilParams(fieldId: string) {
  return useQuery({
    queryKey: QK.soilParams(fieldId),
    queryFn:  () => soilApi.get(`/soil/wofost_params/${fieldId}`).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!fieldId,
  });
}

export function useSoilNRecommendation(fieldId: string, targetYield = 3.5) {
  return useQuery({
    queryKey: QK.soilNRec(fieldId),
    queryFn:  () => soilApi.get('/soil/nitrogen/recommendation', {
      params: { field_id: fieldId, target_yield_t_ha: targetYield }
    }).then(r => r.data),
    staleTime:30 * 60_000,
    enabled:  !!fieldId,
  });
}

// ── Fields & Tasks ────────────────────────────────────────────
export function useFields() {
  const { user } = useAuthStore();
  const tid = (user as any)?.tenant_id ?? 'default';
  return useQuery({
    queryKey: QK.fields(tid),
    queryFn:  () => kongApi.get('/fields', { params: { tenant_id: tid } })
      .then(r => r.data).catch(() => ({ fields: [] })),
    staleTime:5 * 60_000,
  });
}

export function useTasks(fieldId?: string) {
  return useQuery<{ tasks: Task[] }>({
    queryKey: QK.tasks(fieldId),
    queryFn:  () => kongApi.get('/tasks', { params: fieldId ? { field_id: fieldId } : {} })
      .then(r => r.data).catch(() => ({ tasks: [] })),
    staleTime:2 * 60_000,
    refetchInterval: 5 * 60_000,
  });
}

export function useCompleteTask() {
  return useMutation({
    mutationFn: ({ taskId, photoUrl }: { taskId: string; photoUrl?: string }) =>
      kongApi.patch(`/tasks/${taskId}`, { status: 'completed', photo_url: photoUrl }).then(r => r.data),
  });
}

// ── Alerts ────────────────────────────────────────────────────
export function useAlerts() {
  const { user } = useAuthStore();
  const tid = (user as any)?.tenant_id ?? 'default';
  return useQuery({
    queryKey: QK.alerts(tid),
    queryFn:  () => indicatorsApi.get('/v1/alerts', { params: { tenant_id: tid } })
      .then(r => r.data).catch(() => ({ alerts: [] })),
    staleTime:60_000,
    refetchInterval: 2 * 60_000,
  });
}

// إقرار تنبيه (persist فعليّ عبر indicators). الواجهة تُحدّث تفاؤليّاً والـPATCH
// يثبّت الإقرار على الخادم. صدق: لو تعذّرت النقطة، الإقرار يبقى محلّيّاً للجلسة.
export function useAcknowledgeAlert() {
  return useMutation<unknown, Error, string>({
    mutationFn: (alertId) =>
      indicatorsApi.patch(`/indicators/alerts/${alertId}/acknowledge`).then(r => r.data),
  });
}

// ── v9: Supervisor Agent ──────────────────────────────────────
export function useAgentQuery() {
  const { user } = useAuthStore();
  return useMutation<AgentResponse, Error, {
    query: string; fieldId?: string; objectives?: string[]
  }>({
    mutationFn: ({ query, fieldId, objectives }) =>
      kongApi.post('/api/agent/query', {
        query,
        field_id:             fieldId,
        user_id:              (user as any)?.sub ?? 'unknown',
        tenant_id:            (user as any)?.tenant_id ?? 'default',
        preferred_objectives: objectives ?? ['balanced'],
      }).then(r => r.data),
  });
}

export function useFarmOptimize() {
  const { user } = useAuthStore();
  return useMutation<unknown, Error, { fieldId: string; objectives: string[] }>({
    mutationFn: ({ fieldId, objectives }) =>
      kongApi.post('/api/agent/optimize', {
        query: 'optimize farm', field_id: fieldId,
        user_id:   (user as any)?.sub ?? 'unknown',
        tenant_id: (user as any)?.tenant_id ?? 'default',
        preferred_objectives: objectives,
      }).then(r => r.data),
  });
}

// ── v9: Guardrails ────────────────────────────────────────────
export function useGuardrailsValidate() {
  const { user } = useAuthStore();
  return useMutation<GuardrailsResult, Error, {
    actionType: string;
    actionData: Record<string, unknown>;
    farmContext:Record<string, unknown>;
  }>({
    mutationFn: ({ actionType, actionData, farmContext }) =>
      kongApi.post('/api/guardrails/validate', {
        action_type:  actionType,
        action_data:  actionData,
        farm_context: farmContext,
        user_id:      (user as any)?.sub ?? 'unknown',
        tenant_id:    (user as any)?.tenant_id ?? 'default',
        auto_approve_low_risk: true,
      }).then(r => r.data),
  });
}

// ── Dashboard aggregation hook ─────────────────────────────────
export function useDashboardData(primaryFieldId = 'field_01') {
  const allNdvi    = useAllFieldsNdvi();
  const indicators = useIndicators(primaryFieldId);
  const weather    = useWeatherForecast();
  const tasks      = useTasks();
  const alerts     = useAlerts();
  const health     = useAllServicesHealth();
  const isLoading  = allNdvi.isLoading || indicators.isLoading;
  const isError    = indicators.isError;
  const refetch    = () => { allNdvi.refetch?.(); indicators.refetch?.(); };
  const data: any  = { allNdvi: allNdvi.data, indicators: indicators.data, weather: weather.data, tasks: tasks.data, alerts: alerts.data };
  return { data, refetch, allNdvi, indicators, weather, tasks, alerts, health, isLoading, isError };
}
