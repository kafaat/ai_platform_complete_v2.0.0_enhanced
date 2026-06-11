// ═══════════════════════════════════════════════════════════════
// SAHOOL v9.0 — Unified API Client
// ربط حقيقي مع 6 خدمات خلفية + mock fallback ذكي
//
// الخدمات:
//   indicators-service  → :8091  (33 مؤشر + WOFOST)
//   vegetation-service  → :8090  (7 مؤشرات Sentinel-2)
//   weather-service     → :8092  (الطقس + WOFOST format)
//   soil-service        → :8094  (تربة + N recommendation)
//   satellite-tiles     → :8098  (XYZ tiles)
//   auth-service        → :8120  (JWT)
//   kong-gateway        → :8000  (البوابة الموحدة)
// ═══════════════════════════════════════════════════════════════

import axios, { type AxiosInstance } from 'axios';

// ── Environment detection ──────────────────────────────────────
const IS_LOCAL = typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

const KONG_URL       = import.meta.env.VITE_API_URL             || (IS_LOCAL ? 'http://localhost:8000' : '/api');
const WEATHER_URL    = import.meta.env.VITE_WEATHER_URL         || 'http://localhost:8092';
const SOIL_URL       = import.meta.env.VITE_SOIL_URL            || 'http://localhost:8094';
const INDICATORS_URL = import.meta.env.VITE_INDICATORS_URL      || 'http://localhost:8091';
const VEGETATION_URL = import.meta.env.VITE_VEGETATION_URL      || 'http://localhost:8090';
const RASTER_URL     = import.meta.env.VITE_RASTER_URL          || 'http://localhost:8099';
const AUTH_URL       = import.meta.env.VITE_AUTH_URL            || 'http://localhost:8120';
const MOCK_MODE      = import.meta.env.VITE_MOCK_MODE === 'true' || false;

