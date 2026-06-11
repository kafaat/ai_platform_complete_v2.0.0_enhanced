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
  getFarmSummary, getFieldReportSummary, getSeasonReportSummary,
  type WaterSampleInput, type WaterAnalysisResult,
  type PestEscalationInput, type PestEscalationResult,
  type FieldRecommendationInput, type RecommendationResult,
  type FieldIntelInput, type FieldIntelResult,
  type CostAnalytics,
  type FarmSummary, type FieldReportSummary, type SeasonReportSummary,
  // ── الأنظمة الجديدة (شاشات الويب): مخزون/معدّات/أجهزة/ري تشغيلي/مرجعيّة/وثائق ──
  getInventoryItems, getExpiringBatches, createInventoryItem, addInventoryBatch,
  type InventoryItem, type ExpiringBatch, type NewInventoryItem, type NewInventoryBatch,
  fetchEquipment, createEquipment, fetchMaintenance, logMaintenance,
  type Equipment, type EquipmentCreateInput, type MaintenanceRecord, type MaintenanceCreateInput,
  fetchActivities, createActivity,
  type Activity, type ActivityCreateInput,
  fetchIrrigationAdvice, fetchDiseaseRisk,
  type IrrigationAdvice, type DiseaseRisk,
  fetchFieldRecommendations,
  type FieldRecommendationsResult,
  fetchAlerts, createAlert, acknowledgeAlert, evaluateFieldAlerts,
  type AlertRecord, type AlertCreateInput, type AlertListFilters, type AlertEvaluateResult,
  fetchNotificationPreferences, updateNotificationPreferences,
  type NotificationPreferences,
  listDevices, registerDevice, getDeviceTelemetry, recordTelemetry,
  type Device, type DeviceRegisterInput, type TelemetryPoint, type TelemetryRecordInput,
  listValves, createValve, setValveState, listSchedules, createSchedule, deleteSchedule,
  type Valve, type CreateValveInput, type ValveStateIntent,
  type IrrigationSchedule, type CreateScheduleInput,
  fetchMasterData, createMasterDataEntry,
  type MasterDataCategory, type MasterDataEntry, type MasterDataCreateInput,
  listDocuments, createDocument,
  type DocumentRecord, type DocumentCreateInput, type DocumentCategory,
  // ── الحوكمة والتدقيق: أصل/أحداث/أوامر كيان + مفاتيح المشاركة ──
  listSharingKeys, createSharingKey,
  type SharingKey, type NewSharingKey, type SharingKeyCreated,
  // ── المزارع (بوّابة التأهيل): سرد + إنشاء ──
  fetchFarms, createFarm,
  type Farm, type FarmCreateInput, type FarmCreated,
  // ── تفاصيل الحقل المتقدّمة (v37): قراءة + تحديث جزئيّ (ملء تدريجيّ) ──
  fetchFieldDetail, updateField,
  type FieldDetail, type FieldUpdatePatch,
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
  fieldDetail:      (tid: string, fid: string) => ['field-detail', tid, fid],
  farms:            (tid: string)        => ['farms', tid],
  tasks:            (fid?: string)       => ['tasks', fid ?? 'all'],
  activities:       (tid: string, fid: string) => ['activities', tid, fid],
  irrigationAdvice: (tid: string, fid: string) => ['weather-advice', 'irrigation', tid, fid],
  diseaseRisk:      (tid: string, fid: string) => ['weather-advice', 'disease', tid, fid],
  fieldRecs:        (tid: string, fid: string) => ['field-recommendations', tid, fid],
  alerts:           (tid: string)        => ['alerts', tid],
  notifPrefs:       (tid: string)        => ['notifications', 'preferences', tid],
  indicatorGrid:    (fid: string, index: string, date: string) => ['indicator-grid', fid, index, date],
  prescription:     (fid: string, index: string, date: string, n: number, baseRate: number | null, strategy: string) =>
                       ['prescription', fid, index, date, n, baseRate ?? 'auto', strategy],
  costAnalytics:    (tid: string)        => ['analytics', 'costs', tid],
  farmSummary:      (tid: string)        => ['reports', 'farm-summary', tid],
  fieldReport:      (tid: string, fid: string) => ['reports', 'field', tid, fid],
  seasonReport:     (tid: string, sid: string) => ['reports', 'season', tid, sid],
  // الأنظمة الجديدة (شاشات الويب)
  inventoryItems:   (tid: string)        => ['inventory', 'items', tid],
  inventoryExpiring:(tid: string, d: number) => ['inventory', 'expiring', tid, d],
  equipment:        (tid: string)        => ['equipment', tid],
  maintenance:      (tid: string, eid: string) => ['equipment', tid, 'maintenance', eid],
  devices:          (tid: string)        => ['devices', tid],
  deviceTelemetry:  (tid: string, id: string, n: number) => ['devices', 'telemetry', tid, id, n],
  valves:           (tid: string)        => ['irrigation', 'valves', tid],
  schedules:        (tid: string, fid?: string) => ['irrigation', 'schedules', tid, fid ?? 'all'],
  masterData:       (tid: string, cat: string) => ['master-data', tid, cat],
  documents:        (tid: string, category?: string, fieldId?: string) =>
                       ['documents', tid, category ?? 'all', fieldId ?? 'all'],
  sharingKeys:      (tid: string, includeRevoked: boolean) =>
                       ['sharing', 'keys', tid, includeRevoked],
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
export type GridIndex = 'ndvi' | 'ndmi' | 'ndwi' | 'salinity' | 'ndre' | 'msavi' | 'evi' | 'moisture';

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

