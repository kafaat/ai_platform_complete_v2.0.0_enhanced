// SAHOOL v9.0 — src/hooks/useApi.ts — React Query hooks شاملة
import {
  useQuery, useMutation, useQueryClient,
  UseQueryResult, UseMutationResult,
} from '@tanstack/react-query';
import {
  kongApi, indicatorsApi, vegetationApi,
  weatherApi, soilApi, authApi, rasterApi,
  analyzeWaterSample, runPestEscalation, getFieldRecommendation,
  analyzeFieldIntelligence, startAnalyzeFieldIntelligence, getFieldIntelligenceJob, cancelFieldIntelligenceJob, getCostAnalytics,
  getYieldAnalysis, type YieldAnalysisResult,
  getFarmSummary, getFieldReportSummary, getSeasonReportSummary,
  simulateSeason, type SeasonSimResult,
  computeIrrigationPlan, type IrrigationPlanInput, type IrrigationPlanResult,
  computeCropDecision, type CropDecisionInput, type CropDecisionResult,
  fetchSeasons, type SeasonSummary,
  type WaterSampleInput, type WaterAnalysisResult,
  type PestEscalationInput, type PestEscalationResult,
  type FieldRecommendationInput, type RecommendationResult,
  type FieldIntelInput, type FieldIntelResult, type FieldIntelJobStatus,
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
  fetchAlerts, createAlert, acknowledgeAlert, evaluateFieldAlerts, runAllFieldsAlerts,
  type AlertRecord, type AlertCreateInput, type AlertListFilters, type AlertEvaluateResult,
  type AlertsRunResult,
  fetchNotificationPreferences, updateNotificationPreferences,
  type NotificationPreferences,
  listDevices, registerDevice, getDeviceTelemetry, recordTelemetry, getFieldSoilMoisture,
  type Device, type DeviceRegisterInput, type TelemetryPoint, type TelemetryRecordInput,
  type FieldSoilMoisture,
  fetchFleetHealth, type FleetHealth,
  fetchOperationsSummary, type OperationsSummary,
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
  // ── وصفات المعدّل المتغيّر اليدويّة (Manual VRT، v95): سرد + حفظ ──
  fetchPrescriptions, createPrescription,
  type SavedPrescription, type PrescriptionListResponse, type PrescriptionCreateInput,
  // ── إعادة تشغيل الموسم (Agronomic Replay): خطّ زمنيّ واحد قابل للـscrub ──
  fetchAgronomicReplay, type AgronomicReplayResult,
  fetchFieldTerrain, type FieldTerrain,
  fetchFieldState, type FieldStateFull,
  fetchFieldImageryTimeline, type ImageryTimeline,
  refreshFieldImagery,
  // ── مساحة عمل الحقل (Field Workspace Map): ملخّص + طبقات + خطّ زمنيّ ──
  fetchFieldWorkspace, type FieldWorkspace,
  // ── استيراد حدّ حقل من ملفّ/نقاط GPS (بدل الرسم اليدويّ) ──
  importField, type FieldImportInput,
  // ── دمج/انقسام الحقول ذرّيّاً (نقطتا backend تستبدلان لاذرّيّة الواجهة) ──
  mergeFields, splitField, type FieldMergeInput, type FieldSplitInput,
  // ── حالة المعايرة الإقليميّة (قراءة فقط) ──
  fetchCalibration, type CalibrationOverview,
  // ── منضدة المعايرة (Calibration Workbench): مقارنة/اقتراح/موافقة/رفض/تدقيق ──
  fetchRegionCalibration, fetchResolvedCalibration,
  type CalibrationProfile, type ResolvedCalibration,
  proposeCalibrationValues, setRegionOverride, deleteRegionOverride, applyAdaptFromEvidence,
  fetchCalibrationOverrides, fetchCalibrationAudit,
  type CalibrationValuesInput, type CalibrationValidation,
  type CalibrationOverrideResult, type AdaptApplyResult, type AdaptApplyInput,
  type CalibrationOverridesResult, type CalibrationAudit,
  // ── سلسلة النَّسَب المُدامة + الدليل المتراكم (قراءة فقط) ──
  fetchDecisionLineage, type DecisionLineage,
  fetchPersistedEvidence, type PersistedEvidence,
  // ── خريطة الدليل (Evidence Map): مستوى الدليل خلف قرارات كلّ حقل (قراءة فقط) ──
  fetchEvidenceMap, type EvidenceMapResult,
  // ── توائم الأجهزة وثقة الحسّاس (Device Twin): توأم رقميّ + درجة ثقة لكلّ جهاز ──
  fetchDeviceTwin, type DeviceTwinResult,
  // ── رصد حلقة التنفيذ (Execution Feedback): القرار→التنفيذ→النتيجة (قراءة فقط) ──
  fetchExecutionFeedback, type ExecutionFeedbackResult,
  // ── لوحة رصد التعلّم/النَّسَب (قراءة فقط) ──
  fetchDecisionRecords, type DecisionRecordsResult,
  fetchLearningSummary, type LearningSummary,
  // ── Decision Studio: شرح القرار + إعادة التشغيل (قراءة فقط) ──
  fetchDecisionExplain, type DecisionExplainResult,
  // ── Agronomic Timeline: الخطّ الزمنيّ الموحّد للحقل (قراءة فقط) ──
  fetchUnifiedTimeline, type UnifiedTimeline,
  fetchFieldGeometryHistory, type FieldGeometryHistory,
  // ── Decision Confidence: ثقة القرار الموحَّدة لحقل (قراءة فقط) ──
  fetchDecisionConfidence, type DecisionConfidenceResult,
  listLabSamples, createLabSample, submitSoilLabResult, fetchLabDecisionContext,
  type LabSampleRecord, type LabSampleCreateInput, type SoilLabResultInput,
  type SoilLabAnalysisResult, type LabDecisionContext,
  buildProductivityZones, buildZoneSamplingPlan, fetchDailyAiBrief,
  type ProductivityObservationInput, type ProductivityZoneResult,
  type ZoneSamplingPlanResult, type DailyAiBriefResult,
} from '../services/api';
import { useAuthStore } from './useAuth';
import { useDashboardKPIs } from './useIndicators';

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
  fieldWorkspace:   (tid: string, fid: string) => ['field-workspace', tid, fid],
  farms:            (tid: string)        => ['farms', tid],
  tasks:            (fid?: string)       => ['tasks', fid ?? 'all'],
  activities:       (tid: string, fid: string) => ['activities', tid, fid],
  seasons:          (tid: string, fid: string) => ['seasons', tid, fid],
  irrigationAdvice: (tid: string, fid: string) => ['weather-advice', 'irrigation', tid, fid],
  diseaseRisk:      (tid: string, fid: string) => ['weather-advice', 'disease', tid, fid],
  fieldRecs:        (tid: string, fid: string) => ['field-recommendations', tid, fid],
  alerts:           (tid: string)        => ['alerts', tid],
  notifPrefs:       (tid: string)        => ['notifications', 'preferences', tid],
  indicatorGrid:    (fid: string, index: string, date: string) => ['indicator-grid', fid, index, date],
  fieldChange:      (fid: string, index: string, dateA: string, dateB: string) =>
                       ['field-change', fid, index, dateA, dateB],
  fieldTimeseries:  (fid: string, index: string, dates: string) =>
                       ['field-timeseries', fid, index, dates],
  prescription:     (fid: string, index: string, date: string, n: number, baseRate: number | null, strategy: string) =>
                       ['prescription', fid, index, date, n, baseRate ?? 'auto', strategy],
  savedPrescriptions: (tid: string, fid: string) => ['saved-prescriptions', tid, fid],
  costAnalytics:    (tid: string)        => ['analytics', 'costs', tid],
  yieldAnalysis:    (tid: string, fid: string, season: string) => ['analysis', 'yield', tid, fid, season],
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
  fieldSoilMoisture:(tid: string, fid: string) => ['fields', 'soil-moisture', tid, fid],
  valves:           (tid: string)        => ['irrigation', 'valves', tid],
  schedules:        (tid: string, fid?: string) => ['irrigation', 'schedules', tid, fid ?? 'all'],
  masterData:       (tid: string, cat: string) => ['master-data', tid, cat],
  documents:        (tid: string, category?: string, fieldId?: string) =>
                       ['documents', tid, category ?? 'all', fieldId ?? 'all'],
  sharingKeys:      (tid: string, includeRevoked: boolean) =>
                       ['sharing', 'keys', tid, includeRevoked],
  health:                                   ['health', 'all'],
  labSamples:       (tid: string, fid?: string) => ['lab', 'samples', tid, fid ?? 'all'],
  labContext:       (tid: string, fid: string) => ['lab', 'context', tid, fid],
  productivityZones:(tid: string, fid: string, n: number) => ['productivity-zones', tid, fid, n],
  zoneSamplingPlan: (tid: string, fid: string, n: number) => ['zone-sampling-plan', tid, fid, n],
  dailyAiBrief:     (tid: string, fid: string) => ['daily-ai-brief', tid, fid],
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
export type GridIndex = 'ndvi' | 'ndmi' | 'ndwi' | 'salinity' | 'ndre' | 'msavi' | 'evi' | 'moisture' | 'msi' | 'savi' | 'gndvi';

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
  const tid = user?.tenant_id ?? 'default';
  return useQuery({
    queryKey: QK.allFieldsNdvi(tid),
    queryFn:  () => vegetationApi.get('/v1/all_fields', { params: { tenant_id: tid } }).then(r => r.data),
    staleTime:10 * 60_000,
  });
}

// FIX (ربط حيّ): الخادم (vegetation-analysis-service) يكشف GET /v1/analyze بمعاملات
// استعلام لا POST بجسم — كان POST يرتدّ 405. صُحّح الفعل/الشكل ليطابق الخادم الفعليّ.
// FIX (أثر مرئيّ): «تحليل الآن» كان يبدو بلا أثر لأنّه لم يُبطِل المخبّأ — فلا يُعاد
// جلب السلسلة الزمنيّة/المؤشّر بعد التحليل. نُبطِل الآن كلّ استعلامات الحقل المتأثّرة
// (raster timeseries لكلّ المؤشّرات + vegetation timeseries + NDVI الحاليّ + شبكة
// المؤشّر + المؤشّرات) بمطابقة البادئة، فيُحدَّث الشريط الزمنيّ والقيم فور اكتمال التحليل.
export function useAnalyzeVegetation() {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { fieldId: string; dateFrom?: string; geometry?: unknown }>({
    // UI hotfix: معرّفات صفحة الأقمار هي معرّفات المنصّة (fld_*) يملكها raster عبر المنصّة؛
    // vegetation-analysis-service /v1/analyze لا يملكها فيُرجِع «field_id not found». لذا
    // «تحليل الآن» يُطلق مسار تحديث الصور القانونيّ (يتحقّق من الملكيّة ويُوكّل لـraster
    // بهندسة الحقل) — لا احتياطيّ مُختلَق.
    mutationFn: ({ fieldId, dateFrom, geometry }) => refreshFieldImagery(fieldId, dateFrom ?? null, geometry),
    onSuccess: (_data, { fieldId }) => {
      qc.invalidateQueries({ queryKey: ['field-timeseries', fieldId] });   // شريط raster الزمنيّ (كلّ المؤشّرات)
      qc.invalidateQueries({ queryKey: ['vegetation', 'ts', fieldId] });   // سلسلة vegetation البديلة
      qc.invalidateQueries({ queryKey: QK.ndviCurrent(fieldId) });          // NDVI الحاليّ
      qc.invalidateQueries({ queryKey: ['indicator-grid', fieldId] });      // شبكة المؤشّر (كلّ المؤشّرات/التواريخ)
      qc.invalidateQueries({ queryKey: QK.indicators(fieldId) });           // مؤشّرات الحقل المشتقّة
    },
  });
}

export function useRefreshFieldImagery() {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { fieldId: string }>({
    mutationFn: ({ fieldId }) => refreshFieldImagery(fieldId),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: QK.fieldTimeseries(vars.fieldId, 'ndvi', '') });
      qc.invalidateQueries({ queryKey: QK.indicatorGrid(vars.fieldId, 'ndvi', 'latest') });
    },
  });
}

