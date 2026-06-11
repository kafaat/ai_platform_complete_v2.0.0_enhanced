// SAHOOL v9.0 — src/hooks/useApi.ts — React Query hooks شاملة
import {
  useQuery, useMutation, useQueryClient,
  UseQueryResult, UseMutationResult,
} from '@tanstack/react-query';
import {
  kongApi, indicatorsApi, vegetationApi,
  weatherApi, soilApi, authApi, rasterApi,
  analyzeWaterSample, runPestEscalation, getFieldRecommendation,
  analyzeFieldIntelligence, getCostAnalytics,
  type WaterSampleInput, type WaterAnalysisResult,
  type PestEscalationInput, type PestEscalationResult,
  type FieldRecommendationInput, type RecommendationResult,
  type FieldIntelInput, type FieldIntelResult,
  type CostAnalytics,
  // ── الأنظمة الجديدة (شاشات الويب): مخزون/معدّات/أجهزة/ري تشغيلي/مرجعيّة/وثائق ──
  getInventoryItems, getExpiringBatches, createInventoryItem, addInventoryBatch,
  type InventoryItem, type ExpiringBatch, type NewInventoryItem, type NewInventoryBatch,
  fetchEquipment, createEquipment, fetchMaintenance, logMaintenance,
  type Equipment, type EquipmentCreateInput, type MaintenanceRecord, type MaintenanceCreateInput,
  listDevices, registerDevice, getDeviceTelemetry, recordTelemetry,
  type Device, type DeviceRegisterInput, type TelemetryPoint, type TelemetryRecordInput,
  listValves, createValve, setValveState, listSchedules, createSchedule, deleteSchedule,
  type Valve, type CreateValveInput, type ValveStateIntent,
  type IrrigationSchedule, type CreateScheduleInput,
  fetchMasterData, createMasterDataEntry,
  type MasterDataCategory, type MasterDataEntry, type MasterDataCreateInput,
  listDocuments, createDocument,
  type DocumentRecord, type DocumentCreateInput, type DocumentCategory,
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
  costAnalytics:    (tid: string)        => ['analytics', 'costs', tid],
  // الأنظمة الجديدة (شاشات الويب)
  inventoryItems:   (tid: string)        => ['inventory', 'items', tid],
  inventoryExpiring:(tid: string, d: number) => ['inventory', 'expiring', tid, d],
  equipment:        (tid: string)        => ['equipment', tid],
  maintenance:      (tid: string, eid: string) => ['equipment', tid, 'maintenance', eid],
  devices:          (tid: string)        => ['devices', tid],
  deviceTelemetry:  (id: string, n: number) => ['devices', 'telemetry', id, n],
  valves:           (tid: string)        => ['irrigation', 'valves', tid],
  schedules:        (tid: string, fid?: string) => ['irrigation', 'schedules', tid, fid ?? 'all'],
  masterData:       (tid: string, cat: string) => ['master-data', tid, cat],
  documents:        (tid: string, category?: string, fieldId?: string) =>
                       ['documents', tid, category ?? 'all', fieldId ?? 'all'],
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

// تحليل ماء الريّ (sahool-platform) — SAR/RSC + تصنيف. ربط حيّ، بلا تلفيق.
export function useWaterAnalysis() {
  return useMutation<WaterAnalysisResult, Error, WaterSampleInput>({
    mutationFn: (payload) => analyzeWaterSample(payload),
  });
}

// تصعيد الآفة (workflow durable + HIL). الاستئناف بنفس workflow_id + approval.
export function usePestEscalation() {
  return useMutation<PestEscalationResult, Error, PestEscalationInput>({
    mutationFn: (payload) => runPestEscalation(payload),
  });
}

// توصية لحقل — المحرّك الحقيقيّ (validation يُبنى خادميّاً). لا سيناريو مفبرَك.
export function useFieldRecommendation() {
  return useMutation<RecommendationResult, Error, FieldRecommendationInput>({
    mutationFn: (payload) => getFieldRecommendation(payload),
  });
}

// المايسترو — تحليل موحّد لحقل (operational truths + قرار + تنبيهات استباقيّة).
export function useFieldIntelligence() {
  return useMutation<FieldIntelResult, Error, FieldIntelInput>({
    mutationFn: (input) => analyzeFieldIntelligence(input),
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


// ── Inventory: مخزون المدخلات (حيّ، tenant-scoped + RBAC inventory:view/manage) ──
// لا fallback وهميّ: عند الخطأ (503 DB / 403 RBAC / انقطاع) يُرفض الاستعلام لتعرض
// الواجهة حالة خطأ صادقة بدل كميّات مُلفَّقة. الكاش مُفهرَس بالمستأجِر الفعّال.
export function useInventoryItems(): UseQueryResult<InventoryItem[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<InventoryItem[]>({
    queryKey: QK.inventoryItems(tid),
    queryFn:  () => getInventoryItems(),
    staleTime:2 * 60_000,
    retry:    false,
  });
}

export function useExpiringBatches(days = 30): UseQueryResult<ExpiringBatch[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<ExpiringBatch[]>({
    queryKey: QK.inventoryExpiring(tid, days),
    queryFn:  () => getExpiringBatches(days),
    staleTime:2 * 60_000,
    retry:    false,
  });
}

// إضافة صنف مخزون — يُبطِل كاش القائمة لإعادة الجلب الفعليّ بعد النجاح.
export function useCreateInventoryItem(): UseMutationResult<InventoryItem, Error, NewInventoryItem> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<InventoryItem, Error, NewInventoryItem>({
    mutationFn: (payload) => createInventoryItem(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.inventoryItems(tid) }); },
  });
}

// إضافة دفعة لصنف — يُبطِل كاش القائمة والصلاحيّة (الكميّات/الانتهاء تتغيّر).
export function useAddInventoryBatch(): UseMutationResult<unknown, Error, { itemId: string; batch: NewInventoryBatch }> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<unknown, Error, { itemId: string; batch: NewInventoryBatch }>({
    mutationFn: ({ itemId, batch }) => addInventoryBatch(itemId, batch),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: QK.inventoryItems(tid) });
      qc.invalidateQueries({ queryKey: ['inventory', 'expiring', tid] });
    },
  });
}