// ── Prescription / management zones (raster-service quantile binning) ──
export interface PrescriptionZone {
  zone: string;            // low | medium | high | zone_N
  pixel_count: number;
  pct: number;
  value_range: [number, number];
  rate?: number;           // معدّل موصى به (إن مُرّر base_rate)
  factor?: number;
}

export interface PrescriptionResponse {
  field_id: string;
  index: string;
  date: string;
  real_data: boolean;
  source: string;
  n_zones: number;
  total_pixels: number;
  field_mean: number;
  field_cv: number | null;
  zones: PrescriptionZone[];
  base_rate?: number;
  strategy?: string;
  prescription?: { zone: string; pct_of_field: number; rate: number; factor: number }[];
}

// Management zones + variable-rate prescription from the indicator grid.
export function useFieldPrescription(
  fieldId: string,
  index: GridIndex,
  date: string = 'latest',
  opts: { nZones?: number; baseRate?: number; strategy?: string; enabled?: boolean } = {},
) {
  const { nZones = 3, baseRate, strategy = 'compensate', enabled = true } = opts;
  return useQuery<PrescriptionResponse>({
    // baseRate/strategy في المفتاح: تغييرهما يُبطل الكاش ويُعيد الجلب (الطلب POST يعتمدهما).
    queryKey: QK.prescription(fieldId, index, date, nZones, baseRate ?? null, strategy),
    queryFn:  () => rasterApi
      .post(`/v1/fields/${fieldId}/prescription`, {
        index, date, n_zones: nZones, base_rate: baseRate ?? null, strategy,
      })
      .then(r => r.data),
    staleTime: 10 * 60_000,
    enabled:   !!fieldId && enabled,
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
    // الخلفيّة: GET /api/v1/fields تُرجع قائمة FieldSummary (مع lat/lon/geometry
    // لرسم المضلّع). نطبّعها إلى {fields:[...]}. لا ابتلاع صامت ⇒ الفشل يظهر
    // كـisError (لا ارتداد إلى بيانات وهميّة — كان /fields الخاطئ يرتدّ بصمت).
    queryFn:  () => kongApi.get('/api/v1/fields')
      .then(r => ({ fields: Array.isArray(r.data) ? r.data : (r.data?.fields ?? []) })),
    staleTime:5 * 60_000,
  });
}