// ── Axios instances ────────────────────────────────────────────
function makeClient(baseURL: string): AxiosInstance {
  const client = axios.create({ baseURL, timeout: 15000, headers: { 'Content-Type': 'application/json' } });
  // JWT interceptor
  client.interceptors.request.use((config) => {
    // FIX (مراجعة): useAuth يكتب التوكن/المستأجِر في sessionStorage، فكانت قراءة
    // localStorage هنا تُرجِع فارغاً ⇒ كلّ طلبات kongApi غير مُصادَقة. نقرأ من
    // sessionStorage حيث يُكتَب فعلاً (مصدر الحقيقة في useAuth.ts).
    const token = sessionStorage.getItem('sahool_access_token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
    const tenant = sessionStorage.getItem('sahool_tenant_id') || 'default';
    config.headers['X-Tenant-ID'] = tenant;
    return config;
  });
  // 401 → logout
  client.interceptors.response.use(
    (r) => r,
    (err) => {
      if (err.response?.status === 401) {
        sessionStorage.removeItem('sahool_access_token');
        window.dispatchEvent(new CustomEvent('sahool:auth:unauthorized'));
      }
      return Promise.reject(err);
    }
  );
  return client;
}

export const kongApi       = makeClient(KONG_URL);
export const weatherApi    = makeClient(WEATHER_URL);
export const soilApi       = makeClient(SOIL_URL);
export const indicatorsApi = makeClient(INDICATORS_URL);
export const vegetationApi = makeClient(VEGETATION_URL);
export const rasterApi     = makeClient(RASTER_URL);
export const authApi       = makeClient(AUTH_URL);

// ── Helper: real data, with mock ONLY in explicit MOCK_MODE ───────
// H2 FIX: لا يجوز لمنصّة قرار زراعي أن تُلفّق توصيات تسميد/ريّ ثابتة عند فشل
// الخادم (انقطاع/مهلة) وتعرضها كأنّها حقيقيّة — ضرر زراعي ومالي حقيقي. الآن
// الـmock يقتصر على وضع التجريب الصريح (VITE_MOCK_MODE)، وأخطاء الإنتاج
// تُرمى ليتعامل معها الـUI (حالة خطأ/بيانات قديمة) بدل قيمة مخترعة صامتة.
async function tryReal<T>(fn: () => Promise<T>, fallback: () => T): Promise<T> {
  if (MOCK_MODE) return fallback();
  return fn();
}

// ══════════════════════════════════════════════════════════════════
// AUTH
// ══════════════════════════════════════════════════════════════════
export interface LoginPayload { username: string; password: string; }
export interface AuthResponse { access_token: string; refresh_token: string; tenant_id?: string; role?: string; user: { username: string; role: string; tenant_id?: string; email?: string; full_name?: string } }

export const login = (payload: LoginPayload): Promise<AuthResponse> =>
  // أمان (P0-2): المصادقة لا تسقط على fallback وهمي. الفشل يظهر بوضوح
  // بدل منح admin زائف. وضع التجريب فقط عبر MOCK_MODE الصريح، وبدور farmer.
  MOCK_MODE
    ? Promise.resolve({ access_token:'demo_token', refresh_token:'demo_refresh', user:{ username:payload.username, role:'farmer' } } as AuthResponse)
    : authApi.post<AuthResponse>('/auth/login', payload).then(r => r.data);

export const logout = () =>
  tryReal(() => authApi.post('/auth/logout').then(r => r.data), () => ({ status:'ok' }));

// ══════════════════════════════════════════════════════════════════
// SAHOOL-PLATFORM (core) — وحدات قرار حيّة عبر البوابة الموحّدة (kong)
// ربط حقيقيّ: لا fallback وهميّ (قرارات زراعيّة — الخطأ يُعلَن للـUI).
// ══════════════════════════════════════════════════════════════════
export interface WaterSampleInput {
  sample_id: string;
  source?: string;
  na?: number | null; ca?: number | null; mg?: number | null;
  hco3?: number | null; co3?: number | null; cl?: number | null;
  ec_dsm?: number | null; ph?: number | null;
  sampled_at?: string | null;
}
export interface WaterClass {
  class: string | null;
  restriction_ar?: string;
  hazard_ar?: string;
  note_ar?: string;
}
export interface WaterAnalysisResult {
  sample_id: string;
  source: string;
  indices: { sar: number | null; rsc_meq_l: number | null; ec_dsm: number | null; ph: number | null };
  classification: {
    salinity: WaterClass;
    alkalinity_rsc: WaterClass;
    sodicity_sar: WaterClass;
  };
  hazard_flags_ar: string[];
  suitable_ar: string;
  missing_inputs: string[];
  data_complete: boolean;
}
export const analyzeWaterSample = (payload: WaterSampleInput): Promise<WaterAnalysisResult> =>
  kongApi.post<WaterAnalysisResult>('/api/v1/irrigation/water-analysis', payload).then(r => r.data);

export interface PestEscalationInput {
  workflow_id: string;
  field_id?: string;
  pest_type?: string;
  severity?: number;
  approval_status?: string; // للاستئناف بعد التعليق: approved/rejected
}
export interface WorkflowTrace {
  workflow_id: string;
  status: string; // running|suspended|completed|failed|compensated
  completed_steps: string[];
  compensated_steps: string[];
  current_step: string | null;
  steps_done: number;
  error: string | null;
}
export interface PestEscalationResult {
  workflow: WorkflowTrace;
  context: Record<string, unknown>;
  step_results: Record<string, Record<string, unknown>>;
}
export const runPestEscalation = (payload: PestEscalationInput): Promise<PestEscalationResult> =>
  kongApi.post<PestEscalationResult>('/api/v1/pest-escalation/run', payload).then(r => r.data);

export interface FieldRecommendationInput {
  field_id: string;
  farm_id?: string;
  crop: string;
  current_indicators?: Record<string, unknown>;
  growth_stage?: string;
  district_id?: string;
}
export interface RecommendationResult {
  delivered: boolean;
  rec_id?: string;
  // مخرجات المحرّك الحقيقيّ: {status, headline, quality_grade, confidence, ...}
  recommendation?: Record<string, unknown>;
  cross_reference_count?: number;
  cross_reference_note_ar?: string;
  model_versions_count?: number;
  timestamp?: string;
  reason_ar?: string; // عند delivered=false (محجوب/مرفوض)
}
// نقبل فقط الحالات المقصودة: 200 (مُسلَّمة) و422/403 (محجوب/مرفوض ⇒ reason_ar).
// نترك 401 تُرفض ليعمل interceptor تسجيل الخروج، و400/500 تُعامَل كأخطاء فعليّة.
export const getFieldRecommendation = (
  payload: FieldRecommendationInput,
): Promise<RecommendationResult> =>
  kongApi
    .post<RecommendationResult>('/api/v1/recommendations/for-field', payload, {
      validateStatus: (s) => s === 200 || s === 422 || s === 403,
    })
    .then(r => r.data);

// TTS — تحويل نصّ عربيّ إلى صوت (صوت يمنيّ). يُرجِع MP3 كـBlob للتشغيل في المتصفّح.
// قيمة للأمّيّين/ضعاف البصر: قراءة التوصيات/التنبيهات صوتيّاً.
export const synthesizeSpeech = (text: string, voice?: string): Promise<Blob> =>
  kongApi
    .post('/tts/synthesize', { text, ...(voice ? { voice } : {}) }, { responseType: 'blob' })
    .then(r => r.data as Blob);

// المايسترو — التحليل الموحّد لحقل (operational truths + قرار السياسة + تنبيهات).
export interface FieldIntelInput {
  field_id: string;
  lat?: number;
  lon?: number;
  crop?: string;
}
export interface FieldIntelResult {
  field_id: string;
  generated_at?: string;
  operational_truths?: Record<string, unknown>;
  confidence?: string; // high | medium | low | none — نصّ من المحرّك (لا رقم)
  confidence_reason?: string;
  contradictions?: unknown[];
  missing_signals?: unknown[];
  policy_decision?: Record<string, unknown>;
  governance?: Record<string, unknown>;
  alerts?: Record<string, unknown>[];
  alerts_summary?: Record<string, unknown>;
  simulation?: Record<string, unknown>;
  provenance?: unknown[]; // قائمة لقطات المصدريّة (list لا object)
  correlation_id?: string;
  [k: string]: unknown;
}
export const analyzeFieldIntelligence = (input: FieldIntelInput): Promise<FieldIntelResult> =>
  kongApi
    .post<FieldIntelResult>('/api/v1/field-intelligence/analyze', null, {
      params: {
        field_id: input.field_id,
        ...(input.lat != null ? { lat: input.lat } : {}),
        ...(input.lon != null ? { lon: input.lon } : {}),
        ...(input.crop ? { crop: input.crop } : {}),
      },
    })
    .then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// ANALYTICS — تحليلات التكلفة (حيّة، مُقيَّدة بالدور analytics:view وبالمستأجِر)
// ربط حقيقيّ عبر البوابة (kong). لا fallback وهميّ — أرقام مالية، الخطأ يُعلَن
// للـUI (حالة خطأ/فراغ). 503 يُرمى عند تعطيل قاعدة البيانات على الخادم.
// ══════════════════════════════════════════════════════════════════
export interface CostBySource {
  source:    string;
  total_usd: number;
}
export interface CostAnalytics {
  by_source:  CostBySource[];
  total_usd:  number;
  task_count: number;
}
export const getCostAnalytics = (): Promise<CostAnalytics> =>
  kongApi.get<CostAnalytics>('/api/v1/analytics/costs').then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// INVENTORY — مخزون المدخلات (حيّ، مُقيَّد بالدور inventory:view/manage وبالمستأجِر)
// ربط حقيقيّ عبر البوابة (kong). لا fallback وهميّ — كميّات/مخزون حقيقيّة، الخطأ
// يُعلَن للـUI (حالة خطأ/فراغ). 503 يُرمى عند تعطيل قاعدة البيانات على الخادم.
// ══════════════════════════════════════════════════════════════════
export interface InventoryItem {
  item_id:        string;
  category:       string;
  name:           string;
  unit:           string | null;
  reorder_level:  number | null;
  total_quantity: number;
  low_stock:      boolean;
}
export interface ExpiringBatch {
  batch_id:    string;
  item_id:     string;
  name:        string;
  quantity:    number;
  unit:        string | null;
  expiry_date: string;
}
export interface NewInventoryItem {
  category:       string;
  name:           string;
  unit?:          string;
  reorder_level?: number;
  notes?:         string;
}
export interface NewInventoryBatch {
  quantity:     number;
  unit?:        string;
  batch_code?:  string;
  expiry_date?: string;
  received_at?: string;
  supplier?:    string;
  notes?:       string;
}

export const getInventoryItems = (): Promise<InventoryItem[]> =>
  kongApi.get<InventoryItem[]>('/api/v1/inventory/items').then(r => r.data);

export const getExpiringBatches = (days = 30): Promise<ExpiringBatch[]> =>
  kongApi.get<ExpiringBatch[]>('/api/v1/inventory/expiring', { params: { days } }).then(r => r.data);

export const createInventoryItem = (payload: NewInventoryItem): Promise<InventoryItem> =>
  kongApi.post<InventoryItem>('/api/v1/inventory/items', payload).then(r => r.data);

export const addInventoryBatch = (itemId: string, payload: NewInventoryBatch): Promise<unknown> =>
  kongApi.post(`/api/v1/inventory/items/${itemId}/batches`, payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// EQUIPMENT — إدارة المعدّات وسجلّ الصيانة (حيّ، مُقيَّد بالدور والمستأجِر)
// ربط حقيقيّ عبر البوابة (kong). لا fallback وهميّ — حالة المعدّة وتكلفة
// الصيانة قرارات تشغيليّة/ماليّة، الخطأ يُعلَن للـUI. 503 عند تعطيل DB.
// ══════════════════════════════════════════════════════════════════
export type EquipmentType   = 'tractor' | 'pump' | 'harvester' | 'sprayer' | 'other';
export type MaintenanceKind = 'scheduled' | 'repair' | 'breakdown' | 'inspection';

export interface Equipment {
  equipment_id:    string;
  name:            string;
  type:            EquipmentType | string;
  status:          string; // active | broken | maintenance | … (من الخادم)
  operating_hours: number;
  purchase_date:   string | null;
}

export interface EquipmentCreateInput {
  name:             string;
  type:             EquipmentType;
  operating_hours?: number;
  purchase_date?:   string;
  notes?:           string;
}

export interface MaintenanceRecord {
  maintenance_id:  string;
  kind:            MaintenanceKind | string;
  status:          string | null;
  scheduled_date:  string | null;
  performed_date:  string | null;
  cost_usd:        number | null;
  notes:           string | null;
}

export interface MaintenanceCreateInput {
  kind:            MaintenanceKind;
  status?:         string;
  scheduled_date?: string;
  performed_date?: string;
  cost_usd?:       number;
  notes?:          string;
}

export const fetchEquipment = (): Promise<Equipment[]> =>
  kongApi.get<Equipment[]>('/api/v1/equipment').then(r => r.data);

export const createEquipment = (payload: EquipmentCreateInput): Promise<Equipment> =>
  kongApi.post<Equipment>('/api/v1/equipment', payload).then(r => r.data);

export const fetchMaintenance = (equipmentId: string): Promise<MaintenanceRecord[]> =>
  kongApi.get<MaintenanceRecord[]>(`/api/v1/equipment/${equipmentId}/maintenance`).then(r => r.data);

// تسجيل صيانة. kind=breakdown يقلب حالة المعدّة إلى broken خادميّاً.
export const logMaintenance = (
  equipmentId: string,
  payload: MaintenanceCreateInput,
): Promise<MaintenanceRecord> =>
  kongApi.post<MaintenanceRecord>(`/api/v1/equipment/${equipmentId}/maintenance`, payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// IoT DEVICES — أجهزة استشعار حيّة عبر البوابة (kong). ربط حقيقيّ بلا تلفيق:
// عند الخطأ (503 DB مُعطَّلة / 403 RBAC / انقطاع) يُرمى ليعرض الـUI حالة صادقة.
// device:view للقراءة، device:manage للتسجيل، observation:record لرفع قياس.
// ══════════════════════════════════════════════════════════════════
export type DeviceType =
  | 'soil_moisture' | 'weather_station' | 'water_meter'
  | 'camera' | 'actuator' | 'other';

export interface Device {
  device_id:         string;
  name:              string;
  type:              DeviceType;
  field_id:          string | null;
  status:            string;
  online:            boolean; // مُحتسَب خادميّاً (من last_seen_at)
  last_seen_at:      string | null;
  firmware_version:  string | null;
}

export interface DeviceRegisterInput {
  name:              string;
  type:              DeviceType;
  field_id?:         string;
  firmware_version?: string;
}

export interface TelemetryPoint {
  sensor_type: string;
  value:       number;
  unit:        string | null;
  recorded_at: string;
}

export interface TelemetryRecordInput {
  sensor_type: string;
  value:       number;
  unit?:       string;
  recorded_at?:string;
}

/** قائمة الأجهزة (device:view). online مُحتسَب على الخادم. */
export const listDevices = (): Promise<Device[]> =>
  kongApi.get<Device[]>('/api/v1/devices').then(r => r.data);

/** تسجيل جهاز جديد (device:manage). */
export const registerDevice = (payload: DeviceRegisterInput): Promise<Device> =>
  kongApi.post<Device>('/api/v1/devices', payload).then(r => r.data);

/** قياسات حديثة لجهاز (device:view). */
export const getDeviceTelemetry = (deviceId: string, limit = 20): Promise<TelemetryPoint[]> =>
  kongApi.get<TelemetryPoint[]>(`/api/v1/devices/${deviceId}/telemetry`, { params: { limit } }).then(r => r.data);

/** رفع قياس لجهاز (observation:record). */
export const recordTelemetry = (deviceId: string, payload: TelemetryRecordInput): Promise<TelemetryPoint> =>
  kongApi.post<TelemetryPoint>(`/api/v1/devices/${deviceId}/telemetry`, payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// IRRIGATION OPS — صمّامات الريّ + جداول الريّ المُخزَّنة (حيّة عبر البوابة)
// مُقيَّدة بالدور irrigation:view / irrigation:manage. 503 عند تعطيل قاعدة
// البيانات على الخادم. ربط حقيقيّ — لا fallback وهميّ (تشغيل ريّ فعليّ).
// ملاحظة: state يسجّل النيّة فقط؛ التشغيل الفيزيائيّ يمرّ عبر HIL (موافقة بشريّة).
// ══════════════════════════════════════════════════════════════════
export type ValveStatus = 'open' | 'closed' | 'unknown';
export type ValveStateIntent = 'open' | 'closed';
export type ValveType = 'solenoid' | 'manual' | 'drip_header' | 'gate';

export interface Valve {
  valve_id:        string;
  name:            string;
  field_id?:       string | null;
  device_id?:      string | null;
  valve_type?:     ValveType | string | null;
  status:          ValveStatus;
  flow_rate_lpm?:  number | null;
  last_changed_at?: string | null;
}
export interface CreateValveInput {
  name:           string;
  field_id?:      string;
  device_id?:     string;
  valve_type?:    ValveType;
  flow_rate_lpm?: number;
}
export interface IrrigationSchedule {
  schedule_id:     string;
  field_id?:       string | null;
  valve_id?:       string | null;
  name:            string;
  start_time:      string; // 'HH:MM'
  duration_min:    number;
  days_of_week?:   number[] | null; // 0..6
  water_target_mm?: number | null;
  enabled:         boolean;
  last_run_at?:    string | null;
}
export interface CreateScheduleInput {
  name:            string;
  field_id?:       string;
  valve_id?:       string;
  start_time:      string; // 'HH:MM'
  duration_min:    number;
  days_of_week?:   number[];
  water_target_mm?: number;
  enabled?:        boolean;
}

export const listValves = (): Promise<Valve[]> =>
  kongApi.get<Valve[]>('/api/v1/irrigation/valves').then(r => r.data);

export const createValve = (payload: CreateValveInput): Promise<Valve> =>
  kongApi.post<Valve>('/api/v1/irrigation/valves', payload).then(r => r.data);

export const setValveState = (valveId: string, status: ValveStateIntent): Promise<Valve> =>
  kongApi.post<Valve>(`/api/v1/irrigation/valves/${valveId}/state`, { status }).then(r => r.data);

export const listSchedules = (fieldId?: string): Promise<IrrigationSchedule[]> =>
  kongApi.get<IrrigationSchedule[]>('/api/v1/irrigation/schedules', {
    params: fieldId ? { field_id: fieldId } : {},
  }).then(r => r.data);

export const createSchedule = (payload: CreateScheduleInput): Promise<IrrigationSchedule> =>
  kongApi.post<IrrigationSchedule>('/api/v1/irrigation/schedules', payload).then(r => r.data);

export const deleteSchedule = (scheduleId: string): Promise<void> =>
  kongApi.delete(`/api/v1/irrigation/schedules/${scheduleId}`).then(() => undefined);

// ══════════════════════════════════════════════════════════════════
// MASTER DATA — كتالوج البيانات المرجعيّة (محصول/تربة/سماد/مبيد/صنف/معدّة)
// ربط حقيقيّ عبر البوابة (kong). لا fallback وهميّ — بيانات مرجعيّة تُبنى عليها
// قرارات، فالخطأ يُعلَن للـUI. 503 عند تعطيل قاعدة البيانات، 409 عند التكرار
// (tenant,category,code). مُقيَّد بالدور master_data:view / master_data:manage.
// ══════════════════════════════════════════════════════════════════
export type MasterDataCategory =
  | 'crop' | 'soil_type' | 'fertilizer' | 'pesticide'
  | 'seed_variety' | 'equipment_type' | 'other';

export interface MasterDataEntry {
  md_id:    string;
  category: MasterDataCategory;
  code:     string;
  name_ar:  string;
  name_en?: string;
  metadata?: Record<string, unknown>;
}

export interface MasterDataCreateInput {
  category:  MasterDataCategory;
  code:      string;
  name_ar:   string;
  name_en?:  string;
  metadata?: Record<string, unknown>;
}

export const fetchMasterData = (category: MasterDataCategory): Promise<MasterDataEntry[]> =>
  kongApi.get<MasterDataEntry[]>('/api/v1/master-data', { params: { category } }).then(r => r.data);

export const createMasterDataEntry = (payload: MasterDataCreateInput): Promise<MasterDataEntry> =>
  kongApi.post<MasterDataEntry>('/api/v1/master-data', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// DOCUMENTS — سجلّ الوثائق (عقود/تقارير/صور/خرائط/نتائج مخبريّة)
// سجلّ بيانات وصفيّة فقط: الملفّ الفعليّ في تخزين الكائنات، وstorage_ref مسار/رابط.
// ربط حيّ عبر البوابة (kong)، مُقيَّد بالدور (document:view / document:manage)
// وبالمستأجِر. لا fallback وهميّ — 503 يُرمى عند تعطيل قاعدة البيانات.
// ══════════════════════════════════════════════════════════════════
export type DocumentCategory = 'contract' | 'report' | 'image' | 'map' | 'lab_result' | 'other';

export interface DocumentRecord {
  doc_id:       string;
  category:     DocumentCategory;
  title:        string;
  storage_ref:  string | null;
  content_type: string | null;
  size_bytes:   number | null;
  version:      number;
  field_id:     string | null;
  created_at:   string;
}

export interface DocumentCreateInput {
  category:      DocumentCategory;
  title:         string;
  storage_ref?:  string;
  content_type?: string;
  size_bytes?:   number;
  field_id?:     string;
}

export const listDocuments = (
  filters?: { category?: DocumentCategory; field_id?: string },
): Promise<DocumentRecord[]> =>
  kongApi.get<DocumentRecord[]>('/api/v1/documents', {
    params: {
      ...(filters?.category ? { category: filters.category } : {}),
      ...(filters?.field_id ? { field_id: filters.field_id } : {}),
    },
  }).then(r => r.data);

export const getDocument = (docId: string): Promise<DocumentRecord> =>
  kongApi.get<DocumentRecord>(`/api/v1/documents/${docId}`).then(r => r.data);

export const createDocument = (payload: DocumentCreateInput): Promise<DocumentRecord> =>
  kongApi.post<DocumentRecord>('/api/v1/documents', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// GOVERNANCE & AUDIT — أصل/أحداث/أوامر كيان + مفاتيح المشاركة (حيّ عبر البوابة)
// قراءة-غالباً + إنشاء مفتاح. كلّها DB-backed عبر tenant_connection (RLS مُطبَّق)؛
// عند تعطيل قاعدة البيانات يُرمى 503 ليعرض الـUI حالة صادقة. لا بيانات مُلفَّقة —
// التتبّع/التدقيق سجلّ حقيقيّ أو لا شيء. مفتاح المشاركة يُعرَض نصّاً مرّة واحدة فقط.
// ══════════════════════════════════════════════════════════════════
export interface LineageEntry {
  timestamp:   string;
  source_type: string;
  source_id:   string | null;
  action:      string | null;
  summary_ar:  string | null;
}
export interface EntityLineage {
  entity_type:    string;
  entity_id:      string;
  total_entries:  number;
  earliest_at:    string | null;
  latest_at:      string | null;
  commands_count: number;
  events_count:   number;
  entries:        LineageEntry[];
}
export interface SharingKey {
  key_id:      string;
  key_prefix?: string;
  scope?:      string;
  created_by?: string;
  expires_at?: string | null;
  revoked?:    boolean;
  [k: string]: unknown; // الخادم قد يُرجِع حقولاً إضافيّة — لا نقصّها
}
export interface NewSharingKey {
  scope?:            'read' | 'write' | string;
  valid_days?:       number;
  third_party_name?: string;
  third_party_type?: string;
  allowed_field_ids?: string[];
}
export interface SharingKeyCreated {
  key_id:        string;
  key_plaintext: string; // مرّة واحدة فقط — لا يُعاد عرضه
  key_prefix:    string;
  scope:         string;
  expires_at:    string | null;
}

/** أصل (lineage) كامل لكيان (command+event+lifecycle+journal+trueup). */
export const getEntityLineage = (
  entityType: string,
  entityId: string,
  limit = 500,
): Promise<EntityLineage> =>
  kongApi.get<EntityLineage>(
    `/api/v1/lineage/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
    { params: { limit } },
  ).then(r => r.data);

/** تاريخ أحداث كيان من ناقل الأحداث. */
export const getEntityEvents = (
  entityType: string,
  entityId: string,
  limit = 100,
): Promise<{ events: unknown[] }> =>
  kongApi.get<{ events: unknown[] }>(
    `/api/v1/events/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
    { params: { limit } },
  ).then(r => r.data);

/** البحث عن أمر بالمعرّف (404 عند عدم الوجود). */
export const getCommand = (commandId: string): Promise<{ command_id: string; found: boolean }> =>
  kongApi.get<{ command_id: string; found: boolean }>(
    `/api/v1/commands/${encodeURIComponent(commandId)}`,
  ).then(r => r.data);

/** سرد مفاتيح المشاركة للمستأجِر. */
export const listSharingKeys = (includeRevoked = false): Promise<{ keys: SharingKey[] }> =>
  kongApi.get<{ keys: SharingKey[] }>('/api/v1/sharing/keys', {
    params: { include_revoked: includeRevoked },
  }).then(r => r.data);

/** إنشاء مفتاح مشاركة (يتطلّب صلاحيّة دعوة المستخدم). النصّ يُعرَض مرّة واحدة. */
export const createSharingKey = (payload: NewSharingKey): Promise<SharingKeyCreated> =>
  kongApi.post<SharingKeyCreated>('/api/v1/sharing/keys', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// INDICATORS SERVICE — 33 مؤشر + WOFOST
// ══════════════════════════════════════════════════════════════════

/** لوحة KPI الرئيسية */
export const fetchDashboard = () =>
  tryReal(
    () => indicatorsApi.get('/indicators/dashboard').then(r => r.data),
    () => MOCK_DASHBOARD
  );

/** جميع مؤشرات حقل محدد */
export const fetchFieldIndicators = (fieldId: string) =>
  tryReal(
    () => indicatorsApi.get(`/v1/indicators/${fieldId}`).then(r => r.data),
    () => mockFieldIndicators(fieldId)
  );

/** مؤشر واحد مع تاريخه */
export const fetchSingleIndicator = (fieldId: string, indicatorId: string, days = 30) =>
  tryReal(
    () => indicatorsApi.get(`/v1/indicators/${fieldId}/${indicatorId}`, { params:{ days } }).then(r => r.data),
    () => ({ field_id:fieldId, indicator_id:indicatorId, value:0.62, status:'good', trend:[] })
  );

/** كتالوج 33 مؤشر */
export const fetchIndicatorCatalog = () =>
  tryReal(
    () => indicatorsApi.get('/indicators/catalog').then(r => r.data),
    () => ({ total:33, categories:{} })
  );

/** تنبيهات */
export const fetchAlerts = (severity?: string) =>
  tryReal(
    () => indicatorsApi.get('/indicators/alerts', { params:{ severity } }).then(r => r.data),
    () => ({ total_alerts:3, alerts:MOCK_ALERTS })
  );

/** حالة NATS */
export const fetchNatsStatus = () =>
  tryReal(
    () => indicatorsApi.get('/indicators/nats/status').then(r => r.data),
    () => ({ nats_connected:false, events_processed:0 })
  );

/** Probes */
export const fetchIndicatorsHealth = () =>
  indicatorsApi.get('/health').then(r => r.data).catch(() => ({ status:'unavailable' }));

// ══════════════════════════════════════════════════════════════════
// VEGETATION SERVICE
// ══════════════════════════════════════════════════════════════════

/** تحليل صورة + 7 مؤشرات + نشر NATS */
export const analyzeVegetation = (fieldId: string, satellite = 'sentinel-2', tenantId = 'default') =>
  tryReal(
    () => vegetationApi.post('/v1/analyze', { field_id:fieldId, satellite, tenant_id:tenantId }).then(r => r.data),
    () => mockVegetationAnalysis(fieldId)
  );

/** سلسلة زمنية NDVI */
export const fetchVegetationTimeseries = (fieldId: string, days = 30) =>
  tryReal(
    () => vegetationApi.get(`/vegetation/field/${fieldId}/timeseries`, { params:{ days } }).then(r => r.data),
    () => mockTimeseries(fieldId, days)
  );

/** شذوذات */
export const fetchVegetationAnomalies = (fieldId: string, threshold = 1.5) =>
  tryReal(
    () => vegetationApi.get('/vegetation/anomalies', { params:{ field_id:fieldId, threshold } }).then(r => r.data),
    () => ({ field_id:fieldId, total_anomalies:2, anomalies:[] })
  );

/** NDVI الحالي */
export const fetchCurrentNDVI = (fieldId: string) =>
  tryReal(
    () => vegetationApi.get(`/vegetation/field/${fieldId}/current-ndvi`).then(r => r.data),
    () => ({ field_id:fieldId, ndvi:{ current:0.62 }, classification:{ level:'good', label_ar:'جيد', color:'#65a30d' } })
  );

// ══════════════════════════════════════════════════════════════════
// WEATHER SERVICE
// ══════════════════════════════════════════════════════════════════

export const fetchCurrentWeather = (lat = 15.05, lon = 45.55) =>
  tryReal(
    () => weatherApi.get('/weather/current', { params:{ lat, lon } }).then(r => r.data),
    () => ({ current: MOCK_WEATHER_TODAY, location:{ lat, lon, region:'البيضاء، اليمن' } })
  );

export const fetchWeatherForecast = (days = 7, lat = 15.05, lon = 45.55) =>
  tryReal(
    () => weatherApi.get('/weather/forecast', { params:{ days, lat, lon } }).then(r => r.data),
    () => ({ forecast:mockWeatherDays(days), days, summary:{ total_gdd:85, total_et0_mm:31, avg_tmax_c:31 } })
  );

export const fetchWeatherHistorical = (days = 30, lat = 15.05, lon = 45.55) =>
  tryReal(
    () => weatherApi.get('/weather/historical', { params:{ days, lat, lon } }).then(r => r.data),
    () => ({ period_days:days, data:mockWeatherDays(days), summary:{ total_gdd:300, water_deficit_mm:45, total_et0_mm:130, total_rainfall_mm:85 } })
  );

export const fetchWofostFormat = (days = 30, lat = 15.05, lon = 45.55) =>
  tryReal(
    () => weatherApi.get('/weather/wofost_format', { params:{ days, lat, lon } }).then(r => r.data),
    () => ({ wofost_input:mockWeatherDays(days).map(d => ({ date:d.date, tmax:d.tmax, tmin:d.tmin, radiation_mj:18, et0:d.et0, precipitation:d.rain, soil_moisture_pct:35 })), total_days:days })
  );

export const fetchAgroIndicators = (days = 30) =>
  tryReal(
    () => weatherApi.get('/weather/agro-indicators', { params:{ days } }).then(r => r.data),
    () => ({ gdd_accumulated:305, et0_accumulated_mm:132, rainfall_accumulated_mm:87, water_deficit_mm:45, drought_stress_days:5 })
  );

// ══════════════════════════════════════════════════════════════════
// SOIL SERVICE
// ══════════════════════════════════════════════════════════════════

export const fetchSoilData = (fieldId: string) =>
  tryReal(
    () => soilApi.get(`/soil/${fieldId}`).then(r => r.data),
    () => mockSoilData(fieldId)
  );

export const fetchAllSoilData = () =>
  tryReal(
    () => soilApi.get('/soil/all').then(r => r.data),
    () => ({ readings:MOCK_FIELDS.map(f => mockSoilData(f.field_id)), total:8 })
  );

export const fetchSoilWofostParams = (fieldId: string) =>
  tryReal(
    () => soilApi.get(`/soil/wofost_params/${fieldId}`).then(r => r.data),
    () => ({ rdmsol:1.2, soil_water_capacity_mm:150, wilting_point_pct:15, field_capacity_pct:35, suitable_for_wofost:true })
  );

export const fetchNitrogenRecommendation = (fieldId: string, targetYield = 5.0) =>
  tryReal(
    () => soilApi.get('/soil/nitrogen/recommendation', { params:{ field_id:fieldId, target_yield_t_ha:targetYield } }).then(r => r.data),
    () => ({ recommended_n_kg_ha:87.5, n_demand_kg_ha:125, n_available_kg_ha:37.5, method:'FAO adjusted', timing:'40% زراعة + 30% تفريع + 30% تطاول' })
  );

export const fetchSoilRecommendations = (fieldId: string) =>
  tryReal(
    () => soilApi.get(`/soil/${fieldId}/recommendations`).then(r => r.data),
    () => ({ recommendations:['✅ التربة في حالة جيدة — استمر بنفس الإدارة'], priority:'روتيني' })
  );

export const postSoilReading = (data: { field_id:string; ph?:number; moisture_pct?:number; nitrogen_mg_kg?:number }) =>
  tryReal(
    () => soilApi.post('/soil/reading', data).then(r => r.data),
    () => ({ status:'received', nats_published:false })
  );

// ══════════════════════════════════════════════════════════════════
// PROBES — فحص صحة كل الخدمات
// ══════════════════════════════════════════════════════════════════
export const checkAllServices = async () => {
  const checks = await Promise.allSettled([
    indicatorsApi.get('/health').then(r => ({ name:'indicators', ...r.data })),
    vegetationApi.get('/health').then(r => ({ name:'vegetation',  ...r.data })),
    weatherApi.get('/health').then(r    => ({ name:'weather',     ...r.data })),
    soilApi.get('/health').then(r       => ({ name:'soil',        ...r.data })),
    kongApi.get('/').then(r             => ({ name:'kong',         status:'ok' })),
  ]);
  return checks.map((r, i) =>
    r.status === 'fulfilled'
      ? r.value
      : { name:['indicators','vegetation','weather','soil','kong'][i], status:'unavailable' }
  );
};

// ══════════════════════════════════════════════════════════════════
// MOCK DATA
// ══════════════════════════════════════════════════════════════════
export const MOCK_FIELDS = [
  { field_id:'field_01', name:'حقل وادي سبأ',        area:23.5, crop:'قمح صلب',   ndvi:0.72, stage:'ملء الحبوب', gdd:960,  yield:2.8 },
  { field_id:'field_02', name:'حقل البيضاء الشمالي', area:32.0, crop:'شعير',       ndvi:0.58, stage:'نمو خضري',  gdd:825,  yield:2.5 },
  { field_id:'field_03', name:'حقل البيضاء الجنوبي', area:18.7, crop:'ذرة صفراء',  ndvi:0.44, stage:'تزهير',     gdd:980,  yield:3.9 },
  { field_id:'field_04', name:'حقل رداع الغربي',     area:41.3, crop:'طماطم',      ndvi:0.66, stage:'ثمرة',      gdd:780,  yield:4.2 },
  { field_id:'field_05', name:'حقل ذي السفال',       area:28.9, crop:'قمح صلب',   ndvi:0.74, stage:'ملء الحبوب', gdd:1020, yield:3.1 },
  { field_id:'field_06', name:'حقل عتمة الشرقي',    area:37.5, crop:'شعير',       ndvi:0.51, stage:'نمو خضري',  gdd:792,  yield:2.4 },
  { field_id:'field_07', name:'حقل الرياشية',        area:22.1, crop:'خضروات',     ndvi:0.55, stage:'حصاد',      gdd:660,  yield:5.5 },
  { field_id:'field_08', name:'حقل ذي ناعم',         area:45.0, crop:'بطاطس',      ndvi:0.61, stage:'درنات',     gdd:680,  yield:6.8 },
];

const MOCK_ALERTS = [
  { id:'a1', field_id:'field_06', field_name:'حقل عتمة الشرقي', level:'critical', severity:'critical', message:'NDVI حرج — إجهاد مائي', color:'#dc2626', recommendation:'ري فوري', timestamp:new Date().toISOString() },
  { id:'a2', field_id:'field_03', field_name:'حقل البيضاء الجنوبي', level:'warning', severity:'warning', message:'رطوبة تربة منخفضة', color:'#f59e0b', recommendation:'تقليل ET0', timestamp:new Date().toISOString() },
  { id:'a3', field_id:'field_01', field_name:'حقل وادي سبأ', level:'info', severity:'info', message:'موعد التسميد البوتاسي', color:'#38bdf8', recommendation:'إضافة K2O', timestamp:new Date().toISOString() },
];

const MOCK_WEATHER_TODAY = { tmax:31, tmin:17, tmean:24, humidity_pct:52, rainfall_mm:0, et0_mm:4.2, et0:4.2, gdd:14, wind_speed_kmh:12, irrigation_needed:true, heat_stress:false };

function mockWeatherDays(n: number) {
  return Array.from({length:n},(_,i) => {
    const d = new Date(); d.setDate(d.getDate()-n+i+1);
    return { date:d.toISOString().split('T')[0], tmax:28+Math.random()*6, tmin:14+Math.random()*5, tmean:21+Math.random()*4, rain:+(Math.random()*3).toFixed(2), et0:+(3.5+Math.random()*2).toFixed(2), gdd:+(8+Math.random()*8).toFixed(1), rainfall_mm:+(Math.random()*3).toFixed(2) };
  });
}

function mockSoilData(fieldId: string) {
  const s = Math.abs(fieldId.split('').reduce((a,c) => a+c.charCodeAt(0),0)) % 100;
  return { field_id:fieldId, ph:+(6+s%28/20).toFixed(1), ec_ds_m:+(0.3+s%40/20).toFixed(2), moisture_pct:+(20+s%55).toFixed(1), nitrogen_mg_kg:+(12+s%60).toFixed(1), phosphorus_mg_kg:+(6+s%35).toFixed(1), potassium_mg_kg:+(40+s%120).toFixed(1), organic_matter_pct:+(0.8+s%28/10).toFixed(2), texture:'مزيجية', health:{ status:'good', status_ar:'جيد', color:'#65a30d' } };
}

function mockFieldIndicators(fieldId: string) {
  const s = Math.abs(fieldId.split('').reduce((a,c) => a+c.charCodeAt(0),0)) % 100;
  return {
    field_id:fieldId, total_indicators:33,
    indicators:{
      ndvi:{ value:+(0.35+s%55/100).toFixed(4), unit:'', status:'good', status_ar:'جيد', color:'#65a30d', category:'vegetation' },
      evi: { value:+(0.30+s%45/100).toFixed(4), unit:'', status:'good', status_ar:'جيد', color:'#15803d', category:'vegetation' },
      soil_moisture:{ value:+(20+s%55).toFixed(1), unit:'%', status:'fair', status_ar:'مقبول', color:'#ca8a04', category:'water' },
      soil_ph:{ value:+(6+s%28/20).toFixed(1), unit:'', status:'good', status_ar:'جيد', color:'#92400e', category:'soil' },
      yield_est:{ value:+(2.5+s%40/10).toFixed(2), unit:'t/ha', status:'good', status_ar:'جيد', color:'#a855f7', category:'productivity' },
      temperature:{ value:+(20+s%20).toFixed(1), unit:'°C', status:'good', status_ar:'جيد', color:'#f97316', category:'weather' },
    },
    wofost:{ gdd_accumulated:s*10, progress_pct:s/2, lai:+(2+s%30/10).toFixed(2), yield_t_ha:+(2+s%40/10).toFixed(2), engine:'WOFOST-RUE-v9' },
  };
}

function mockVegetationAnalysis(fieldId: string) {
  return {
    field_id:fieldId, satellite:'sentinel-2', cloud_coverage:5,
    indices:{ ndvi:0.72, evi:0.61, savi:0.45, ndwi:0.18, ndmi:0.22, gndvi:0.68, lai:3.82 },
    classification:{ level:'good', label_ar:'جيد', color:'#65a30d' },
    nats_event:{ published:false, subject:`sahool.tenant.default.satellite.ndvi.computed` },
    analyzed_at:new Date().toISOString(),
  };
}

function mockTimeseries(fieldId: string, days: number) {
  const series = Array.from({length:days},(_,i) => {
    const d = new Date(); d.setDate(d.getDate()-days+i+1);
    return { date:d.toISOString().split('T')[0], ndvi:+(0.45+Math.sin(i/8)*0.15+Math.random()*0.04).toFixed(4), evi:+(0.38+Math.sin(i/8)*0.12+Math.random()*0.03).toFixed(4), lai:+(2+Math.sin(i/8)*1.2+Math.random()*0.3).toFixed(2) };
  });
  return { field_id:fieldId, period_days:days, timeseries:series, data:series, statistics:{ ndvi_mean:0.58, slope:0.001, r_squared:0.72, trend_direction:'stable' } };
}

const MOCK_DASHBOARD = {
  generated_at:new Date().toISOString(),
  total_fields:8, total_indicators:33, active_alerts:2, nats_events_processed:0,
  kpis:[
    { id:'ndvi',    name:'متوسط NDVI',      value:0.623, unit:'',       status:'good',      trend_direction:'improving', category:'vegetation',   sparkline:[0.58,0.60,0.61,0.62,0.63,0.62,0.63], color:'#16a34a' },
    { id:'wue',     name:'كفاءة المياه',    value:2.1,   unit:'kg/m³',  status:'good',      trend_direction:'stable',    category:'water',        sparkline:[1.9,2.0,2.0,2.1,2.1,2.1,2.1],       color:'#0ea5e9' },
    { id:'soil_ph', name:'pH التربة',       value:6.8,   unit:'',       status:'excellent', trend_direction:'stable',    category:'soil',         sparkline:[6.8,6.8,6.9,6.8,6.8,6.9,6.8],       color:'#92400e' },
    { id:'yield_est',name:'توقع الإنتاج',  value:3.6,   unit:'t/ha',   status:'good',      trend_direction:'improving', category:'productivity', sparkline:[3.2,3.3,3.4,3.5,3.5,3.6,3.6],       color:'#a855f7' },
    { id:'stress',  name:'مؤشر الإجهاد',  value:0.18,  unit:'',       status:'good',      trend_direction:'declining', category:'health',       sparkline:[0.22,0.21,0.20,0.19,0.19,0.18,0.18], color:'#f59e0b' },
    { id:'temperature',name:'الحرارة',     value:30.2,  unit:'°C',     status:'fair',      trend_direction:'stable',    category:'weather',      sparkline:[28,29,30,30,31,30,30],               color:'#f97316' },
  ],
  fields_summary:MOCK_FIELDS.map(f => ({
    field_id:f.field_id, field_name:f.name, ndvi:f.ndvi, crop:f.crop,
    composite:+(f.ndvi*0.5+0.3).toFixed(3), color:'#65a30d', status:'جيد',
  })),
  alerts:MOCK_ALERTS,
  data_freshness:{ source:'sentinel2+wofost+iot', last_update:new Date().toISOString() },
  status:'success',
};