// ── Equipment: المعدّات + سجلّ الصيانة (حيّ، tenant-scoped + RBAC equipment:view/manage)
// لا fallback وهميّ: عند الخطأ (503 DB مُعطَّلة / 403 RBAC / انقطاع) يُرفض
// الاستعلام لتعرض الواجهة حالة صادقة بدل بيانات معدّات/تكلفة مُلفَّقة.
export function useEquipment(): UseQueryResult<Equipment[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<Equipment[]>({
    queryKey: QK.equipment(tid),
    queryFn:  () => fetchEquipment(),
    staleTime:2 * 60_000,
    retry:    false,
  });
}

export function useMaintenance(equipmentId: string): UseQueryResult<MaintenanceRecord[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<MaintenanceRecord[]>({
    queryKey: QK.maintenance(tid, equipmentId),
    queryFn:  () => fetchMaintenance(equipmentId),
    staleTime:60_000,
    retry:    false,
    enabled:  !!equipmentId,
  });
}

// تسجيل معدّة جديدة — يُبطِل كاش قائمة المعدّات للمستأجِر الحاليّ.
export function useCreateEquipment(): UseMutationResult<Equipment, Error, EquipmentCreateInput> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<Equipment, Error, EquipmentCreateInput>({
    mutationFn: (payload) => createEquipment(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.equipment(tid) }); },
  });
}