// ── Field Detail: تفاصيل الحقل المتقدّمة (sahool-platform v37) — ملء تدريجيّ ──
// قراءة حيّة (field:view) عند فتح لوحة التفاصيل فقط (enabled على fieldId). لا
// fallback وهميّ: عند الخطأ (503 DB / 404 حقل / 403) يُرفض الاستعلام لتعرض
// الواجهة حالة صادقة (StateViews).
export function useFieldDetail(fieldId?: string): UseQueryResult<FieldDetail, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<FieldDetail, Error>({
    queryKey: QK.fieldDetail(tid, fieldId ?? 'none'),
    queryFn:  () => fetchFieldDetail(fieldId as string),
    enabled:  !!fieldId,
    staleTime:60_000,
    retry:    false,
  });
}

// تحديث جزئيّ لتفاصيل حقل — يُبطِل كاش التفاصيل وقائمة الحقول للمستأجِر الحاليّ.
// 503 DB / 404 حقل / 403 RBAC يُرفع ليعرض الـUI خطأً صادقاً (لا حفظ تفاؤليّ صامت).
export function useUpdateField(
  fieldId: string,
): UseMutationResult<FieldDetail, Error, FieldUpdatePatch> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<FieldDetail, Error, FieldUpdatePatch>({
    mutationFn: (patch) => updateField(fieldId, patch),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: QK.fieldDetail(tid, fieldId) });
      qc.invalidateQueries({ queryKey: QK.fields(tid) });
    },
  });
}

// ── Farms: المزارع (حيّة، tenant-scoped + RBAC farm:view/create) ──
// تُستخدم لبوّابة التأهيل: مستخدم جديد بلا مزرعة يُجبَر على إنشاء واحدة قبل اللوحة.
// لا fallback وهميّ: عند الخطأ (503 DB مُعطَّلة / 403 RBAC / انقطاع) يُرفض الاستعلام.
export function useFarms(enabled = true): UseQueryResult<Farm[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<Farm[]>({
    queryKey: QK.farms(tid),
    queryFn:  () => fetchFarms(),
    staleTime:5 * 60_000,
    retry:    false,
    enabled,
  });
}

// إنشاء مزرعة — يُبطِل كاش قائمة المزارع للمستأجِر الحاليّ (بوّابة التأهيل تتجاوز
// فور وجود مزرعة). 503 عند تعطيل DB / 403 RBAC يُرفع ليعرض النموذج خطأً صادقاً.
export function useCreateFarm(): UseMutationResult<FarmCreated, Error, FarmCreateInput> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<FarmCreated, Error, FarmCreateInput>({
    mutationFn: (payload) => createFarm(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.farms(tid) }); },
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

// ── Field Activities: العمليّات الزراعيّة لكلّ حقل (sahool-platform v35) ──
// ربط حيّ بلا fallback وهميّ: عند الخطأ (503 DB / 404 حقل / 403) يُرفض الاستعلام
// لتعرض الواجهة حالة صادقة (StateViews). مُفعَّل فقط عند وجود fieldId.
export function useActivities(fieldId?: string): UseQueryResult<Activity[], Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<Activity[], Error>({
    queryKey: QK.activities(tid, fieldId ?? 'none'),
    queryFn:  () => fetchActivities(fieldId as string),
    staleTime:2 * 60_000,
    enabled:  !!fieldId,
  });
}

// تسجيل عمليّة لحقل — يُبطِل كاش عمليّات الحقل للمستأجِر الحاليّ.
export function useCreateActivity(
  fieldId: string,
): UseMutationResult<Activity, Error, ActivityCreateInput> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<Activity, Error, ActivityCreateInput>({
    mutationFn: (payload) => createActivity(fieldId, payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.activities(tid, fieldId) }); },
  });
}

// ── Weather advice: توصية الريّ + مخاطر الأمراض لكلّ حقل (Sprint 5a) ──
// ربط حيّ بلا fallback وهميّ: عند الخطأ (503 طقس/قاعدة، 404 حقل، 422 بلا
// إحداثيّات، 403) يُرفض الاستعلام لتعرض الواجهة حالة صادقة. مُفعَّل فقط مع fieldId.
export function useIrrigationAdvice(fieldId?: string): UseQueryResult<IrrigationAdvice, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<IrrigationAdvice, Error>({
    queryKey: QK.irrigationAdvice(tid, fieldId ?? 'none'),
    queryFn:  () => fetchIrrigationAdvice(fieldId as string),
    staleTime:10 * 60_000,
    retry:    false,
    enabled:  !!fieldId,
  });
}