// ── Indicators ────────────────────────────────────────────────
// UI deeper-fix (ملكيّة المعرّف): معرّفات الحقل platform (fld_*) لا يملكها
// vegetation-service؛ استدعاؤه بـGET /v1/analyze بهذه المعرّفات يُرجِع «field_id not
// found» (404) دائماً. نقرأ كتالوج المؤشّرات من المنصّة (نقطة قائمة فعليّاً)، وزرّ
// «تحليل الآن» يُطلق imagery refresh القانونيّ (raster عبر المنصّة).
export function useIndicators(fieldId: string) {
  return useQuery({
    queryKey: QK.indicators(fieldId),
    queryFn:  () => kongApi.get('/api/v1/indicators/catalog').then(r => r.data),
    staleTime:5 * 60_000,
    enabled:  !!fieldId,
    retry:    false,
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

// ── Change detection (per-pixel 2D, between two dates) ─────────────
export interface ChangeZone {
  class: 'improvement' | 'degradation' | 'severe_degradation';
  code: number;            // 1 | -1 | -2
  count: number;
  mean_delta: number;
  cells: [number, number][];
}

export interface ChangeDetectionResponse {
  field_id: string;
  index: string;
  date_a: string;
  date_b: string;
  available: boolean;      // false ⇒ لا COG حقيقي لأحد التاريخين (لا تغيّر مُفبرَك)
  real_data: boolean;
  // الحقول التالية موجودة فقط عند available=true
  rows?: number;
  cols?: number;
  bbox?: [number, number, number, number];
  delta_grid?: (number | null)[][]; // after - before (null = فجوة/غيمة)
  change_grid?: (number | null)[][]; // -2/-1/0/1 (null = فجوة)
  mean_delta?: number;
  improved_pct?: number;
  degraded_pct?: number;
  stable_pct?: number;
  coverage_pct?: number;
  valid_pixels?: number;
  total_pixels?: number;
  areas?: { severe_degraded_pct: number; degraded_pct: number; improved_pct: number; stable_pct: number };
  zones?: ChangeZone[];
  cloud_warning?: boolean;
  interpretation_ar?: string;
  // الحقول التالية موجودة فقط عند available=false
  missing_dates?: string[];
  note?: string;
}

// Spatial change detection between two acquisition dates (real COG grids only).
export function useFieldChange(
  fieldId: string,
  index: GridIndex,
  dateA: string,
  dateB: string,
  opts: { grid?: number; enabled?: boolean } = {},
) {
  const { grid = 32, enabled = true } = opts;
  return useQuery<ChangeDetectionResponse>({
    queryKey: QK.fieldChange(fieldId, index, dateA, dateB),
    queryFn:  () => rasterApi
      .post(`/v1/fields/${fieldId}/change`, { index, date_a: dateA, date_b: dateB, grid })
      .then(r => r.data),
    staleTime: 10 * 60_000,
    enabled:   !!fieldId && !!dateA && !!dateB && dateA !== dateB && enabled,
    retry:     false,
  });
}

// ── Time series (real per-date index means for a field) ────────────
// stddev/cloudy_pct اختياريّان: raster-service يزوّدهما لكلّ تاريخ COG؛ مصدر
// vegetation-service البديل لا يملكهما (فيبقيان undefined — لا قيم مُختلَقة).
export interface TimeseriesPoint { datetime: string; mean: number; stddev?: number; cloudy_pct?: number }

export interface FieldTimeseriesResponse {
  field_id: string;
  index: string;
  available: boolean;      // false ⇒ لا COG حقيقي في التواريخ (لا قيم مخترعة)
  real_data: boolean;
  points: TimeseriesPoint[];
  requested_dates?: string[];
  monthly_composite?: { month: string; median: number; mean: number; min: number; max: number; scene_count: number }[];
  trend?: { slope: number | null; direction: string; points: number; first?: number; last?: number };
  anomalies?: { month: string; value: number; z_score: number; type: 'drop' | 'spike' }[];
  scenes_used?: number;
  note?: string;
}

// Real index-mean time series for a field. dates="" ⇒ all available COG dates.
export function useFieldTimeseries(
  fieldId: string,
  index: GridIndex,
  dates: string = '',
  opts: { grid?: number; enabled?: boolean } = {},
) {
  const { grid = 16, enabled = true } = opts;
  return useQuery<FieldTimeseriesResponse>({
    queryKey: QK.fieldTimeseries(fieldId, index, dates),
    queryFn:  () => rasterApi
      .get(`/v1/fields/${fieldId}/timeseries`, { params: { index, dates, grid } })
      .then(r => r.data),
    staleTime: 10 * 60_000,
    enabled:   !!fieldId && enabled,
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

// FIX (ربط حيّ): الكتالوج الحقيقيّ مُخدَّم من sahool-platform عبر البوّابة
// (/api/v1/indicators/catalog) لا من indicators-service الـstub. tenant-scoped + FIELD_VIEW.
// عنصر كتالوج المؤشّرات كما تقرؤه الشاشات: id + اسم عربيّ اختياريّ + قابليّة التصيير.
export interface CatalogIndicator {
  id: string;
  name_ar?: string;
  renderable?: boolean;
}
export interface IndicatorsCatalogResponse {
  indicators?: CatalogIndicator[];
}

export function useIndicatorsCatalog(): UseQueryResult<IndicatorsCatalogResponse> {
  return useQuery({
    queryKey: QK.indicatorsCatalog,
    queryFn:  () => kongApi.get<IndicatorsCatalogResponse>('/api/v1/indicators/catalog').then(r => r.data),
    staleTime:60 * 60_000,
    retry:    false,
  });
}

// ── Weather ───────────────────────────────────────────────────
// توحيد بيانات الطقس على المنصّة (sahool-platform/api/routers/weather.py):
//   GET /api/v1/weather/current  → {temperature_c, humidity_pct, wind_speed_ms, …}
//   GET /api/v1/weather/forecast → {location, days:[{date, temp_max_c, temp_min_c,
//                                    et0_mm, daylight_hours, sunrise/sunset, …}]}
//   GET /api/v1/weather/historical (start_date/end_date) → {days:[…]}
// المنطق الحقيقيّ (Open-Meteo + ET₀ FAO-56) انتقل إلى weather-service؛ المنصّة
// تعمل الآن كـBFF آمن عبر kongApi (/api/v1/weather/*) حتى لا تستدعي الواجهة خدمة
// الطقس مباشرةً ولا تكشف توكنات الخدمة. نُطبّع الردّ إلى
// الشكل الذي تقرؤه المكوّنات بثبات: {current:{tmean,humidity_pct,wind_speed_kmh,
// et0_mm}, forecast:[{date,tmean,tmax,tmin,…}], daily:[…]}. لا تلفيق: أيّ حقل غائب
// يبقى null والمكوّنات تعرض «—». فشل المصدر (502/503) يُرفع لتعرض الواجهة حالة خطأ.

interface PlatformForecastDay {
  date?: string;
  temp_max_c?: number | null;
  temp_min_c?: number | null;
  precipitation_mm?: number | null;
  et0_mm?: number | null;
  sunshine_hours?: number | null;
  sunrise?: string | null;
  sunset?: string | null;
  daylight_hours?: number | null;
  solar_radiation_mj_m2?: number | null;
  wind_max_ms?: number | null;
  weather_code?: number | null;
  weather_ar?: string | null;
}
interface PlatformCurrent {
  temperature_c?: number | null;
  humidity_pct?: number | null;
  wind_speed_ms?: number | null;
  wind_direction_deg?: number | null;
  wind_dir_deg?: number | null;
  precipitation_mm?: number | null;
  weather_code?: number | null;
  weather_ar?: string | null;
  is_day?: number | null;
  timestamp?: string | null;
}
/** يُطبّع يوماً من المنصّة إلى شكل المكوّنات (tmean/tmax/tmin + حقول الشمس/ET₀). */
function normForecastDay(d: PlatformForecastDay) {
  const tmax = d.temp_max_c ?? null;
  const tmin = d.temp_min_c ?? null;
  const tmean = tmax != null && tmin != null ? (tmax + tmin) / 2 : null;
  return {
    date: d.date ?? null,
    tmean, tmax, tmin,
    rain: d.precipitation_mm ?? null,
    et0_mm: d.et0_mm ?? null,
    sunrise: d.sunrise ?? undefined,
    sunset: d.sunset ?? undefined,
    daylight_hours: d.daylight_hours ?? undefined,
    solar_radiation_mj_m2: d.solar_radiation_mj_m2 ?? undefined,
    weather_ar: d.weather_ar ?? undefined,
  };
}
/** يجلب الطقس الحاليّ + التوقّعات من المنصّة ويُطبّعهما لشكل المكوّنات الموحّد.
 *  current.wind_speed_kmh مُحوّلة من m/s (×3.6). et0_mm للحاضر من أوّل يوم توقّع. */
async function fetchPlatformWeather(lat: number, lon: number, days: number) {
  const [cur, fc] = await Promise.all([
    kongApi.get<PlatformCurrent>('/api/v1/weather/current', { params: { lat, lon } }).then(r => r.data),
    kongApi.get<{ days?: PlatformForecastDay[] }>('/api/v1/weather/forecast', { params: { lat, lon, days } }).then(r => r.data),
  ]);
  const rawDays = Array.isArray(fc?.days) ? fc.days : [];
  const forecast = rawDays.map(normForecastDay);
  const windKmh = cur?.wind_speed_ms != null ? Math.round(cur.wind_speed_ms * 3.6 * 10) / 10 : undefined;
  return {
    current: {
      tmean: cur?.temperature_c ?? undefined,
      humidity_pct: cur?.humidity_pct ?? undefined,
      wind_speed_kmh: windKmh,
      wind_direction_deg: cur?.wind_direction_deg ?? cur?.wind_dir_deg ?? undefined,
      et0_mm: forecast[0]?.et0_mm ?? null,
      weather_ar: cur?.weather_ar ?? undefined,
    },
    forecast,
    daily: forecast,
    location: { lat, lon },
    source: 'sahool-platform',
  };
}

export function useWeatherForecast(lat = 15.05, lon = 45.55, days = 7) {
  return useQuery({
    queryKey:        QK.weatherForecast(lat, lon),
    queryFn:         () => fetchPlatformWeather(lat, lon, days),
    staleTime:       30 * 60_000,
    refetchInterval: 60 * 60_000,
    retry:           false,
  });
}

export function useWeatherWofost(lat = 15.05, lon = 45.55, days = 14) {
  // لا نقطة wofost_format على المنصّة؛ نشتقّ مدخلات بنمط WOFOST من توقّعات المنصّة
  // الحقيقيّة عبر BFF المنصّة؛ weather-service يملك مصدر Open-Meteo وتبقى الواجهة خلف البوابة.
  return useQuery({
    queryKey: QK.weatherWofost(lat, lon, days),
    queryFn:  async () => {
      const fc = await kongApi
        .get<{ days?: PlatformForecastDay[] }>('/api/v1/weather/forecast', { params: { lat, lon, days } })
        .then(r => r.data);
      const rawDays = Array.isArray(fc?.days) ? fc.days : [];
      return {
        wofost_input: rawDays.map(d => ({
          date: d.date ?? null,
          tmax: d.temp_max_c ?? null,
          tmin: d.temp_min_c ?? null,
          radiation_mj: d.solar_radiation_mj_m2 ?? null,
          et0: d.et0_mm ?? null,
          precipitation: d.precipitation_mm ?? null,
        })),
        total_days: rawDays.length,
        source: 'sahool-platform',
      };
    },
    staleTime:60 * 60_000,
    retry:    false,
  });
}

export function useWeatherHistory(lat = 15.05, lon = 45.55, days = 30) {
  // المنصّة تتطلّب نطاق تاريخ صريح (start_date/end_date) لا عدد أيّام — نُحوّله هنا.
  return useQuery({
    queryKey: QK.weatherHistory(lat, lon, days),
    queryFn:  () => {
      const end = new Date();
      const start = new Date(end.getTime() - days * 86_400_000);
      const iso = (d: Date) => d.toISOString().slice(0, 10);
      return kongApi
        .get('/api/v1/weather/historical', {
          params: { lat, lon, start_date: iso(start), end_date: iso(end) },
        })
        .then(r => r.data);
    },
    staleTime:30 * 60_000,
    retry:    false,
  });
}

// ── Soil ──────────────────────────────────────────────────────
// صدق: خدمة soil-service غير منشورة (مُعلّقة في docker-compose؛ nginx يردّ 503 على
// /api/soil/)، والمنصّة لا تكشف نقطة مكافئة لتركيب التربة (pH/EC/OM/NPK) ولا توصية
// نيتروجين بنمط GET. لذا لا نُطلق طلباً محكوماً بالفشل: الهوكات معطّلة افتراضيّاً
// (FEATURE_FLAGS.soil مُطفأ — VITE_ENABLE_SOIL!=='true')، فلا استدعاء ميّت. عند رفع
// soil-service بتنفيذ حقيقيّ وفتح العلم، يُعاد تفعيلها كما هي (مسارات /api/soil عبر
// البوّابة). المكوّن المستهلِك (FarmAdvisoryReport) يعرض حالة «بيانات التربة غير
// متاحة» الصادقة حين تكون معطّلة (لا استدعاء صامت يفشل).
// نقرأ العلم محليّاً (لا استيراد App.tsx ⇒ تفادي اعتماد دائريّ): نفس منطق
// FEATURE_FLAGS.soil في App.tsx.
export const SOIL_ENABLED = import.meta.env.VITE_ENABLE_SOIL === 'true';

export function useSoilParams(fieldId: string) {
  return useQuery({
    queryKey: QK.soilParams(fieldId),
    queryFn:  () => soilApi.get(`/soil/wofost_params/${fieldId}`).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  SOIL_ENABLED && !!fieldId,
    retry:    false,
  });
}

export function useSoilNRecommendation(fieldId: string, targetYield = 3.5) {
  return useQuery({
    queryKey: QK.soilNRec(fieldId),
    queryFn:  () => soilApi.get('/soil/nitrogen/recommendation', {
      params: { field_id: fieldId, target_yield_t_ha: targetYield }
    }).then(r => r.data),
    staleTime:30 * 60_000,
    enabled:  SOIL_ENABLED && !!fieldId,
    retry:    false,
  });
}

// ── Phenology / Season (ربط حيّ بنقاط المنصّة؛ لا كتابة، اقتراحات فقط) ──
export interface PhenologyStage {
  stage: string; name_ar: string; day_start: number; day_end: number;
  start_date?: string; end_date?: string; kc?: number | null; key_action_ar?: string | null;
  status: 'past' | 'current' | 'upcoming';
}
export interface FieldPhenology {
  available: boolean; reason_ar?: string;
  crop?: string; crop_id?: string; sowing_date?: string; days_after_sowing?: number;
  current_stage?: { stage?: string; name_ar?: string; key_action_ar?: string | null } | null;
  current_stage_kc?: number | null;
  timeline?: PhenologyStage[];
}
export interface StageActionSuggestion { stage?: string; stage_name_ar?: string; action_ar?: string }
export interface FieldStageActions {
  available: boolean; reason_ar?: string;
  crop?: string; days_after_sowing?: number;
  current_stage?: string; current_stage_name_ar?: string;
  suggestions?: StageActionSuggestion[]; note_ar?: string;
}

/** مراحل نموّ الموسم النشط للحقل (field:view). available=false بسبب صريح عند غياب البذار/المحصول. */
export function useFieldPhenology(fieldId: string | null | undefined): UseQueryResult<FieldPhenology> {
  return useQuery<FieldPhenology>({
    queryKey: ['phenology', fieldId ?? 'none'],
    queryFn:  () => kongApi.get(`/api/v1/fields/${fieldId}/phenology`).then(r => r.data),
    staleTime:30 * 60_000,
    enabled:  !!fieldId,
    retry:    false,
  });
}

/** اقتراحات إجراء الطور الحاليّ (إرشاديّة فقط — لا تُنشَأ مهامّ). */
export function useFieldStageActions(fieldId: string | null | undefined): UseQueryResult<FieldStageActions> {
  return useQuery<FieldStageActions>({
    queryKey: ['stage-actions', fieldId ?? 'none'],
    queryFn:  () => kongApi.get(`/api/v1/fields/${fieldId}/stage-actions`).then(r => r.data),
    staleTime:30 * 60_000,
    enabled:  !!fieldId,
    retry:    false,
  });
}

// ── Water efficiency / ledger (Outcome KPI حيّ من دفتر المياه) ──
export interface FieldWaterEfficiency {
  field_id: string;
  efficiency: {
    status: string; // ok | needs_data | needs_irrigation_data
    days_counted?: number;
    etc_mm_total?: number;
    irrigation_mm_total?: number;
    effective_rain_mm_total?: number;
    supplied_mm_total?: number;
    water_use_efficiency?: number | null;
    demand_met_pct?: number | null;
    over_application_mm?: number | null;
  };
  note_ar?: string;
}

/** كفاءة مياه الحقل + إجماليّ الريّ المُطبَّق (mm) من دفتر المياه (field:view). */
export function useFieldWaterEfficiency(fieldId: string | null | undefined): UseQueryResult<FieldWaterEfficiency> {
  return useQuery<FieldWaterEfficiency>({
    queryKey: ['water-efficiency', fieldId ?? 'none'],
    queryFn:  () => kongApi.get(`/api/v1/fields/${fieldId}/water-efficiency`).then(r => r.data),
    staleTime:15 * 60_000,
    enabled:  !!fieldId,
    retry:    false,
  });
}

// ── Farm Cost Ledger (v100–v102) — تعكس التكاليف/الربحيّة الفعليّة المُخزَّنة في الواجهة ──
// الميزة خلف FEATURE_FARM_OPERATIONS_LEDGER (مُطفأة افتراضاً ⇒ 404). نلتقط 404 ونحوّله إلى
// حالة صادقة `disabled` بدل خطأ مُفزِع؛ باقي الأخطاء (503 قاعدة/403 صلاحيّة) تُرفَع كما هي.
import type {
  LedgerSummaryResponse, ProfitabilityResponse, VarianceResponse,
} from '../lib/fieldProfitability';

function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

/** ملخّص التكلفة الرقابي للحقل/الموسم من السجلّ الفعليّ. */
export function useFarmLedgerSummary(
  fieldId: string | null | undefined,
  seasonId: string | null | undefined,
  enabled = true,
): UseQueryResult<LedgerSummaryResponse> {
  return useQuery<LedgerSummaryResponse>({
    queryKey: ['farm-ledger-summary', fieldId ?? 'none', seasonId ?? 'none'],
    queryFn:  () => kongApi
      .get('/api/v1/farm-ledger/summary', { params: { field_id: fieldId || undefined, season_id: seasonId || undefined } })
      .then(r => r.data as LedgerSummaryResponse)
      .catch((e) => { if (isDisabled404(e)) return { summary: null, disabled: true }; throw e; }),
    staleTime:15 * 60_000,
    enabled:  enabled && (!!fieldId || !!seasonId),
    retry:    false,
  });
}

/** ربحيّة الموسم الفعليّة (إيراد − تكلفة) من السجلّ. */
export function useSeasonProfitability(
  seasonId: string | null | undefined,
  enabled = true,
): UseQueryResult<ProfitabilityResponse> {
  return useQuery<ProfitabilityResponse>({
    queryKey: ['season-profitability', seasonId ?? 'none'],
    queryFn:  () => kongApi
      .get(`/api/v1/farm-ledger/profitability/${seasonId}`)
      .then(r => r.data as ProfitabilityResponse)
      .catch((e) => { if (isDisabled404(e)) return { season_id: String(seasonId), profitability: null, disabled: true }; throw e; }),
    staleTime:15 * 60_000,
    enabled:  enabled && !!seasonId,
    retry:    false,
  });
}

// ── Crop & Variety Cards — بطاقات المعرفة المرجعيّة (FAO-56/Maas-Hoffman/GDD) ──
import type {
  CropCardResponse, CropCardsIndex, VarietyDiseaseWatch, VarietyExpectedHarvest, VarietySalinity,
} from '../lib/fieldCropCard';

/** فهرس بطاقات المحاصيل (معرفة مرجعيّة ثابتة ⇒ staleTime طويل). */
export function useCropCardsIndex(enabled = true): UseQueryResult<CropCardsIndex> {
  return useQuery<CropCardsIndex>({
    queryKey: ['crop-cards-index'],
    queryFn:  () => kongApi.get('/api/v1/crop-cards').then(r => r.data),
    staleTime:60 * 60_000,
    enabled,
    retry:    false,
  });
}

/** بطاقة محصول كاملة + معرّفات أصنافها. */
export function useCropCard(cropId: string | null | undefined): UseQueryResult<CropCardResponse> {
  return useQuery<CropCardResponse>({
    queryKey: ['crop-card', cropId ?? 'none'],
    queryFn:  () => kongApi.get(`/api/v1/crop-cards/crop/${cropId}`).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!cropId,
    retry:    false,
  });
}

/** مقاومات الصنف المُوثَّقة + إرشاد المسح. */
export function useVarietyDiseaseWatch(varietyId: string | null | undefined): UseQueryResult<VarietyDiseaseWatch> {
  return useQuery<VarietyDiseaseWatch>({
    queryKey: ['variety-disease-watch', varietyId ?? 'none'],
    queryFn:  () => kongApi.get(`/api/v1/crop-cards/variety/${varietyId}/disease-watch`).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!varietyId,
    retry:    false,
  });
}

/** تواريخ التزهير/الحصاد المتوقّعة من بذار حقيقيّ (لا يُستدعى بلا تاريخ). */
export function useVarietyExpectedHarvest(
  varietyId: string | null | undefined,
  sowingDate: string | null | undefined,
): UseQueryResult<VarietyExpectedHarvest> {
  return useQuery<VarietyExpectedHarvest>({
    queryKey: ['variety-expected-harvest', varietyId ?? 'none', sowingDate ?? 'none'],
    queryFn:  () => kongApi
      .get(`/api/v1/crop-cards/variety/${varietyId}/expected-harvest`, { params: { sowing_date: sowingDate } })
      .then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!varietyId && !!sowingDate,
    retry:    false,
  });
}

/** ملاءمة ملوحة مقيسة (ECe dS/m يُدخِلها المستخدم من قياس حقيقيّ) لصنف. */
export function useVarietySalinity(
  varietyId: string | null | undefined,
  ece: number | null,
): UseQueryResult<VarietySalinity> {
  return useQuery<VarietySalinity>({
    queryKey: ['variety-salinity', varietyId ?? 'none', ece ?? 'none'],
    queryFn:  () => kongApi
      .get(`/api/v1/crop-cards/variety/${varietyId}/salinity-suitability`, { params: { ece } })
      .then(r => r.data),
    staleTime:30 * 60_000,
    enabled:  !!varietyId && ece != null && Number.isFinite(ece),
    retry:    false,
  });
}

/** انحرافات المخطَّط/الفعليّ + توصيات الضبط للموسم من السجلّ. */
export function useSeasonVariance(
  seasonId: string | null | undefined,
  enabled = true,
): UseQueryResult<VarianceResponse> {
  return useQuery<VarianceResponse>({
    queryKey: ['season-variance', seasonId ?? 'none'],
    queryFn:  () => kongApi
      .get(`/api/v1/farm-ledger/variance/${seasonId}`)
      .then(r => r.data as VarianceResponse)
      .catch((e) => { if (isDisabled404(e)) return { season_id: String(seasonId), variance: [], recommendations: [], disabled: true }; throw e; }),
    staleTime:15 * 60_000,
    enabled:  enabled && !!seasonId,
    retry:    false,
  });
}

/** الحالة الاقتصاديّة العميقة للموسم (كثافات وحدة + حالة موازنة + توصيات كفاءة). */
export function useSeasonEconomicState(
  seasonId: string | null | undefined,
  areaHa: number | null,
  enabled = true,
): UseQueryResult<import('../lib/fieldProfitability').EconomicStateResponse> {
  return useQuery({
    queryKey: ['season-economic-state', seasonId ?? 'none', areaHa ?? 'none'],
    queryFn:  () => kongApi
      .get(`/api/v1/farm-ledger/economic-state/${seasonId}`, {
        params: { area_ha: areaHa != null && areaHa > 0 ? areaHa : undefined },
      })
      .then(r => r.data as import('../lib/fieldProfitability').EconomicStateResponse)
      .catch((e) => {
        if (isDisabled404(e)) return { season_id: String(seasonId), economic_state: null, disabled: true };
        throw e;
      }),
    staleTime:15 * 60_000,
    enabled:  enabled && !!seasonId,
    retry:    false,
  });
}

/** سعر التعادل (طن): تكلفة السجلّ الفعليّة + مساحة الحقل + غلّة متوقَّعة يُدخِلها المستخدم. */
export function useBreakEven(
  areaHa: number | null,
  yieldTPerHa: number | null,
  totalCost: number | null,
): UseQueryResult<import('../lib/fieldProfitability').BreakEvenResponse> {
  return useQuery({
    queryKey: ['break-even', areaHa ?? 'none', yieldTPerHa ?? 'none', totalCost ?? 'none'],
    queryFn:  () => kongApi
      .get('/api/v1/economics/break-even', {
        params: { area_ha: areaHa, yield_t_per_ha: yieldTPerHa, total_cost: totalCost },
      })
      .then(r => r.data as import('../lib/fieldProfitability').BreakEvenResponse),
    staleTime:15 * 60_000,
    enabled:  areaHa != null && areaHa > 0 && yieldTPerHa != null && yieldTPerHa > 0 && totalCost != null && totalCost > 0,
    retry:    false,
  });
}

// ── Harvest Traceability (v65) — من المزرعة إلى السوق ──
import type {
  HarvestLotSummary, InputLedger, LotTraceability,
} from '../lib/fieldHarvestTraceability';

/** دفعات حصاد الحقل (الأحدث أولاً، RLS). */
export function useHarvestLots(fieldId: string | null | undefined, enabled = true): UseQueryResult<HarvestLotSummary[]> {
  return useQuery<HarvestLotSummary[]>({
    queryKey: ['harvest-lots', fieldId ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/harvest-lots', { params: { field_id: fieldId } }).then(r => r.data),
    staleTime:5 * 60_000,
    enabled:  enabled && !!fieldId,
    retry:    false,
  });
}

/** الأثر الكامل لدفعة: سلسلة الحيازة + المنشأ + تقييم الاكتمال (معيار الخادم). */
export function useLotTraceability(lotId: string | null | undefined): UseQueryResult<LotTraceability> {
  return useQuery<LotTraceability>({
    queryKey: ['lot-traceability', lotId ?? 'none'],
    queryFn:  () => kongApi.get(`/api/v1/harvest-lots/${lotId}/traceability`).then(r => r.data),
    staleTime:5 * 60_000,
    enabled:  !!lotId,
    retry:    false,
  });
}

/** دفتر مدخلات الحقل (بذرة→حصاد) — الكلفة الغائبة تُعلَن بتغطية لا تُؤلَّف. */
export function useFieldInputTraceability(
  fieldId: string | null | undefined,
  seasonId: string | null | undefined,
  enabled = true,
): UseQueryResult<InputLedger> {
  return useQuery<InputLedger>({
    queryKey: ['input-traceability', fieldId ?? 'none', seasonId ?? 'none'],
    queryFn:  () => kongApi
      .get(`/api/v1/fields/${fieldId}/input-traceability`, { params: { season_id: seasonId || undefined } })
      .then(r => r.data),
    staleTime:10 * 60_000,
    enabled:  enabled && !!fieldId,
    retry:    false,
  });
}

// ── Boundary Review (#15) — تهديف ثقة الحدّ + شبكة الجوار ──
import type { BoundaryGraphResponse, BoundaryScoreResult } from '../lib/fieldBoundaryReview';

/** شبكة جوار الحقل (field_boundary_graph) — قائمة فارغة صالحة لا 404. */
export function useBoundaryGraph(fieldId: string | null | undefined, enabled = true): UseQueryResult<BoundaryGraphResponse> {
  return useQuery<BoundaryGraphResponse>({
    queryKey: ['boundary-graph', fieldId ?? 'none'],
    queryFn:  () => kongApi.get(`/api/v1/fields/${fieldId}/boundary-graph`).then(r => r.data),
    staleTime:15 * 60_000,
    enabled:  enabled && !!fieldId,
    retry:    false,
  });
}

/** تهديف ثقة حدّ الحقل (يشتقّ الخادم الخصائص من geom عبر PostGIS ويخزّن النتيجة). */
export function useScoreBoundary(): ReturnType<typeof useMutation<BoundaryScoreResult, Error, { fieldId: string }>> {
  return useMutation<BoundaryScoreResult, Error, { fieldId: string }>({
    mutationFn: ({ fieldId }) => kongApi
      .post(`/api/v1/fields/${fieldId}/boundary/score`, {})
      .then(r => r.data),
  });
}

import type { BoundaryCleanResult, BoundaryReviewResult, BoundaryReviewStatus } from '../lib/fieldBoundaryReview';

/** المراجعة البشريّة (HIL) لحدّ الحقل: approved|rejected|needs_edit (FIELD_EDIT خادميّاً). */
export function useReviewBoundary(): ReturnType<typeof useMutation<BoundaryReviewResult, Error, { fieldId: string; status: BoundaryReviewStatus }>> {
  return useMutation<BoundaryReviewResult, Error, { fieldId: string; status: BoundaryReviewStatus }>({
    mutationFn: ({ fieldId, status }) => kongApi
      .patch(`/api/v1/fields/${fieldId}/boundary/review`, { review_status: status })
      .then(r => r.data),
  });
}

/** التنظيف الطوبولوجيّ الحتميّ (MakeValid + إزالة تكرار + تبسيط حافظ) — شبه عديم الأثر عند الإعادة. */
export function useCleanBoundary(): ReturnType<typeof useMutation<BoundaryCleanResult, Error, { fieldId: string; toleranceM?: number }>> {
  return useMutation<BoundaryCleanResult, Error, { fieldId: string; toleranceM?: number }>({
    mutationFn: ({ fieldId, toleranceM }) => kongApi
      .post(`/api/v1/fields/${fieldId}/boundary/clean`, toleranceM != null ? { tolerance_m: toleranceM } : {})
      .then(r => r.data),
  });
}

// ── Admin Runtime Console — مسارات التشغيل الإداريّة (owner/manager) ──
import type {
  AutomationRunsResponse, DeadLetterResponse, QueueStatusResponse, ReadinessReport, SecurityDenialsResponse,
} from '../lib/adminRuntime';

/** جاهزيّة الإنتاج من لقطة بيئة المنصّة (ready + blockers + warnings + checks). */
export function useAdminReadiness(enabled = true): UseQueryResult<ReadinessReport> {
  return useQuery<ReadinessReport>({
    queryKey: ['admin-readiness'],
    queryFn:  () => kongApi.get('/api/v1/admin/readiness').then(r => r.data),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

/** الأحداث الميّتة (DLQ NATS) — الخادم يوصي: نبّه لو total>0. */
export function useAdminEventsDeadLetter(enabled = true): UseQueryResult<DeadLetterResponse> {
  return useQuery<DeadLetterResponse>({
    queryKey: ['admin-events-dlq'],
    queryFn:  () => kongApi.get('/api/v1/admin/events/dead-letter').then(r => r.data),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

/** صفوف outbox المستنفدة (dead) — قابلة لإعادة الجدولة بعد إصلاح السبب. */
export function useAdminOutboxDeadLetter(enabled = true): UseQueryResult<DeadLetterResponse> {
  return useQuery<DeadLetterResponse>({
    queryKey: ['admin-outbox-dlq'],
    queryFn:  () => kongApi.get('/api/v1/admin/outbox/dead-letter').then(r => r.data),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

/** سجلّ رفض الأمان (denials) الأخير + ملخّصه. */
export function useSecurityDenials(enabled = true): UseQueryResult<SecurityDenialsResponse> {
  return useQuery<SecurityDenialsResponse>({
    queryKey: ['admin-security-denials'],
    queryFn:  () => kongApi.get('/api/v1/admin/security/denials').then(r => r.data),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

/** حالة قائمة offline للمستأجِر الحاليّ. */
export function useQueueStatus(enabled = true): UseQueryResult<QueueStatusResponse> {
  return useQuery<QueueStatusResponse>({
    queryKey: ['queue-status'],
    queryFn:  () => kongApi.get('/api/v1/queue/status').then(r => r.data),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

/** سجلّ تشغيلات الأتمتة + الملخّص. */
export function useAutomationRuns(enabled = true, limit = 10): UseQueryResult<AutomationRunsResponse> {
  return useQuery<AutomationRunsResponse>({
    queryKey: ['automation-runs', limit],
    queryFn:  () => kongApi.get('/api/v1/automation/runs', { params: { limit } }).then(r => r.data),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

/** حالة مجدوِل الأتمتة (بنية مرنة من الخادم). */
export function useSchedulerStatus(enabled = true): UseQueryResult<Record<string, unknown>> {
  return useQuery<Record<string, unknown>>({
    queryKey: ['automation-scheduler-status'],
    queryFn:  () => kongApi.get('/api/v1/automation/scheduler-status').then(r => r.data),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

// ── Yemeni Agricultural Calendar — طبقة عرض تراثيّة-رصديّة (display_only) ──
import type { CalendarTodayContext, ProverbsForDateResponse } from '../lib/yemeniCalendar';

/** سياق التقويم الزراعيّ اليمنيّ لليوم (منزلة + شهر حميريّ + منطقة + نافذة محصول). */
export function useCalendarToday(
  crop: string | null | undefined,
  governorate: string | null | undefined,
  enabled = true,
): UseQueryResult<CalendarTodayContext> {
  return useQuery<CalendarTodayContext>({
    queryKey: ['calendar-today', crop ?? 'none', governorate ?? 'none'],
    queryFn:  () => kongApi
      .get('/api/v1/calendars/today', { params: { crop: crop || undefined, governorate: governorate || undefined } })
      .then(r => r.data),
    staleTime:6 * 60 * 60_000, // معرفة يوميّة شبه ثابتة
    enabled,
    retry:    false,
  });
}

/** أمثال التاريخ (المنزلة النشطة ⇒ أمثالها) — سياق ثقافيّ، عرض فقط. */
export function useProverbsForDate(
  dateIso: string | null | undefined,
  governorate: string | null | undefined,
  enabled = true,
): UseQueryResult<ProverbsForDateResponse> {
  return useQuery<ProverbsForDateResponse>({
    queryKey: ['proverbs-for-date', dateIso ?? 'none', governorate ?? 'none'],
    queryFn:  () => kongApi
      .get('/api/v1/agricultural-proverbs/for-date', { params: { date_iso: dateIso, governorate: governorate || undefined } })
      .then(r => r.data),
    staleTime:6 * 60 * 60_000,
    enabled:  enabled && !!dateIso,
    retry:    false,
  });
}

// ── Planting Advisor — «ماذا أزرع بعد محصولي؟» (دورة زراعيّة + نافذة الشهر) ──
import type { RotationSuggestResponse } from '../lib/plantingAdvisor';
import type { PlantingFit as PlantingFitT } from '../lib/yemeniCalendar';

/** أفضل المحاصيل التالية بعد محصول (مرتّبة بأسباب يمنيّة من جدول الدورة). */
export function useRotationSuggest(previousCrop: string | null | undefined, enabled = true): UseQueryResult<RotationSuggestResponse> {
  return useQuery<RotationSuggestResponse>({
    queryKey: ['rotation-suggest', previousCrop ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/rotation/suggest', { params: { previous: previousCrop } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  enabled && !!previousCrop,
    retry:    false,
  });
}

/** ملاءمة شهر لزراعة محصول (حكم الخادم optimal/acceptable/off_window). */
export function usePlantingCheck(crop: string | null | undefined, month: number | null): UseQueryResult<PlantingFitT> {
  return useQuery<PlantingFitT>({
    queryKey: ['planting-check', crop ?? 'none', month ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/planting/check', { params: { crop, month } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!crop && month != null,
    retry:    false,
  });
}

// ── Decision Runtime — موزِّع القرار المحروس (خلف SAHOOL_DECISION_DISPATCH) ──
import type {
  DecisionLedgerResponse, DecisionPoliciesResponse, DispatchAudit,
  DispatchDecisionsResponse, DispatchEvaluateInput, DispatchQueueResponse,
} from '../lib/decisionRuntime';

/** طابور أوامر المُشغِّل المنتظِرة (queued، الأقدم أوّلاً). 404 ⇒ الميزة مُطفأة. */
export function useDispatchQueue(enabled = true): UseQueryResult<DispatchQueueResponse> {
  return useQuery<DispatchQueueResponse>({
    queryKey: ['dispatch-queue'],
    queryFn:  () => kongApi.get('/api/v1/decision/dispatch/queue').then(r => r.data as DispatchQueueResponse)
      .catch((e) => { if (isDisabled404(e)) return { queued: [], count: 0, disabled: true }; throw e; }),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

/** آخر قرارات التوزيع بحالاتها المحروسة (blocked/pending_approval/ready). */
export function useDispatchDecisions(enabled = true): UseQueryResult<DispatchDecisionsResponse> {
  return useQuery<DispatchDecisionsResponse>({
    queryKey: ['dispatch-decisions'],
    queryFn:  () => kongApi.get('/api/v1/decision/dispatch/decisions').then(r => r.data as DispatchDecisionsResponse)
      .catch((e) => { if (isDisabled404(e)) return { decisions: [], count: 0, disabled: true }; throw e; }),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

/** سجلّ تنفيذ القرارات (نتائج مُسجَّلة). */
export function useDecisionLedger(enabled = true): UseQueryResult<DecisionLedgerResponse> {
  return useQuery<DecisionLedgerResponse>({
    queryKey: ['decision-ledger'],
    queryFn:  () => kongApi.get('/api/v1/decision/ledger').then(r => r.data as DecisionLedgerResponse)
      .catch((e) => { if (isDisabled404(e)) return { ledger: [], count: 0, disabled: true }; throw e; }),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

/** سياسات القرار (الأعلى أولويّة أوّلاً). */
export function useDecisionPolicies(enabled = true): UseQueryResult<DecisionPoliciesResponse> {
  return useQuery<DecisionPoliciesResponse>({
    queryKey: ['decision-policies'],
    queryFn:  () => kongApi.get('/api/v1/decision/policies').then(r => r.data as DecisionPoliciesResponse)
      .catch((e) => { if (isDisabled404(e)) return { policies: [], count: 0, disabled: true }; throw e; }),
    staleTime:5 * 60_000,
    enabled,
    retry:    false,
  });
}

/** معاينة dry-run لقرار توزيع — لا تنفيذ (dry_run=true من الخادم). */
export function useEvaluateDispatch(): ReturnType<typeof useMutation<DispatchAudit, Error, DispatchEvaluateInput>> {
  return useMutation<DispatchAudit, Error, DispatchEvaluateInput>({
    mutationFn: (input) => kongApi.post('/api/v1/decision/dispatch/evaluate', input).then(r => r.data),
  });
}

import type { OutcomeMeasureInput, OutcomeMeasureResponse } from '../lib/decisionRuntime';

/** قياس نتيجة قرار (مُخطَّط مقابل مرصود) — الخادم يقيّم المتوفّر طرفاه فقط (needs_data للناقص). */
export function useMeasureOutcome(): ReturnType<typeof useMutation<OutcomeMeasureResponse, Error, OutcomeMeasureInput>> {
  return useMutation<OutcomeMeasureResponse, Error, OutcomeMeasureInput>({
    mutationFn: (input) => kongApi.post('/api/v1/outcome/measure', input).then(r => r.data),
  });
}

// ── Ledger Entry — إدخال السجلّ الماليّ من الواجهة (ACTIVITY_EXECUTE خادميّاً) ──
import type { BudgetLinesPayload, OperationPayload, RevenuePayload } from '../lib/ledgerEntry';

/** مفاتيح الكاش الماليّة التي يجب إبطالها بعد أيّ إدخال — تُحدَّث بطاقة الربحيّة حيّاً. */
export const LEDGER_QUERY_PREFIXES = [
  'farm-ledger-summary', 'season-profitability', 'season-variance', 'season-economic-state',
] as const;

/** تسجيل عمليّة بتكلفة في سجلّ العمليّات الفعليّ. */
export function useRecordLedgerOperation(): ReturnType<typeof useMutation<unknown, Error, OperationPayload>> {
  return useMutation<unknown, Error, OperationPayload>({
    mutationFn: (payload) => kongApi.post('/api/v1/farm-ledger/operations', payload).then(r => r.data),
  });
}

/** إدراج/تحديث بنود موازنة الموسم المخطَّطة. */
export function useUpsertBudgetLines(): ReturnType<typeof useMutation<unknown, Error, BudgetLinesPayload>> {
  return useMutation<unknown, Error, BudgetLinesPayload>({
    mutationFn: (payload) => kongApi.post('/api/v1/farm-ledger/budgets', payload).then(r => r.data),
  });
}

/** تسجيل إيراد للموسم. */
export function useRecordRevenue(): ReturnType<typeof useMutation<unknown, Error, RevenuePayload>> {
  return useMutation<unknown, Error, RevenuePayload>({
    mutationFn: (payload) => kongApi.post('/api/v1/farm-ledger/revenues', payload).then(r => r.data),
  });
}

// ── Agro-Knowledge — طبقة معرفة زراعيّة يتيمة (إكثار/ما بعد الحصاد/البنّ اليمنيّ) ──
// معرفة مرجعيّة نقيّة من مصادر موثّقة ⇒ staleTime طويل (وكيل C).
import type {
  CropPropagation, PostharvestBestPractices,
  CoffeeGuide, CoffeeVarieties, CoffeePests,
} from '../lib/fieldAgroKnowledge';

/** طريقة الإكثار المناسبة لمحصول الحقل (لا يُستدعى بلا محصول). */
export function useCropPropagation(cropLabel: string | null | undefined): UseQueryResult<CropPropagation> {
  return useQuery<CropPropagation>({
    queryKey: ['propagation-crop', cropLabel ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/propagation/crop', { params: { crop: cropLabel } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!cropLabel,
    retry:    false,
  });
}

/** أفضل ممارسات ما بعد الحصاد (crop اختياريّ يضيف عتبة الرطوبة). */
export function usePostharvestBestPractices(
  cropLabel: string | null | undefined,
  enabled = true,
): UseQueryResult<PostharvestBestPractices> {
  return useQuery<PostharvestBestPractices>({
    queryKey: ['postharvest-best-practices', cropLabel ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/postharvest/best-practices', { params: { crop: cropLabel || undefined } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled,
    retry:    false,
  });
}

/** دليل زراعة البنّ اليمنيّ (يُفعَّل فقط حين يكون المحصول بُنّاً). */
export function useCoffeeGuide(enabled = true): UseQueryResult<CoffeeGuide> {
  return useQuery<CoffeeGuide>({
    queryKey: ['coffee-guide'],
    queryFn:  () => kongApi.get('/api/v1/coffee/guide').then(r => r.data),
    staleTime:60 * 60_000,
    enabled,
    retry:    false,
  });
}

/** أصناف البنّ اليمنيّة (يُفعَّل للبنّ فقط). */
export function useCoffeeVarieties(enabled = true): UseQueryResult<CoffeeVarieties> {
  return useQuery<CoffeeVarieties>({
    queryKey: ['coffee-varieties'],
    queryFn:  () => kongApi.get('/api/v1/coffee/varieties').then(r => r.data),
    staleTime:60 * 60_000,
    enabled,
    retry:    false,
  });
}

/** آفات البنّ الرئيسيّة المرتبطة بـIPM (يُفعَّل للبنّ فقط). */
export function useCoffeePests(enabled = true): UseQueryResult<CoffeePests> {
  return useQuery<CoffeePests>({
    queryKey: ['coffee-pests'],
    queryFn:  () => kongApi.get('/api/v1/coffee/pests').then(r => r.data),
    staleTime:60 * 60_000,
    enabled,
    retry:    false,
  });
}

// ── حصاد المياه + طريقة الريّ — /api/v1/water-harvesting/* و/api/v1/irrigation-method (وكيل B) ──
import type {
  HarvestPotentialResponse, HarvestingMethodsResponse, IrrigationMethodsResponse, MethodGuideResponse,
} from '../lib/waterHarvesting';

/** إمكانات حصاد مياه الأمطار — من قياسَي مساحة/مطر يُدخِلهما المستخدم (لا تخمين). */
export function useWaterHarvestPotential(areaM2: number | null, rainMm: number | null, surface: string, enabled = true): UseQueryResult<HarvestPotentialResponse> {
  return useQuery<HarvestPotentialResponse>({
    queryKey: ['water-harvest-potential', areaM2 ?? 'none', rainMm ?? 'none', surface],
    queryFn:  () => kongApi.get('/api/v1/water-harvesting/potential', { params: { catchment_area_m2: areaM2, annual_rain_mm: rainMm, surface } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  enabled && areaM2 != null && rainMm != null,
    retry:    false,
  });
}

/** طرق حصاد المياه التراثيّة اليمنيّة (مدرّجات/عقوم/كرفان/مصاطب كنتوريّة). */
export function useWaterHarvestingMethods(enabled = true): UseQueryResult<HarvestingMethodsResponse> {
  return useQuery<HarvestingMethodsResponse>({
    queryKey: ['water-harvesting-methods'],
    queryFn:  () => kongApi.get('/api/v1/water-harvesting/methods').then(r => r.data),
    staleTime:60 * 60_000,
    enabled,
    retry:    false,
  });
}

/** دليل طريقة حصاد محدّدة (فوائد + الأنسب + تحذير) — حكم الخادم يمرّ كما هو. */
export function useWaterHarvestMethodGuide(method: string | null): UseQueryResult<MethodGuideResponse> {
  return useQuery<MethodGuideResponse>({
    queryKey: ['water-harvest-method-guide', method ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/water-harvesting/method-guide', { params: { method } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!method,
    retry:    false,
  });
}

/** ملامح طرق الريّ الخمس (كفاءات FAO موسومة calibrated=false — تحذيراتها تُعرَض). */
export function useIrrigationMethodProfiles(enabled = true): UseQueryResult<IrrigationMethodsResponse> {
  return useQuery<IrrigationMethodsResponse>({
    queryKey: ['irrigation-method-profiles'],
    queryFn:  () => kongApi.get('/api/v1/irrigation-method').then(r => r.data),
    staleTime:60 * 60_000,
    enabled,
    retry:    false,
  });
}

// ── مخاطر المناخ والماء — حساسيّة المراحل المائيّة + المخاطر الموسميّة + المناطق المشابهة (وكيل A) ──
import type {
  ChillHoursResponse, ClimateAnalogsListResponse, SeasonalRiskCalendarResponse, WaterCalendarResponse,
} from '../lib/fieldClimateRisk';

/** التقويم المائيّ لمحصول (FAO-56 + سياق يمنيّ — معرفة مرجعيّة ثابتة ⇒ staleTime طويل).
 *  يقبل المفتاح الإنجليزيّ أو الاسم العربيّ (الخادم يحلّ المرادفات). */
export function useWaterSensitivityCalendar(
  crop: string | null | undefined,
  enabled = true,
): UseQueryResult<WaterCalendarResponse> {
  return useQuery<WaterCalendarResponse>({
    queryKey: ['water-sensitivity-calendar', crop ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/water-sensitivity/calendar', { params: { crop } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  enabled && !!crop,
    retry:    false,
  });
}

/** نوافذ المخاطر المناخيّة الموسميّة لإقليم (اختيار المستخدم — لا يُستدعى بلا إقليم). */
export function useSeasonalRiskCalendar(
  zone: string | null | undefined,
  enabled = true,
): UseQueryResult<SeasonalRiskCalendarResponse> {
  return useQuery<SeasonalRiskCalendarResponse>({
    queryKey: ['seasonal-risk-calendar', zone ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/seasonal-risk/calendar', { params: { zone } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  enabled && !!zone,
    retry:    false,
  });
}

/** تقدير ساعات البرودة لإقليم + حكم الخادم على الأشجار المتساقطة (can_satisfy). */
export function useChillHoursEstimate(
  zone: string | null | undefined,
  enabled = true,
): UseQueryResult<ChillHoursResponse> {
  return useQuery<ChillHoursResponse>({
    queryKey: ['seasonal-risk-chill-hours', zone ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/seasonal-risk/chill-hours', { params: { zone } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  enabled && !!zone,
    retry:    false,
  });
}

/** المناطق العالميّة المشابهة مناخيّاً (مرجعيّة ثابتة — تُجلَب عند فتح القسم فقط). */
export function useClimateAnalogRegions(enabled = true): UseQueryResult<ClimateAnalogsListResponse> {
  return useQuery<ClimateAnalogsListResponse>({
    queryKey: ['climate-analogs-list'],
    queryFn:  () => kongApi.get('/api/v1/climate-analogs/list').then(r => r.data),
    staleTime:60 * 60_000,
    enabled,
    retry:    false,
  });
}

/** إعادة بناء شبكة جوار حدود حقول المستأجِر كاملةً (PostGIS حتميّ) — إداريّ. */
export function useRebuildBoundaryGraph(): ReturnType<typeof useMutation<{ rebuilt: boolean; relations_written: number }, Error, void>> {
  return useMutation<{ rebuilt: boolean; relations_written: number }, Error, void>({
    mutationFn: () => kongApi.post('/api/v1/fields/boundary-graph/rebuild', {}).then(r => r.data),
  });
}

// ── حاسبات القياس الحقليّة (وكيل E) — بذور/رطوبة حبوب/ارتفاع البنّ ──
import type {
  GerminationParams, GerminationRateResponse, StorageCheckParams, SeedStorageCheckResponse,
  SowingDepthParams, SowingDepthResponse, SeedCriteriaResponse,
  MoistureCheckParams, MoistureCheckResponse, CoffeeSiteParams, CoffeeSiteResponse,
} from '../lib/agroCalculators';

/** معدّل الإنبات من عدّ عيّنة حقيقيّ — لا يُستدعى إلّا بمُدخلات صحيحة (builder). */
export function useSeedGerminationRate(params: GerminationParams | null): UseQueryResult<GerminationRateResponse> {
  return useQuery<GerminationRateResponse>({
    queryKey: ['seed-germination-rate', params?.sprouted ?? 'none', params?.total ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/seed/germination-rate', { params }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!params,
    retry:    false,
  });
}

/** قاعدة المئة لتخزين البذور (الخادم بالفهرنهايت — الـbuilder يحوّل من °م). */
export function useSeedStorageCheck(params: StorageCheckParams | null): UseQueryResult<SeedStorageCheckResponse> {
  return useQuery<SeedStorageCheckResponse>({
    queryKey: ['seed-storage-check', params?.temp_f ?? 'none', params?.humidity_pct ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/seed/storage-check', { params }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!params,
    retry:    false,
  });
}

/** عمق البذر ~5× حجم البذرة (2× للزراعة الدقيقة). */
export function useSeedSowingDepth(params: SowingDepthParams | null): UseQueryResult<SowingDepthResponse> {
  return useQuery<SowingDepthResponse>({
    queryKey: ['seed-sowing-depth', params?.seed_size_mm ?? 'none', params?.precision ?? false],
    queryFn:  () => kongApi.get('/api/v1/seed/sowing-depth', { params }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!params,
    retry:    false,
  });
}

/** معايير اختيار البذور المحسّنة — مرجع ثابت يُجلَب عند فتح القسم فقط. */
export function useSeedCriteria(enabled: boolean): UseQueryResult<SeedCriteriaResponse> {
  return useQuery<SeedCriteriaResponse>({
    queryKey: ['seed-criteria'],
    queryFn:  () => kongApi.get('/api/v1/seed/criteria').then(r => r.data),
    staleTime:24 * 60 * 60_000,
    enabled,
    retry:    false,
  });
}

/** أمان رطوبة الحبوب للتخزين — supported=false يعني محصولاً بلا عتبة معروفة. */
export function usePostharvestMoistureCheck(params: MoistureCheckParams | null): UseQueryResult<MoistureCheckResponse> {
  return useQuery<MoistureCheckResponse>({
    queryKey: ['postharvest-moisture-check', params?.crop ?? 'none', params?.moisture_pct ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/postharvest/moisture-check', { params }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!params,
    retry:    false,
  });
}

/** ملاءمة موقع للبنّ من ارتفاع حقيقيّ (GPS/خريطة). */
export function useCoffeeSiteSuitability(params: CoffeeSiteParams | null): UseQueryResult<CoffeeSiteResponse> {
  return useQuery<CoffeeSiteResponse>({
    queryKey: ['coffee-site-suitability', params?.altitude_m ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/coffee/site-suitability', { params }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!params,
    retry:    false,
  });
}

// ── كتالوج GIS السحابيّ (وكيل D) — STAC · OGC · خطّة الكاش (قراءة فقط) ──
import type {
  StacLandingPage, StacCollectionsResponse, StacSearchResponse,
  OgcConformanceResponse, OgcCollectionsResponse, TileCachePlan,
} from '../lib/gisCatalog';

/** بوّابة STAC (عقد ثابت + conformsTo). */
export function useGisStacLanding(enabled = true): UseQueryResult<StacLandingPage> {
  return useQuery<StacLandingPage>({
    queryKey: ['gis-stac-landing'],
    queryFn:  () => kongApi.get('/api/v1/gis/cloud-native/stac').then(r => r.data),
    staleTime: 30 * 60_000,
    enabled,
    retry:    false,
  });
}

/** مجموعات STAC من سجلّ الرستر (DB-backed — 503 صادقة عند غياب القاعدة). */
export function useGisStacCollections(enabled = true): UseQueryResult<StacCollectionsResponse> {
  return useQuery<StacCollectionsResponse>({
    queryKey: ['gis-stac-collections'],
    queryFn:  () => kongApi.get('/api/v1/gis/cloud-native/stac/collections').then(r => r.data),
    staleTime: 5 * 60_000,
    enabled,
    retry:    false,
  });
}

/** بحث عناصر STAC (أحدث المشاهد أوّلاً بترتيب الخادم). */
export function useGisStacItems(enabled = true, limit = 50): UseQueryResult<StacSearchResponse> {
  return useQuery<StacSearchResponse>({
    queryKey: ['gis-stac-items', limit],
    queryFn:  () => kongApi.get('/api/v1/gis/cloud-native/stac/search', { params: { limit } }).then(r => r.data),
    staleTime: 5 * 60_000,
    enabled,
    retry:    false,
  });
}

/** مطابقة OGC API (عقد ثابت). */
export function useGisOgcConformance(enabled = true): UseQueryResult<OgcConformanceResponse> {
  return useQuery<OgcConformanceResponse>({
    queryKey: ['gis-ogc-conformance'],
    queryFn:  () => kongApi.get('/api/v1/gis/cloud-native/ogc/conformance').then(r => r.data),
    staleTime: 30 * 60_000,
    enabled,
    retry:    false,
  });
}

/** مجموعات OGC (fields/rasters). */
export function useGisOgcCollections(enabled = true): UseQueryResult<OgcCollectionsResponse> {
  return useQuery<OgcCollectionsResponse>({
    queryKey: ['gis-ogc-collections'],
    queryFn:  () => kongApi.get('/api/v1/gis/cloud-native/ogc/collections').then(r => r.data),
    staleTime: 30 * 60_000,
    enabled,
    retry:    false,
  });
}

/** خطّة كاش البلاطات (DB-backed من سجلّ الرستر). */
export function useGisTileCachePlan(enabled = true): UseQueryResult<TileCachePlan> {
  return useQuery<TileCachePlan>({
    queryKey: ['gis-tile-cache-plan'],
    queryFn:  () => kongApi.get('/api/v1/gis/cloud-native/tile-cache-plan').then(r => r.data),
    staleTime: 5 * 60_000,
    enabled,
    retry:    false,
  });
}

// ── Decision Insight (وكيل F) — سجلّ القرارات المُدامة + الشرح + التعلُّم + الأثر ──
import type {
  DecisionExplainResponse, DecisionImpactResponse, DecisionLearningResponse, DecisionRecordsResponse,
} from '../lib/decisionInsight';

/** سجلّ قرارات المستأجِر المُدامة (الأحدث أوّلاً، decision_record v78). */
export function useDecisionRecordsInsight(limit = 20, enabled = true): UseQueryResult<DecisionRecordsResponse> {
  return useQuery<DecisionRecordsResponse>({
    queryKey: ['decision-records', limit],
    queryFn:  () => kongApi.get('/api/v1/decision/records', { params: { limit } })
      .then(r => r.data as DecisionRecordsResponse)
      .catch((e) => { if (isDisabled404(e)) return { decisions: [], count: 0, disabled: true }; throw e; }),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

/** سلسلة شرح قرار مُدام (ثقة→إشارات→سياسة→قيود→إجراء) + نتائجه (replay).
 *  404 ⇒ الميزة مُطفأة (FEATURE_DECISION_STUDIO) أو القرار غير مُدام — حالة صادقة. */
export function useDecisionExplainInsight(decisionId: string | null | undefined, enabled = true): UseQueryResult<DecisionExplainResponse> {
  return useQuery<DecisionExplainResponse>({
    queryKey: ['decision-explain', decisionId ?? 'none'],
    queryFn:  () => kongApi.get(`/api/v1/decision/${decisionId}/explain`)
      .then(r => r.data as DecisionExplainResponse)
      .catch((e) => {
        if (isDisabled404(e)) return { decision_id: String(decisionId), explanation: null, outcomes: [], outcome_count: 0, calibrated: false, disabled: true };
        throw e;
      }),
    staleTime:60_000,
    enabled:  enabled && !!decisionId,
    retry:    false,
  });
}

/** اقتراحات معايرة مُسنَدة بالأثر — استشاريّة (advisory_only، لا تُطبَّق آليّاً). */
export function useDecisionLearning(minSample = 5, enabled = true): UseQueryResult<DecisionLearningResponse> {
  return useQuery<DecisionLearningResponse>({
    queryKey: ['decision-learning', minSample],
    queryFn:  () => kongApi.get('/api/v1/decision/learning', { params: { min_sample: minSample } })
      .then(r => r.data as DecisionLearningResponse)
      .catch((e) => { if (isDisabled404(e)) return { suggestions: [], count: 0, advisory_only: true, based_on: null, disabled: true }; throw e; }),
    staleTime:5 * 60_000,
    enabled,
    retry:    false,
  });
}

/** الأثر المُحقَّق من سجلّ التنفيذ (نُفِّذ/فشل، نسبة نجاح، ماء موفَّر) — قياس لا تنبّؤ. */
export function useDecisionImpact(fieldId?: string | null, enabled = true): UseQueryResult<DecisionImpactResponse> {
  return useQuery<DecisionImpactResponse>({
    queryKey: ['decision-impact', fieldId ?? 'all'],
    queryFn:  () => kongApi.get('/api/v1/decision/impact', { params: { field_id: fieldId || undefined } })
      .then(r => r.data as DecisionImpactResponse)
      .catch((e) => {
        if (isDisabled404(e)) return {
          total_decisions: 0, executed: 0, failed: 0, success_rate: 0,
          water_requested_mm: 0, water_applied_mm: 0, water_saved_mm: 0, water_records: 0,
          by_action: {}, disabled: true,
        };
        throw e;
      }),
    staleTime:60_000,
    enabled,
    retry:    false,
  });
}

// ── تقويم عمليّات المحصول + تتبّع GDD (متابعة عقد التغطية — أرشيف المستخدم) ──
export interface CropOperationCalendarStage {
  stage: string;
  stage_ar?: string;
  operations?: Array<{ type?: string; label?: string; label_ar?: string; timing_ar?: string; notes_ar?: string }>;
}

export interface CropOperationsCalendarResponse {
  crop?: string;
  crop_id?: string;
  stages?: CropOperationCalendarStage[];
  calendar?: CropOperationCalendarStage[];
  notes_ar?: string;
  disabled?: boolean;
}

/** تقويم العمليّات الكامل لمحصول — يقرأ backend crop operations calendar بدل تركه يتيماً. */
export function useCropOperationsCalendar(crop: string | null | undefined, enabled = true): UseQueryResult<CropOperationsCalendarResponse> {
  return useQuery<CropOperationsCalendarResponse>({
    queryKey: ['crop-operations-calendar', crop ?? 'none'],
    queryFn:  () => kongApi.get(`/api/v1/crops/${encodeURIComponent(crop ?? '')}/operations-calendar`).then(r => r.data as CropOperationsCalendarResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true, stages: [], calendar: [] }; throw e; }),
    staleTime:6 * 60 * 60_000,
    enabled:  enabled && !!crop,
    retry:    false,
  });
}

export interface GddTrackInput {
  crop: string;
  temps: Array<{ t_min_c: number; t_max_c: number }>;
}

export interface GddTrackResult {
  crop: string;
  t_base: number;
  days_counted: number;
  cumulative_gdd: number;
  current_stage: string;
  next_stage: string | null;
  gdd_to_next_stage: number | null;
  stage_progress: Array<{ stage: string; gdd_threshold: number; reached: boolean }>;
  notes_ar: string;
}

/** تتبّع GDD يتطلّب سلسلة حرارة صريحة؛ لا نخمّنها في الواجهة. */
export function useGddTrack(): UseMutationResult<GddTrackResult, unknown, GddTrackInput> {
  return useMutation<GddTrackResult, unknown, GddTrackInput>({
    mutationFn: (input) => kongApi.post('/api/v1/gdd/track', input).then(r => r.data as GddTrackResult),
  });
}

// ── Field Diagnostics Workbench (وكيل G) — التشخيص الأوّليّ + IPM + الملوحة ──
import type {
  CropPestsResponse, DiagnosePayload, DiagnoseResponse, IpmPestsResponse,
  IpmPlanResponse, SalinityAssessResponse, SalinityPayload, SymptomCatalogResponse,
} from '../lib/fieldDiagnostics';

/** كتالوج الأعراض القابلة للاختيار (ثابت خادميّاً ⇒ staleTime طويل). */
export function useDiagnosisSymptoms(enabled = true): UseQueryResult<SymptomCatalogResponse> {
  return useQuery<SymptomCatalogResponse>({
    queryKey: ['diagnosis-symptoms'],
    queryFn:  () => kongApi.get('/api/v1/diagnose/symptoms').then(r => r.data),
    staleTime:60 * 60_000,
    enabled,
    retry:    false,
  });
}

/** تشخيص أوّليّ بقواعد الأعراض — مرشّحون مرتّبون لا حكم قاطع (next_step_ar يُعرَض حرفيّاً). */
export function useDiagnose(): ReturnType<typeof useMutation<DiagnoseResponse, Error, DiagnosePayload>> {
  return useMutation<DiagnoseResponse, Error, DiagnosePayload>({
    mutationFn: (payload) => kongApi.post('/api/v1/diagnose', payload).then(r => r.data),
  });
}

/** الآفات المدعومة بخطط إدارة متكاملة. */
export function useIpmPests(enabled = true): UseQueryResult<IpmPestsResponse> {
  return useQuery<IpmPestsResponse>({
    queryKey: ['ipm-pests'],
    queryFn:  () => kongApi.get('/api/v1/ipm/pests').then(r => r.data),
    staleTime:60 * 60_000,
    enabled,
    retry:    false,
  });
}

/** خطّة IPM المتدرّجة لآفة (وقاية → مراقبة → حيويّ → كيميائيّ ملاذاً أخيراً). */
export function useIpmPlan(pest: string | null | undefined): UseQueryResult<IpmPlanResponse> {
  return useQuery<IpmPlanResponse>({
    queryKey: ['ipm-plan', pest ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/ipm/plan', { params: { pest } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!pest,
    retry:    false,
  });
}

/** الآفات المحتملة لمحصول الحقل (وقاية استباقيّة — الخادم يحلّ المرادف العربيّ). */
export function useIpmCropPests(crop: string | null | undefined): UseQueryResult<CropPestsResponse> {
  return useQuery<CropPestsResponse>({
    queryKey: ['ipm-crop-pests', crop ?? 'none'],
    queryFn:  () => kongApi.get('/api/v1/ipm/crop-pests', { params: { crop } }).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  !!crop,
    retry:    false,
  });
}

/** تقييم شامل للملوحة من قياسات المستخدم (ECe/ECw/SAR) — أحكام FAO من الخادم. */
export function useSalinityAssess(): ReturnType<typeof useMutation<SalinityAssessResponse, Error, SalinityPayload>> {
  return useMutation<SalinityAssessResponse, Error, SalinityPayload>({
    mutationFn: (payload) => kongApi.post('/api/v1/salinity/assess', payload).then(r => r.data),
  });
}

// ── سيناريوهات «ماذا لو؟» (وكيل H) — محاكاة افتراضات، ليست تنبّؤاً معايَراً ──
import type {
  PlantingScenarioPayload, PlantingScenarioResult, RainfallScenarioPayload, RainfallScenarioResult,
  TemperatureScenarioPayload, TemperatureScenarioResult, WaterTwinScenarioPayload, WaterTwinScenarioResult,
} from '../lib/whatIfScenarios';

/** سيناريو الحرارة (+Δ°م): أثر على GDD/المراحل — افتراض المستخدم لا تنبّؤ. */
export function useScenarioTemperature(): ReturnType<typeof useMutation<TemperatureScenarioResult, Error, TemperatureScenarioPayload>> {
  return useMutation<TemperatureScenarioResult, Error, TemperatureScenarioPayload>({
    mutationFn: (payload) => kongApi.post('/api/v1/scenario/temperature', payload).then(r => r.data),
  });
}

/** سيناريو المطر (±٪): أثر على ميزان الماء. */
export function useScenarioRainfall(): ReturnType<typeof useMutation<RainfallScenarioResult, Error, RainfallScenarioPayload>> {
  return useMutation<RainfallScenarioResult, Error, RainfallScenarioPayload>({
    mutationFn: (payload) => kongApi.post('/api/v1/scenario/rainfall', payload).then(r => r.data),
  });
}

/** سيناريو تاريخ الزراعة (تبكير/تأخير أيّاماً). */
export function useScenarioPlantingDate(): ReturnType<typeof useMutation<PlantingScenarioResult, Error, PlantingScenarioPayload>> {
  return useMutation<PlantingScenarioResult, Error, PlantingScenarioPayload>({
    mutationFn: (payload) => kongApi.post('/api/v1/scenario/planting-date', payload).then(r => r.data),
  });
}

/** توأم الماء: مساران (مرجعيّ/معدَّل) ليوميّات رطوبة افتراضيّة. */
export function useScenarioWaterTwin(): ReturnType<typeof useMutation<WaterTwinScenarioResult, Error, WaterTwinScenarioPayload>> {
  return useMutation<WaterTwinScenarioResult, Error, WaterTwinScenarioPayload>({
    mutationFn: (payload) => kongApi.post('/api/v1/scenario/water-twin', payload).then(r => r.data),
  });
}

// ── Approvals Console — الموافقات البشريّة المعلّقة (v58 + SEC-3.1) ──
import type { PendingAgentApproval, PendingApprovalsResponse } from '../lib/approvalsConsole';

/** طلبات موافقة وكيل AI المعلّقة للمستأجِر (كان المخزن بلا نقطة قراءة). */
export function usePendingAgentApprovals(enabled = true): UseQueryResult<PendingApprovalsResponse> {
  return useQuery<PendingApprovalsResponse>({
    queryKey: ['pending-agent-approvals'],
    queryFn:  () => kongApi.get('/api/ai-agronomist/approvals/pending').then(r => r.data as PendingApprovalsResponse)
      .catch((e) => { if (isDisabled404(e)) return { pending: [], count: 0, disabled: true }; throw e; }),
    staleTime:30_000,
    enabled,
    retry:    false,
  });
}

/** اعتماد/رفض طلب أداة وكيل — الموافِق المسجَّل هو هويّة البوّابة (SEC-3.1) لا الـbody. */
export function useDecideAgentApproval(): ReturnType<typeof useMutation<unknown, Error, { approval: PendingAgentApproval; decision: 'approve' | 'deny'; reason?: string }>> {
  return useMutation<unknown, Error, { approval: PendingAgentApproval; decision: 'approve' | 'deny'; reason?: string }>({
    mutationFn: ({ approval, decision, reason }) => kongApi
      .post(`/api/ai-agronomist/approvals/${decision}`, { approval, reason })
      .then(r => r.data),
  });
}

// ── Fields & Tasks ────────────────────────────────────────────
export function useFields() {
  const { user } = useAuthStore();
  const tid = user?.tenant_id ?? 'default';
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

// ── Imagery Timeline (إنتاج): خطّ زمنيّ خادميّ جاهز + thumbnail_url (قراءة، نطاق حقل) ──
// GET /api/v1/fields/{id}/imagery/timeline?months=N. retry:false كي تُكشَف الحالة الفارغة
// الصادقة فوراً. المفتاح يضمّ المستأجِر + الأشهر لعزل الكاش.
export function useFieldImageryTimeline(
  fieldId?: string,
  months = 24,
): UseQueryResult<ImageryTimeline, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<ImageryTimeline, Error>({
    queryKey: ['field-imagery-timeline', tid, fieldId ?? 'none', months],
    queryFn:  () => fetchFieldImageryTimeline(fieldId as string, months),
    enabled:  !!fieldId,
    staleTime:5 * 60_000,
    retry:    false,
  });
}

// ── Field State (موحّد): مصدر الحقيقة الواحد لكل الشاشات (قراءة فقط، نطاق حقل) ──
// GET /api/v1/fields/{id}/state/full. مُفعَّل مع fieldId. retry:false كي تُكشَف
// الأقسام غير المتاحة (available:false) بصدق. المفتاح يضمّ المستأجِر لعزل الكاش.
export function useFieldState(fieldId?: string): UseQueryResult<FieldStateFull, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<FieldStateFull, Error>({
    queryKey: ['field-state-full', tid, fieldId ?? 'none'],
    queryFn:  () => fetchFieldState(fieldId as string),
    enabled:  !!fieldId,
    staleTime:60_000,
    retry:    false,
  });
}

// ── Field Terrain: إحصاءات التضاريس من DEM حقيقيّ (قراءة فقط، نطاق حقل) ──
// GET /api/v1/fields/{id}/terrain. مُفعَّل مع fieldId فقط. retry:false كي تُكشَف
// حالة `computed:false` (لا DEM/لا bbox) فوراً وتُعرَض بصدق. المفتاح يضمّ المستأجِر.
export function useFieldTerrain(fieldId?: string): UseQueryResult<FieldTerrain, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<FieldTerrain, Error>({
    queryKey: ['field-terrain', tid, fieldId ?? 'none'],
    queryFn:  () => fetchFieldTerrain(fieldId as string),
    enabled:  !!fieldId,
    staleTime:10 * 60_000,
    retry:    false,
  });
}

// ── Agronomic Replay: إعادة تشغيل الموسم (قراءة فقط، نطاق حقل) ──
// GET /api/v1/fields/{id}/agronomic-replay. مُفعَّل فقط مع fieldId. retry:false كي
// يُكشَف 404 (العلم FEATURE_REPLAY_MAP مُطفأ) فوراً ⇒ إشعار «الميزة غير مُفعَّلة»،
// و503 ⇒ حالة خطأ صادقة. لا fallback وهميّ. المفتاح يضمّ المستأجِر لعزل الكاش.
export function useAgronomicReplay(fieldId?: string): UseQueryResult<AgronomicReplayResult, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<AgronomicReplayResult, Error>({
    queryKey: ['agronomic-replay', tid, fieldId ?? 'none'],
    queryFn:  () => fetchAgronomicReplay(fieldId as string),
    enabled:  !!fieldId,
    staleTime:2 * 60_000,
    retry:    false,
  });
}

// ── Field Workspace: مساحة عمل الحقل (المصدر الأساسيّ لكرت Field Workspace Map) ──
// قراءة حيّة (field:view) عبر البوّابة: ملخّص الحقل + كتالوج الطبقات (كلّ طبقة
// تُعلن توفّرها بصدق) + خطّ زمنيّ من أحداث مسجّلة فقط. مُفعَّلة فقط مع fieldId.
// لا fallback وهميّ: عند الخطأ (404 حقل ليس للمستأجِر / 503 DB) يُرفض الاستعلام
// لتعرض الواجهة حالة صادقة (StateViews). retry:false كبقيّة قوائم المنصّة.
export function useFieldWorkspace(fieldId?: string): UseQueryResult<FieldWorkspace, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<FieldWorkspace, Error>({
    queryKey: QK.fieldWorkspace(tid, fieldId ?? 'none'),
    queryFn:  () => fetchFieldWorkspace(fieldId as string),
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

// ── وصفات المعدّل المتغيّر اليدويّة (Manual VRT Prescriptions، v95) ──
// سرد الوصفات المحفوظة لحقل (field:view، tenant-scoped + RLS). لا fallback وهميّ:
// 503 (DB مُعطَّلة) / 404 (حقل خارج المستأجِر) يُرفع ليعرض الـUI خطأً صادقاً؛ والقائمة
// الفارغة تُعرَض كما هي (note_ar من الخادم) — لا اختراع وصفات.
export function useFieldPrescriptions(
  fieldId: string,
  enabled = true,
): UseQueryResult<PrescriptionListResponse> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<PrescriptionListResponse>({
    queryKey: QK.savedPrescriptions(tid, fieldId),
    queryFn:  () => fetchPrescriptions(fieldId),
    staleTime:5 * 60_000,
    retry:    false,
    enabled:  !!fieldId && enabled,
  });
}

// حفظ وصفة يدويّة — يُبطِل كاش وصفات الحقل كي تظهر فوراً في القائمة. الخطأ
// (422 نوع منتج / 404 حقل / 503 DB / 403 RBAC) يُرمى ليعرضه النموذج بصدق.
export function useCreatePrescription(
  fieldId: string,
): UseMutationResult<SavedPrescription & { persisted: boolean }, Error, PrescriptionCreateInput> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<SavedPrescription & { persisted: boolean }, Error, PrescriptionCreateInput>({
    mutationFn: (payload) => createPrescription(fieldId, payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.savedPrescriptions(tid, fieldId) }); },
  });
}

/**
 * استيراد حقل من ملفّ (GeoJSON/KML) أو نقاط GPS (field:create).
 * عند النجاح يُبطِل قائمة الحقول كي تظهر فوراً. الخطأ (400 تحليل / 422 هندسة /
 * 503 DB) يُرمى ليعرضه النموذج بصدق — لا ابتلاع.
 */
export function useImportField(): UseMutationResult<unknown, Error, FieldImportInput> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<unknown, Error, FieldImportInput>({
    mutationFn: (payload) => importField(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.fields(tid) }); },
  });
}

/**
 * دمج عدّة حقول مصدر في حقل واحد ذرّيّاً (field:create) — POST /api/v1/fields/merge.
 * يستبدل لاذرّيّة الواجهة (POST + حلقة DELETE). عند النجاح يُبطِل قائمة الحقول كي
 * يختفي المصادر ويظهر المدموج فوراً. الخطأ (404/409/422/503) يُرمى ليُعرَض بصدق.
 */
export function useMergeFields(): UseMutationResult<unknown, Error, FieldMergeInput> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<unknown, Error, FieldMergeInput>({
    mutationFn: (payload) => mergeFields(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.fields(tid) }); },
  });
}

/**
 * انقسام حقل واحد إلى حقول وليدة ذرّيّاً (field:create) — POST /api/v1/fields/split.
 * يستبدل لاذرّيّة الواجهة (POST×n + DELETE). عند النجاح يُبطِل قائمة الحقول كي يختفي
 * الأصل وتظهر الأطفال فوراً. الخطأ (404/409/422/503) يُرمى ليُعرَض بصدق.
 */
export function useSplitField(): UseMutationResult<unknown, Error, FieldSplitInput> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<unknown, Error, FieldSplitInput>({
    mutationFn: (payload) => splitField(payload),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: QK.fields(tid) }); },
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
  // صدق: لا ابتلاع صامت للأخطاء. كان .catch(() => ({tasks:[]})) يُحوّل فشل الخادم/
  // المصادقة إلى «لا مهامّ» فلا يُفعَّل isError أبداً (pseudo-mock). الآن يَطفو الخطأ
  // فتعرض TasksPage حالة ErrorState بصدق (retry:false كبقيّة قوائم المنصّة).
  return useQuery<{ tasks: Task[] }>({
    queryKey: QK.tasks(fieldId),
    queryFn:  () => kongApi.get('/api/v1/tasks', { params: fieldId ? { field_id: fieldId } : {} })
      .then(r => r.data),
    staleTime:2 * 60_000,
    refetchInterval: 5 * 60_000,
    retry: false,
  });
}

export function useCompleteTask() {
  return useMutation({
    mutationFn: ({ taskId, photoUrl }: { taskId: string; photoUrl?: string }) =>
      kongApi.patch(`/api/v1/tasks/${taskId}`, { status: 'completed', photo_url: photoUrl }).then(r => r.data),
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

// ── محاكاة الموسم (Crop-model simulation, RUE/FAO-56) — v39 ──────────
// يشغّل محاكاة محصوليّة للموسم على الخادم ويحفظ ناتجها (تقديرات بنطاق وثقة).
// طفرة (mutation) بلا تخزين مؤقّت وهميّ: عند الخطأ (503 طقس/قاعدة، 404 موسم،
// 422 بلا إحداثيّات) تعرض الواجهة الرسالة كما هي.
export function useSimulateSeason(): UseMutationResult<SeasonSimResult, Error, string> {
  return useMutation<SeasonSimResult, Error, string>({
    mutationFn: (seasonId) => simulateSeason(seasonId),
  });
}

// ── مواسم حقل (مع نتائج المحاكاة المُخزَّنة sim_*) — قراءة حيّة بلا تلفيق ──
// GET /api/v1/fields/{id}/seasons. مُفعَّل فقط مع fieldId. عند الخطأ (503 DB /
// 404 حقل / 403) يُرفض الاستعلام لتعرض الواجهة حالة صادقة (لا fallback وهميّ).
export function useSeasons(fieldId?: string): UseQueryResult<SeasonSummary[], Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<SeasonSummary[], Error>({
    queryKey: QK.seasons(tid, fieldId ?? 'none'),
    queryFn:  () => fetchSeasons(fieldId as string),
    staleTime:5 * 60_000,
    retry:    false,
    enabled:  !!fieldId,
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

// تشغيل تقييم التنبيهات لكلّ الحقول دفعةً (أتمتة عند الطلب، sahool-platform)
// — يُبطِل كاش تنبيهات المستأجِر ليُعاد جلب القائمة بالتنبيهات المُولَّدة حديثاً.
export function useRunAllAlerts(): UseMutationResult<AlertsRunResult, Error, void> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<AlertsRunResult, Error, void>({
    mutationFn: () => runAllFieldsAlerts(),
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

// حالة المعايرة الإقليميّة (GET /api/v1/calibration) — قراءة فقط. تكشف لكلّ إقليم
// هل ثوابته الأغرونوميّة مُتحقَّق منها ميدانيّاً أم ما تزال افتراضات FAO عامّة. ثابتة
// نسبيّاً (تتغيّر مع جمع بيانات ميدانيّة) ⇒ staleTime طويل. لا fallback وهميّ.
export function useCalibration(): UseQueryResult<CalibrationOverview, Error> {
  return useQuery<CalibrationOverview, Error>({
    queryKey: ['calibration'],
    queryFn:  () => fetchCalibration(),
    staleTime:60 * 60_000,
    retry:    false,
  });
}

// ── منضدة المعايرة (Calibration Workbench) — مقارنة القاعدة بالمُدام + اقتراح/موافقة/رفض/تدقيق ──
// كلّها معزولة بالمستأجِر خادميّاً (RLS). مُفتاح الكاش بالمنطقة. لا fallback وهميّ:
// الخطأ (503 DB / 403 RBAC) يُرفض الاستعلام لتعرض المنضدة حالة صادقة. retry:false.

// القاعدة الموروثة لمنطقة (GET /{region}) — مرجع المقارنة. ثابتة نسبيّاً.
export function useRegionCalibration(region?: string): UseQueryResult<CalibrationProfile, Error> {
  const r = (region ?? '').trim();
  return useQuery<CalibrationProfile, Error>({
    queryKey: ['calibration-base', r],
    queryFn:  () => fetchRegionCalibration(r),
    staleTime:60 * 60_000,
    retry:    false,
    enabled:  !!r,
  });
}

// الملفّ المُحلّ مع التجاوز المُدام (GET /{region}/resolved) — الطرف الآخر للمقارنة.
// staleTime قصير (يتغيّر مع الإدامة/الحذف) ⇒ يُعاد جلبه فور الإبطال بعد الكتابة.
export function useResolvedCalibration(region?: string): UseQueryResult<ResolvedCalibration, Error> {
  const r = (region ?? '').trim();
  return useQuery<ResolvedCalibration, Error>({
    queryKey: ['calibration-resolved', r],
    queryFn:  () => fetchResolvedCalibration(r),
    staleTime:60_000,
    retry:    false,
    enabled:  !!r,
  });
}

// كلّ التجاوزات المُدامة للمستأجِر (GET /overrides/all) — مصدر التدقيق البديل + إدارة.
export function useCalibrationOverrides(): UseQueryResult<CalibrationOverridesResult, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<CalibrationOverridesResult, Error>({
    queryKey: ['calibration-overrides', tid],
    queryFn:  () => fetchCalibrationOverrides(),
    staleTime:60_000,
    retry:    false,
  });
}

// سجلّ تدقيق منطقة (GET /{region}/audit) — أفضل-جهد: null عند 404/خطأ (النقطة قد
// لا تتوفّر) فترتدّ المنضدة إلى overrides/all. data=null حالةٌ صريحة لا خطأ.
export function useCalibrationAudit(region?: string): UseQueryResult<CalibrationAudit | null, Error> {
  const r = (region ?? '').trim();
  return useQuery<CalibrationAudit | null, Error>({
    queryKey: ['calibration-audit', r],
    queryFn:  () => fetchCalibrationAudit(r),
    staleTime:60_000,
    retry:    false,
    enabled:  !!r,
  });
}

// اقتراح/تحقّق (POST /{region}/propose-values) — يقترح ولا يكتب. طفرة بلا إبطال
// (لا تغيّر حالة مُدامة): تُعيد accepted/rejected لعرضها بأسباب عربيّة.
export function useProposeCalibrationValues(): UseMutationResult<
  CalibrationValidation, Error, { region: string; values: CalibrationValuesInput }
> {
  return useMutation<CalibrationValidation, Error, { region: string; values: CalibrationValuesInput }>({
    mutationFn: ({ region, values }) => proposeCalibrationValues(region, values),
  });
}

// موافقة/إدامة (POST /{region}/override) — يُبطِل القاعدة/المُحلّ/التجاوزات/التدقيق
// للمنطقة كي تظهر القيم المُعايَرة فوراً في المقارنة. الخطأ (422/503) يُرفع للنموذج.
export function useSetRegionOverride(): UseMutationResult<
  CalibrationOverrideResult, Error, { region: string; values: CalibrationValuesInput }
> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<CalibrationOverrideResult, Error, { region: string; values: CalibrationValuesInput }>({
    mutationFn: ({ region, values }) => setRegionOverride(region, values),
    onSuccess:  (_d, { region }) => {
      qc.invalidateQueries({ queryKey: ['calibration-resolved', region] });
      qc.invalidateQueries({ queryKey: ['calibration-base', region] });
      qc.invalidateQueries({ queryKey: ['calibration-audit', region] });
      qc.invalidateQueries({ queryKey: ['calibration-overrides', tid] });
    },
  });
}

// رفض/عكس (DELETE /{region}/override) — يعيد المنطقة للوراثة ويُبطِل نفس المفاتيح.
export function useDeleteRegionOverride(): UseMutationResult<
  { region: string; reverted: boolean }, Error, string
> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<{ region: string; reverted: boolean }, Error, string>({
    mutationFn: (region) => deleteRegionOverride(region),
    onSuccess:  (_d, region) => {
      qc.invalidateQueries({ queryKey: ['calibration-resolved', region] });
      qc.invalidateQueries({ queryKey: ['calibration-base', region] });
      qc.invalidateQueries({ queryKey: ['calibration-audit', region] });
      qc.invalidateQueries({ queryKey: ['calibration-overrides', tid] });
    },
  });
}

// تطبيق التكيّف بدليل مُدام (POST /{region}/adapt-from-evidence/apply, confirm=true).
// يُبطِل المفاتيح كالإدامة (قد يُدِيم تجاوزاً عند التأهّل). الخطأ (422/503) يُرفع.
export function useApplyAdaptFromEvidence(): UseMutationResult<
  AdaptApplyResult, Error, { region: string; input: AdaptApplyInput }
> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<AdaptApplyResult, Error, { region: string; input: AdaptApplyInput }>({
    mutationFn: ({ region, input }) => applyAdaptFromEvidence(region, input),
    onSuccess:  (_d, { region }) => {
      qc.invalidateQueries({ queryKey: ['calibration-resolved', region] });
      qc.invalidateQueries({ queryKey: ['calibration-base', region] });
      qc.invalidateQueries({ queryKey: ['calibration-audit', region] });
      qc.invalidateQueries({ queryKey: ['calibration-overrides', tid] });
    },
  });
}

// سلسلة النَّسَب المُدامة (GET /api/v1/decision/{id}/lineage) — قراءة فقط، عند الطلب.
// مُفعَّلة فقط عند توفّر decision_id (إدخال المستخدم). لا fallback وهميّ: الخطأ
// (404 قرار غير مُدام / 503 DB) يُرفض الاستعلام لتعرض الواجهة حالة صادقة.
export function useDecisionLineage(decisionId?: string): UseQueryResult<DecisionLineage, Error> {
  const id = (decisionId ?? '').trim();
  return useQuery<DecisionLineage, Error>({
    queryKey: ['decision-lineage', id],
    queryFn:  () => fetchDecisionLineage(id),
    staleTime:5 * 60_000,
    retry:    false,
    enabled:  !!id,
  });
}

// الدليل المتراكم لمنطقة (GET /api/v1/calibration/{region}/evidence/persisted) — قراءة
// فقط. يُظهر تقدّم العيّنات نحو التحقّق ومستوى الدليل. صدق: تقديريّ غير مُعايَر
// (calibrated=false) حتى تكفي العيّنات. لا fallback وهميّ — الخطأ يُرفض الاستعلام.
export function usePersistedEvidence(region?: string): UseQueryResult<PersistedEvidence, Error> {
  const r = (region ?? '').trim();
  return useQuery<PersistedEvidence, Error>({
    queryKey: ['persisted-evidence', r],
    queryFn:  () => fetchPersistedEvidence(r),
    staleTime:5 * 60_000,
    retry:    false,
    enabled:  !!r,
  });
}

// خريطة الدليل (GET /api/v1/evidence/map) — قراءة فقط. مستوى الدليل خلف قرارات كلّ
// حقل (مؤكَّد/مدعوم/إرشاديّ/يحتاج بيانات) على خريطة 2D + قائمة. مُفهرَسة بالمستأجِر
// (العزل بـRLS خادميّاً). لا fallback وهميّ: الخطأ (404 العلم مُطفأ، 503 DB) يُرفض
// الاستعلام لتعرض الواجهة حالة صادقة (الصفحة تكشف 404 عبر error.response?.status
// لرسالة «الميزة غير مُفعَّلة»). retry:false كبقيّة صفحات العلم.
export function useEvidenceMap(): UseQueryResult<EvidenceMapResult, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<EvidenceMapResult, Error>({
    queryKey: ['evidence-map', tid],
    queryFn:  () => fetchEvidenceMap(),
    staleTime:5 * 60_000,
    retry:    false,
  });
}

// ── توائم الأجهزة وثقة الحسّاس (Device Twin) — قراءة فقط ──
// يجلب التوأم الرقميّ + درجة الثقة لكلّ جهاز (GET /api/v1/devices/twin). لا fallback
// وهميّ: الخطأ (404 العلم FEATURE_DEVICE_TWIN مُطفأ، 503 DB) يُرفض الاستعلام لتعرض
// الواجهة حالة صادقة (الصفحة تكشف 404 عبر error.response?.status لرسالة «الميزة غير
// مُفعَّلة»). retry:false كبقيّة صفحات العلم. مُفهرَس بالمستأجِر الفعّال (عزل RLS خادميّاً).
export function useDeviceTwin(): UseQueryResult<DeviceTwinResult, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<DeviceTwinResult, Error>({
    queryKey: ['device-twin', tid],
    queryFn:  () => fetchDeviceTwin(),
    staleTime:5 * 60_000,
    retry:    false,
  });
}

// ── رصد حلقة التنفيذ (Execution Feedback) — قراءة فقط ──
// يجلب لكلّ قرار حديث هل نُفِّذ وهل طابقت النتيجة الخطّة (GET /api/v1/execution/feedback)
// — إغلاق حلقة القرار→التنفيذ→النتيجة. لا fallback وهميّ: الخطأ (404 العلم
// FEATURE_EXECUTION_FEEDBACK مُطفأ، 503 DB) يُرفض الاستعلام لتعرض الواجهة حالة صادقة
// (الصفحة تكشف 404 عبر error.response?.status لرسالة «الميزة غير مُفعَّلة»). retry:false
// كبقيّة صفحات العلم. مُفهرَس بالمستأجِر الفعّال (عزل RLS خادميّاً). قراءة فقط لا أوامر.
export function useExecutionFeedback(): UseQueryResult<ExecutionFeedbackResult, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<ExecutionFeedbackResult, Error>({
    queryKey: ['execution-feedback', tid],
    queryFn:  () => fetchExecutionFeedback(),
    staleTime:5 * 60_000,
    retry:    false,
  });
}

// ── لوحة رصد التعلّم (Learning/Lineage Observability) — قراءة فقط ──
// سرد القرارات المُدامة (GET /api/v1/decision/records). لا fallback وهميّ: الخطأ
// (503 DB / 403 RBAC) يُرفض الاستعلام لتعرض الواجهة حالة صادقة. retry:false كبقيّة
// قوائم المنصّة. مُفهرَس بالمستأجِر الفعّال (العزل بـRLS خادميّاً).
export function useDecisionRecords(limit = 200): UseQueryResult<DecisionRecordsResult, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<DecisionRecordsResult, Error>({
    queryKey: ['decision-records', tid, limit],
    queryFn:  () => fetchDecisionRecords(limit),
    staleTime:5 * 60_000,
    retry:    false,
  });
}

// تلخيص حلقة التعلّم لكلّ منطقة (GET /api/v1/learning/summary) — قراءة فقط، أفضل-جهد.
// النقطة قد لا تتوفّر بعد: fetchLearningSummary يُعيد null عند 404/خطأ (لا تلفيق)،
// فلا يُفعَّل isError — تعرض الواجهة حالةً فارغة صادقة. retry:false (لا إعادة محاولة
// على نقطة غائبة). data=null حالةٌ صريحة لا خطأ.
export function useLearningSummary(): UseQueryResult<LearningSummary | null, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<LearningSummary | null, Error>({
    queryKey: ['learning-summary', tid],
    queryFn:  () => fetchLearningSummary(),
    staleTime:5 * 60_000,
    retry:    false,
  });
}

// ── Decision Studio: شرح القرار + إعادة التشغيل (قراءة فقط، عند الطلب) ──
// مُفعَّل فقط عند توفّر decision_id (إدخال المستخدم). fetchDecisionExplain يجرّب
// /explain ثمّ يرتدّ عند 404 إلى /lineage (العلم FEATURE_DECISION_STUDIO قد يكون
// مُطفأً). لا fallback وهميّ: 503/403 يُرفض الاستعلام لحالة صادقة. retry:false كي
// لا تُعاد المحاولة على نقطة غائبة (الارتداد يُعالَج داخل الـfetcher نفسه).
export function useDecisionExplain(decisionId?: string): UseQueryResult<DecisionExplainResult, Error> {
  const id = (decisionId ?? '').trim();
  return useQuery<DecisionExplainResult, Error>({
    queryKey: ['decision-explain', id],
    queryFn:  () => fetchDecisionExplain(id),
    staleTime:5 * 60_000,
    retry:    false,
    enabled:  !!id,
  });
}

// ── Agronomic Timeline: الخطّ الزمنيّ الموحّد للحقل (قراءة فقط) ──
// GET /api/v1/fields/{id}/unified-timeline. مُفعَّل فقط مع fieldId. الفئة (category)
// جزءٌ من المفتاح: تغييرها يُعيد الجلب المُرشَّح خادميّاً. لا fallback وهميّ — عند
// تعطّل القاعدة يُرجِع الخادم خطّاً فارغاً + note_ar (حالة فارغة صادقة لا خطأ).
export function useFieldGeometryHistory(
  fieldId?: string,
  limit = 50,
): UseQueryResult<FieldGeometryHistory, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<FieldGeometryHistory, Error>({
    queryKey: ['field-geometry-history', tid, fieldId ?? 'none', limit],
    queryFn:  () => fetchFieldGeometryHistory(fieldId as string, limit),
    staleTime:2 * 60_000,
    retry:    false,
    enabled:  !!fieldId,
  });
}

export function useUnifiedTimeline(
  fieldId?: string,
  opts: { limit?: number; newestFirst?: boolean; category?: string } = {},
): UseQueryResult<UnifiedTimeline, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  const { limit = 200, newestFirst = true, category } = opts;
  return useQuery<UnifiedTimeline, Error>({
    queryKey: ['unified-timeline', tid, fieldId ?? 'none', limit, newestFirst, category ?? 'all'],
    queryFn:  () => fetchUnifiedTimeline(fieldId as string, { limit, newestFirst, category }),
    staleTime:2 * 60_000,
    retry:    false,
    enabled:  !!fieldId,
  });
}

// ── Decision Confidence: ثقة القرار الموحَّدة لحقل (قراءة فقط، نطاق حقل) ──
// GET /api/v1/fields/{id}/decision-confidence. مُفعَّل فقط مع fieldId. retry:false كي
// يُكشَف 404 (العلم FEATURE_DECISION_CONFIDENCE مُطفأ) فوراً ⇒ إشعار «الميزة غير مُفعَّلة»،
// و503 ⇒ حالة خطأ صادقة. لا fallback وهميّ. المفتاح يضمّ المستأجِر لعزل الكاش.
export function useDecisionConfidence(fieldId?: string): UseQueryResult<DecisionConfidenceResult, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<DecisionConfidenceResult, Error>({
    queryKey: ['decision-confidence', tid, fieldId ?? 'none'],
    queryFn:  () => fetchDecisionConfidence(fieldId as string),
    staleTime:2 * 60_000,
    retry:    false,
    enabled:  !!fieldId,
  });
}

// خطّة الريّ التنبّؤيّة (خطّ «مركز المحاصيل»): نسيج+عمق ⇒ TAW ⇒ سياسة ⇒ جدول ريّ.
export function useComputeIrrigationPlan(): UseMutationResult<IrrigationPlanResult, Error, IrrigationPlanInput> {
  return useMutation<IrrigationPlanResult, Error, IrrigationPlanInput>({
    mutationFn: (payload) => computeIrrigationPlan(payload),
  });
}

// قرار المحصول الموحّد: ريّ + تسميد + مخاطر + ثقة من حالة محصول واحدة.
export function useCropDecision(): UseMutationResult<CropDecisionResult, Error, CropDecisionInput> {
  return useMutation<CropDecisionResult, Error, CropDecisionInput>({
    mutationFn: (payload) => computeCropDecision(payload),
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

// المايسترو — النمط الجديد: يبدأ job سريعاً ثم تُقرأ الحالة عبر polling.
export function useStartFieldIntelligenceJob() {
  return useMutation<FieldIntelJobStatus, Error, FieldIntelInput>({
    mutationFn: (input) => startAnalyzeFieldIntelligence(input),
  });
}

export function useFieldIntelligenceJob(jobId?: string | null) {
  return useQuery<FieldIntelJobStatus, Error>({
    queryKey: ['field-intelligence-job', jobId],
    enabled: !!jobId,
    queryFn: () => getFieldIntelligenceJob(jobId as string),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status === 'completed' || status === 'failed' || status === 'cancelled' ? false : 1000;
    },
  });
}

export function useCancelFieldIntelligenceJob() {
  return useMutation<FieldIntelJobStatus, Error, string>({
    mutationFn: (jobId) => cancelFieldIntelligenceJob(jobId),
  });
}

// توافق قديم: يبقى متاحاً لكنه يستعمل job + polling، وليس POST متزامناً طويلاً.
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
        user_id:              user?.id != null ? String(user.id) : 'unknown',
        tenant_id:            user?.tenant_id ?? 'default',
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
        user_id:   user?.id != null ? String(user.id) : 'unknown',
        tenant_id: user?.tenant_id ?? 'default',
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
        user_id:      user?.id != null ? String(user.id) : 'unknown',
        tenant_id:    user?.tenant_id ?? 'default',
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

// ── Fleet Health: صحّة أسطول الأجهزة (كشف استباقي للصامت، مرتّب بالخطورة) ──
// قراءة حيّة (device:view) عبر البوّابة. لا fallback وهميّ: عند الخطأ (503 DB / 403
// RBAC) يُرفض الاستعلام لتعرض البلاطة حالة خطأ صادقة. ينعش دوريّاً (الصمت مُحتسَب
// من آخر ظهور). refetchInterval اختياريّ لجدار العرض المستمرّ.
export function useFleetHealth(
  opts: { refetchInterval?: number | false } = {},
): UseQueryResult<FleetHealth, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<FleetHealth, Error>({
    queryKey:        ['devices', 'fleet-health', tid],
    queryFn:         () => fetchFleetHealth(),
    staleTime:       60_000,
    refetchInterval: opts.refetchInterval ?? false,
    retry:           false,
  });
}

// ── Operation Center Wall: التلخيص التشغيليّ الموحّد (المصدر الأساسيّ للجدار) ──
// أفضل-جهد: fetchOperationsSummary يُرجِع null عند 404/أيّ خطأ (العلم
// FEATURE_OPERATIONS_WALL قد يكون مُطفأً) فترتدّ الصفحة لكلّ بلاطة لنقطتها المنفصلة.
// data=null حالةٌ صريحة لا خطأ ⇒ لا يُفعَّل isError. retry:false. refetchInterval اختياريّ.
export function useOperationsSummary(
  opts: { refetchInterval?: number | false } = {},
): UseQueryResult<OperationsSummary | null, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<OperationsSummary | null, Error>({
    queryKey:        ['operations-summary', tid],
    queryFn:         () => fetchOperationsSummary(),
    staleTime:       30_000,
    refetchInterval: opts.refetchInterval ?? false,
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

// أحدث رطوبة تربة لحقل من أجهزته (field:view). reading=null عند غياب قراءة صالحة —
// لا fallback وهميّ: الواجهة تعرض حالة صادقة. ينعش دوريّاً لمواكبة القراءات الحيّة.
export function useFieldSoilMoisture(
  fieldId: string | null | undefined,
): UseQueryResult<FieldSoilMoisture> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<FieldSoilMoisture>({
    queryKey:        QK.fieldSoilMoisture(tid, fieldId ?? ''),
    queryFn:         () => getFieldSoilMoisture(fieldId as string),
    staleTime:       60_000,
    refetchInterval: 60_000,
    enabled:         !!fieldId,
    retry:           false,
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
    queryFn:  () => listSharingKeys(includeRevoked).then((r) => (Array.isArray(r.keys) ? r.keys : [])),
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

// ── Yield Analysis: تحليل الغلّة (نمط FieldView، حيّ، tenant-scoped + analytics:view) ──
// GET /api/v1/analysis/yield: زراعة↔حصاد + أداء الهجن من جدول seasons المُخزَّن فقط.
// fieldId/season اختياريّان (فراغهما ⇒ كلّ المواسم للمستأجِر). لا fallback وهميّ:
// عند الخطأ (503 DB / 403 RBAC) يُرفض الاستعلام لتعرض الواجهة حالة صادقة. الفراغ
// (لا مواسم/لا حصاد) عقدٌ صحيح بقوائم فارغة + note_ar (لا 404 ولا تلفيق).
export function useYieldAnalysis(
  fieldId?: string,
  season?: string,
): UseQueryResult<YieldAnalysisResult, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<YieldAnalysisResult, Error>({
    queryKey: QK.yieldAnalysis(tid, fieldId ?? 'all', season ?? 'all'),
    queryFn:  () => getYieldAnalysis(fieldId, season),
    staleTime:60_000,
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

// ── Dashboard aggregation types ────────────────────────────────
// شكل عدّادات اللوحة كما يُصدِرها الخادم الحقيقيّ (sahool-platform
// `_shape_indicators_dashboard`): id/name_ar/value/unit/status من جداول
// fields/seasons/alerts — لا أرقام مخترعة.
export interface DashboardKpi {
  id: string;
  category?: string;
  name?: string;
  name_ar?: string;
  value: number | string;
  unit?: string;
  status?: string;
}

export interface DashboardFieldSummary {
  field_id: string;
  field_name: string;
  crop?: string;
  area_ha?: number;
  has_active_season?: boolean;
  ndvi?: number; // مُلحَق من vegetation `/v1/all_fields` بمطابقة field_id (إن توفّر)
}

export interface DashboardData {
  kpis: DashboardKpi[];
  fields_summary: DashboardFieldSummary[];
  alerts: unknown[];
  total_fields: number;
  active_alerts: number;
  generated_at?: string;
  // لا مصدر خلفيّ حقيقيّ لهذين ⇒ يُتركان undefined لتعرض اللوحة قيمها الاحتياطيّة
  // الثابتة (حجم كتالوج المؤشّرات / تسمية المصدر) بصدق بدل عدد مخترع.
  total_indicators?: number;
  data_freshness?: { source?: string };
}

// شكل ردّ vegetation `/v1/all_fields` (مصدر NDVI الحقليّ) — للمطابقة بـfield_id.
interface AllFieldsNdviResponse {
  fields?: Array<{ field_id: string; ndvi?: number }>;
  generated_at?: string;
}

// ── Dashboard aggregation hook ─────────────────────────────────
// المصدر الحقيقيّ للوحة: عدّادات + ملخّص الحقول + التنبيهات من الخادم المُجمِّع
// (`useDashboardKPIs` → GET /api/v1/indicators/dashboard، tenant-scoped + FIELD_VIEW).
// NDVI لكلّ حقل يُلحَق من vegetation `/v1/all_fields` بمطابقة field_id (مصدران حقيقيّان،
// بلا تلفيق). كانت النسخة السابقة تبني مفاتيح (allNdvi/indicators/…) لا يقرؤها
// المُستهلِك (kpis/fields_summary/total_fields…) ⇒ بيانات حيّة تُجلب ثمّ تُهمَل.
export function useDashboardData(primaryFieldId = '') {
  const dash       = useDashboardKPIs();
  const allNdvi    = useAllFieldsNdvi();
  const indicators = useIndicators(primaryFieldId);
  const weather    = useWeatherForecast();
  const tasks      = useTasks();
  const alerts     = useAlerts();
  const health     = useAllServicesHealth();
  const isLoading  = dash.isLoading || allNdvi.isLoading;
  const isError    = dash.isError;
  const refetch    = () => { dash.refetch?.(); allNdvi.refetch?.(); };

  // مطابقة NDVI الحقليّ (vegetation) إلى ملخّص الحقول (DB) عبر field_id.
  const allFields = allNdvi.data as AllFieldsNdviResponse | undefined;
  const ndviByField = new Map<string, number>();
  for (const f of allFields?.fields ?? []) {
    if (typeof f.ndvi === 'number') ndviByField.set(f.field_id, f.ndvi);
  }
  const kpis = (dash.data?.kpis ?? []) as DashboardKpi[];
  const fieldsSrc = (dash.data?.fields_summary ?? []) as DashboardFieldSummary[];
  const fields_summary = fieldsSrc.map((f) => ({ ...f, ndvi: ndviByField.get(f.field_id) ?? f.ndvi }));
  const alertRows = (dash.data?.alerts ?? []) as unknown[];

  const data: DashboardData = {
    kpis,
    fields_summary,
    alerts: alertRows,
    total_fields: fields_summary.length,
    active_alerts: alertRows.length,
    generated_at: allFields?.generated_at,
  };
  return { data, refetch, dash, allNdvi, indicators, weather, tasks, alerts, health, isLoading, isError };
}


// ── Lab Sampling hooks: soil/water sampling points and decision context ─────
export function useLabSamples(fieldId?: string): UseQueryResult<LabSampleRecord[]> {
  const { user } = useAuthStore();
  const tid = user?.tenant_id ?? 'default';
  return useQuery({
    queryKey: QK.labSamples(tid, fieldId),
    queryFn: () => listLabSamples(fieldId),
    staleTime: 60_000,
  });
}

export function useCreateLabSample(): UseMutationResult<LabSampleRecord, Error, LabSampleCreateInput> {
  const qc = useQueryClient();
  const { user } = useAuthStore();
  const tid = user?.tenant_id ?? 'default';
  return useMutation({
    mutationFn: createLabSample,
    onSuccess: (row) => {
      qc.invalidateQueries({ queryKey: QK.labSamples(tid, row.field_id) });
      qc.invalidateQueries({ queryKey: QK.labSamples(tid) });
    },
  });
}

export function useSubmitSoilLabResult(): UseMutationResult<SoilLabAnalysisResult, Error, SoilLabResultInput> {
  const qc = useQueryClient();
  const { user } = useAuthStore();
  const tid = user?.tenant_id ?? 'default';
  return useMutation({
    mutationFn: submitSoilLabResult,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['lab'] });
      qc.invalidateQueries({ queryKey: ['field-detail', tid] });
    },
  });
}

export function useLabDecisionContext(fieldId?: string): UseQueryResult<LabDecisionContext> {
  const { user } = useAuthStore();
  const tid = user?.tenant_id ?? 'default';
  return useQuery({
    queryKey: QK.labContext(tid, fieldId ?? 'none'),
    queryFn: () => fetchLabDecisionContext(fieldId as string),
    enabled: Boolean(fieldId),
    staleTime: 60_000,
  });
}


// ── OneSoil-inspired precision workflow hooks ─────────────────────────────
export function useProductivityZones(fieldId?: string, observations: ProductivityObservationInput[] = []): UseQueryResult<ProductivityZoneResult> {
  const { user } = useAuthStore();
  const tid = user?.tenant_id ?? 'default';
  return useQuery({
    queryKey: QK.productivityZones(tid, fieldId ?? 'none', observations.length),
    queryFn: () => buildProductivityZones(fieldId as string, observations),
    enabled: Boolean(fieldId),
    staleTime: 120_000,
  });
}

export function useZoneSamplingPlan(fieldId?: string, observations: ProductivityObservationInput[] = []): UseQueryResult<ZoneSamplingPlanResult> {
  const { user } = useAuthStore();
  const tid = user?.tenant_id ?? 'default';
  return useQuery({
    queryKey: QK.zoneSamplingPlan(tid, fieldId ?? 'none', observations.length),
    queryFn: () => buildZoneSamplingPlan(fieldId as string, observations),
    enabled: Boolean(fieldId),
    staleTime: 120_000,
  });
}

export function useDailyAiBrief(fieldId?: string, signals: Record<string, unknown> = {}, tasks: Record<string, unknown>[] = []): UseQueryResult<DailyAiBriefResult> {
  const { user } = useAuthStore();
  const tid = user?.tenant_id ?? 'default';
  return useQuery({
    queryKey: QK.dailyAiBrief(tid, fieldId ?? 'none'),
    queryFn: () => fetchDailyAiBrief(fieldId as string, signals, tasks),
    enabled: Boolean(fieldId),
    staleTime: 60_000,
  });
}