// تسجيل صيانة — يُبطِل سجلّ صيانة المعدّة + قائمة المعدّات (breakdown يقلب الحالة
// إلى broken خادميّاً، فالقائمة بحاجة تحديث).
export function useLogMaintenance(
  equipmentId: string,
): UseMutationResult<MaintenanceRecord, Error, MaintenanceCreateInput> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<MaintenanceRecord, Error, MaintenanceCreateInput>({
    mutationFn: (payload) => logMaintenance(equipmentId, payload),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: QK.maintenance(tid, equipmentId) });
      qc.invalidateQueries({ queryKey: QK.equipment(tid) });
    },
  });
}

// ── IoT Devices: أجهزة استشعار (حيّة، tenant-scoped + RBAC device:view) ──
// لا fallback وهميّ: عند الخطأ (503 DB / 403 RBAC / انقطاع) يُرفض الاستعلام
// لتعرض الواجهة حالة صادقة (StateViews) بدل قراءة مُلفَّقة.
export function useDevices(): UseQueryResult<Device[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<Device[]>({
    queryKey:        QK.devices(tid),
    queryFn:         () => listDevices(),
    staleTime:       60_000,
    refetchInterval: 60_000, // online مُحتسَب خادميّاً ⇒ نُحدّث دوريّاً
    retry:           false,
  });
}

export function useDeviceTelemetry(deviceId: string, limit = 20): UseQueryResult<TelemetryPoint[]> {
  return useQuery<TelemetryPoint[]>({
    queryKey: QK.deviceTelemetry(deviceId, limit),
    queryFn:  () => getDeviceTelemetry(deviceId, limit),
    staleTime:60_000,
    enabled:  !!deviceId,
    retry:    false,
  });
}

// تسجيل جهاز (device:manage). ينعش قائمة الأجهزة للمستأجِر بعد النجاح.
export function useRegisterDevice(): UseMutationResult<Device, Error, DeviceRegisterInput> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<Device, Error, DeviceRegisterInput>({
    mutationFn: (payload) => registerDevice(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.devices(tid) }); },
  });
}

// رفع قياس لجهاز (observation:record). ينعش قياسات الجهاز بعد النجاح.
export function useRecordTelemetry(
  deviceId: string,
): UseMutationResult<TelemetryPoint, Error, TelemetryRecordInput> {
  const qc = useQueryClient();
  return useMutation<TelemetryPoint, Error, TelemetryRecordInput>({
    mutationFn: (payload) => recordTelemetry(deviceId, payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['devices', 'telemetry', deviceId] }); },
  });
}

// ── Irrigation Ops: صمّامات + جداول الريّ (حيّة، tenant-scoped + RBAC) ──
// لا fallback وهميّ: عند الخطأ (503 DB مُعطَّلة / 403 RBAC / انقطاع) يُرفض
// الاستعلام لتعرض الواجهة حالة خطأ صادقة. الكاش مُفهرَس بالمستأجِر الفعّال.
export function useValves(): UseQueryResult<Valve[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<Valve[]>({
    queryKey: QK.valves(tid),
    queryFn:  () => listValves(),
    staleTime:60_000,
    retry:    false,
  });
}

export function useCreateValve(): UseMutationResult<Valve, Error, CreateValveInput> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<Valve, Error, CreateValveInput>({
    mutationFn: (payload) => createValve(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.valves(tid) }); },
  });
}

// تسجيل نيّة فتح/إغلاق الصمّام. التشغيل الفيزيائيّ يمرّ عبر HIL (موافقة بشريّة).
export function useSetValveState(): UseMutationResult<Valve, Error, { valveId: string; status: ValveStateIntent }> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<Valve, Error, { valveId: string; status: ValveStateIntent }>({
    mutationFn: ({ valveId, status }) => setValveState(valveId, status),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.valves(tid) }); },
  });
}

export function useSchedules(fieldId?: string): UseQueryResult<IrrigationSchedule[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<IrrigationSchedule[]>({
    queryKey: QK.schedules(tid, fieldId),
    queryFn:  () => listSchedules(fieldId),
    staleTime:60_000,
    retry:    false,
  });
}