export function useDiseaseRisk(fieldId?: string): UseQueryResult<DiseaseRisk, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<DiseaseRisk, Error>({
    queryKey: QK.diseaseRisk(tid, fieldId ?? 'none'),
    queryFn:  () => fetchDiseaseRisk(fieldId as string),
    staleTime:10 * 60_000,
    retry:    false,
    enabled:  !!fieldId,
  });
}

// ── Unified recommendations: عمود التوصيات الموحَّد لكلّ حقل ──
// يجمع الخادم الريّ + التسميد + الأمراض + الحصاد مفروزاً بالأولويّة (تدهور رشيق
// عند تعذّر الطقس). ربط حيّ بلا fallback وهميّ: عند الخطأ (503/404/403) يُرفض
// الاستعلام لتعرض الواجهة حالة صادقة. مُفعَّل فقط مع fieldId.
export function useFieldRecommendations(
  fieldId?: string,
): UseQueryResult<FieldRecommendationsResult, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<FieldRecommendationsResult, Error>({
    queryKey: QK.fieldRecs(tid, fieldId ?? 'none'),
    queryFn:  () => fetchFieldRecommendations(fieldId as string),
    staleTime:10 * 60_000,
    retry:    false,
    enabled:  !!fieldId,
  });
}

// ── Alerts: التنبيهات الزراعيّة المُصنَّفة لكلّ مستأجِر (sahool-platform v36) ──
// ربط حيّ بلا fallback وهميّ: عند الخطأ (503 DB / 403 RBAC) يُرفض الاستعلام
// لتعرض الواجهة حالة صادقة (StateViews) بدل تنبيهات ملفّقة.
export function useAlerts(
  filters: AlertListFilters = {},
): UseQueryResult<AlertRecord[], Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<AlertRecord[], Error>({
    queryKey: [...QK.alerts(tid), filters.status ?? 'all', filters.severity ?? 'all'],
    queryFn:  () => fetchAlerts(filters),
    staleTime:60_000,
    refetchInterval: 2 * 60_000,
  });
}

// إقرار تنبيه (persist فعليّ على sahool-platform) — يُبطِل كاش تنبيهات المستأجِر
// ليُعاد جلب القائمة بالحالة المُثبَّتة على الخادم.
export function useAcknowledgeAlert(): UseMutationResult<AlertRecord, Error, string> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<AlertRecord, Error, string>({
    mutationFn: (alertId) => acknowledgeAlert(alertId),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.alerts(tid) }); },
  });
}

// إنشاء تنبيه — يُبطِل كاش تنبيهات المستأجِر.
export function useCreateAlert(): UseMutationResult<AlertRecord, Error, AlertCreateInput> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<AlertRecord, Error, AlertCreateInput>({
    mutationFn: (payload) => createAlert(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.alerts(tid) }); },
  });
}

// تقييم تنبيهات حقل تلقائيّاً (يُولّد تنبيهات من ظروف الحقل الحيّة، sahool-platform)
// — يُبطِل كاش تنبيهات المستأجِر ليُعاد جلب القائمة بالتنبيهات المُولَّدة حديثاً.
export function useEvaluateAlerts(): UseMutationResult<AlertEvaluateResult, Error, string> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<AlertEvaluateResult, Error, string>({
    mutationFn: (fieldId) => evaluateFieldAlerts(fieldId),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.alerts(tid) }); },
  });
}

// ── Notification Preferences: قنوات تسليم التنبيهات لكلّ مستخدم (v9+v38) ──
// ربط حيّ بلا fallback وهميّ: عند الخطأ (503 DB / 403 RBAC) يُرفض الاستعلام
// لتعرض الواجهة حالة صادقة. الخادم يُرجع تفضيلات افتراضيّة (كلّ القنوات مُعطَّلة)
// لا 404 إن لم يُحفَظ شيء بعد — فالنموذج يبدأ فارغاً صادقاً.
export function useNotificationPreferences(): UseQueryResult<NotificationPreferences, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<NotificationPreferences, Error>({
    queryKey: QK.notifPrefs(tid),
    queryFn:  () => fetchNotificationPreferences(),
    staleTime:60_000,
    retry:    false,
  });
}

// حفظ تفضيلات الإشعار (UPSERT على الخادم) — يُبطِل كاش التفضيلات للمستأجِر الحاليّ.
// 503 DB / 403 RBAC / 422 (نوع حدث/خطورة غير معروفة) يُرفع ليعرض النموذج خطأً صادقاً.
export function useUpdateNotificationPreferences(): UseMutationResult<
  NotificationPreferences, Error, NotificationPreferences
> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<NotificationPreferences, Error, NotificationPreferences>({
    mutationFn: (payload) => updateNotificationPreferences(payload),
    onSuccess:  (data) => { qc.setQueryData(QK.notifPrefs(tid), data); },
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
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<TelemetryPoint[]>({
    queryKey: QK.deviceTelemetry(tid, deviceId, limit),
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
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<TelemetryPoint, Error, TelemetryRecordInput>({
    // مفتاح جزئيّ مفهرَس بالمستأجِر ⇒ يُبطِل كل القياسات (مهما كان الحدّ) لهذا الجهاز.
    mutationFn: (payload) => recordTelemetry(deviceId, payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['devices', 'telemetry', tid, deviceId] }); },
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

// ── Governance: مفاتيح المشاركة (حيّة، tenant-scoped + RBAC user:invite) ──
// لا fallback وهميّ: 503 DB مُعطَّلة / 403 RBAC يُرفع لتعرض الواجهة حالة صادقة.
export function useSharingKeys(includeRevoked = false): UseQueryResult<SharingKey[]> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<SharingKey[]>({
    queryKey: QK.sharingKeys(tid, includeRevoked),
    queryFn:  () => listSharingKeys(includeRevoked).then((r) => r.keys),
    staleTime:60_000,
    retry:    false,
  });
}

// إنشاء مفتاح مشاركة. النصّ الكامل يُعاد مرّة واحدة فقط (يعرضه المُستدعي ثمّ يُهمَل).
export function useCreateSharingKey(): UseMutationResult<SharingKeyCreated, Error, NewSharingKey> {
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<SharingKeyCreated, Error, NewSharingKey>({
    mutationFn: (payload) => createSharingKey(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['sharing', 'keys', tid] }); },
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

// ── Reports: تقارير وتحليلات (حيّة، tenant-scoped + RBAC field:view) ──
// لا fallback وهميّ: عند الخطأ (503 DB / 404 / 403) يُرفض الاستعلام لتعرض
// الواجهة حالة صادقة (StateViews) بدل أرقام مُلفَّقة.
export function useFarmSummary(): UseQueryResult<FarmSummary> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<FarmSummary>({
    queryKey: QK.farmSummary(tid),
    queryFn:  () => getFarmSummary(),
    staleTime:5 * 60_000,
    retry:    false,
  });
}

export function useFieldReport(fieldId?: string): UseQueryResult<FieldReportSummary, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<FieldReportSummary, Error>({
    queryKey: QK.fieldReport(tid, fieldId ?? 'none'),
    queryFn:  () => getFieldReportSummary(fieldId as string),
    enabled:  !!fieldId,
    staleTime:60_000,
    retry:    false,
  });
}

export function useSeasonReport(seasonId?: string): UseQueryResult<SeasonReportSummary, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<SeasonReportSummary, Error>({
    queryKey: QK.seasonReport(tid, seasonId ?? 'none'),
    queryFn:  () => getSeasonReportSummary(seasonId as string),
    enabled:  !!seasonId,
    staleTime:60_000,
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