export function useCreateSchedule(): UseMutationResult<IrrigationSchedule, Error, CreateScheduleInput> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<IrrigationSchedule, Error, CreateScheduleInput>({
    mutationFn: (payload) => createSchedule(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['irrigation', 'schedules', tid] }); },
  });
}

export function useDeleteSchedule(): UseMutationResult<void, Error, string> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<void, Error, string>({
    mutationFn: (scheduleId) => deleteSchedule(scheduleId),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['irrigation', 'schedules', tid] }); },
  });
}

// ── Master Data: كتالوج البيانات المرجعيّة (tenant-scoped + RBAC master_data) ──
// لا fallback وهميّ: عند الخطأ (503 DB مُعطَّلة / 403 RBAC / انقطاع) يُرفض الاستعلام
// لتعرض الواجهة حالة خطأ صادقة بدل بيانات مرجعيّة مُلفَّقة تُبنى عليها قرارات.
export function useMasterData(
  category: MasterDataCategory,
): UseQueryResult<MasterDataEntry[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<MasterDataEntry[]>({
    queryKey: QK.masterData(tid, category),
    queryFn:  () => fetchMasterData(category),
    staleTime:5 * 60_000,
    retry:    false,
    enabled:  !!category,
  });
}

// إضافة مُدخَل مرجعيّ. عند النجاح نُبطِل كاش الفئة المعنيّة لإعادة الجلب الحيّ.
// 409 (تكرار tenant,category,code) يُرفَع كخطأ ليتعامل معه الـUI بصدق.
export function useCreateMasterData(): UseMutationResult<
  MasterDataEntry, Error, MasterDataCreateInput
> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<MasterDataEntry, Error, MasterDataCreateInput>({
    mutationFn: (payload) => createMasterDataEntry(payload),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: QK.masterData(tid, vars.category) });
    },
  });
}

// ── Documents: سجلّ الوثائق (حيّ، tenant-scoped + RBAC document:view/manage) ──
// سجلّ بيانات وصفيّة فقط (الملفّ في تخزين الكائنات). لا fallback وهميّ: عند الخطأ
// (503 DB مُعطَّلة / 403 RBAC / انقطاع) يُرفض الاستعلام لتعرض الواجهة حالة صادقة.
export function useDocuments(
  category?: DocumentCategory,
  fieldId?: string,
): UseQueryResult<DocumentRecord[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<DocumentRecord[]>({
    queryKey: QK.documents(tid, category, fieldId),
    queryFn:  () => listDocuments({ category, field_id: fieldId }),
    staleTime:5 * 60_000,
    retry:    false,
  });
}

// تسجيل وثيقة (بيانات وصفيّة + storage_ref). ليس رفعاً للملفّ — يسجّل المرجع فقط.
// بعد النجاح نُبطِل كاش الوثائق للمستأجِر الحاليّ ليُعاد الجلب.
export function useCreateDocument(): UseMutationResult<DocumentRecord, Error, DocumentCreateInput> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<DocumentRecord, Error, DocumentCreateInput>({
    mutationFn: (payload) => createDocument(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['documents', tid] }); },
  });
}

// ── Analytics: تحليلات التكلفة (حيّة، tenant-scoped + RBAC analytics:view) ──
// لا fallback وهميّ: عند الخطأ (503 DB مُعطَّلة / 403 RBAC / انقطاع) يُرفض
// الاستعلام لتعرض الواجهة حالة خطأ صادقة بدل رقم مالي مُلفَّق.
export function useCostAnalytics(): UseQueryResult<CostAnalytics> {
  // FIX (مراجعة): المستأجِر الفعّال في المتجر هو tenantId (لا user.tenant_id الذي
  // قد يكون غائباً) — نُفهرِس الكاش به لتجنّب تصادم كاش بين المستأجرين عند التبديل.
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<CostAnalytics>({
    queryKey: QK.costAnalytics(tid),
    queryFn:  () => getCostAnalytics(),
    staleTime:5 * 60_000,
    retry:    false,
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
