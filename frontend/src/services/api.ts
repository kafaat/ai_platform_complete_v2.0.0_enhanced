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
// عقد auth-service: /auth/login و/auth/register يتوقّعان `email` (لا username).
export interface LoginPayload { email: string; password: string; mfa_code?: string; }
export interface AuthResponse { access_token: string; refresh_token: string; tenant_id?: string; role?: string; user: { username: string; role: string; tenant_id?: string; email?: string; full_name?: string } }

export const login = (payload: LoginPayload): Promise<AuthResponse> =>
  // أمان (P0-2): المصادقة لا تسقط على fallback وهمي. الفشل يظهر بوضوح
  // بدل منح admin زائف. وضع التجريب فقط عبر MOCK_MODE الصريح، وبدور farmer.
  // mfa_code يُرسَل فقط إن وُجد (الخادم يتطلّبه للحسابات المُفعّل لها MFA).
  MOCK_MODE
    ? Promise.resolve({ access_token:'demo_token', refresh_token:'demo_refresh', user:{ username:payload.email, email:payload.email, role:'farmer' } } as AuthResponse)
    : authApi.post<AuthResponse>('/auth/login', {
        email: payload.email,
        password: payload.password,
        ...(payload.mfa_code ? { mfa_code: payload.mfa_code } : {}),
      }).then(r => r.data);

/** يفحص ما إذا كان خطأ تسجيل الدخول يعني "MFA مطلوب" (الخادم يردّ 401 مع
 *  الرأس X-MFA-Required: true حين تصحّ كلمة المرور لكن يلزم رمز TOTP). */
export function isMfaRequiredError(e: any): boolean {
  const status = e?.response?.status;
  const header = e?.response?.headers?.['x-mfa-required'];
  return status === 401 && (header === 'true' || header === true);
}

// يستخرج رسالة خطأ مقروءة من ردّ FastAPI (detail قد يكون نصّاً أو مصفوفة كائنات).
export function apiErrorMessage(e: any, fallback: string): string {
  const d = e?.response?.data?.detail ?? e?.response?.data?.message_ar;
  if (Array.isArray(d)) {
    const msgs = d.map((x: any) => x?.msg || x?.message_ar || '').filter(Boolean);
    return msgs.length ? msgs.join('، ') : fallback;
  }
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object') return d.message_ar || d.msg || fallback;
  return e?.message || fallback;
}

export interface RegisterPayload { full_name: string; email: string; password: string }
// التسجيل: الخلفيّة تُصدر توكناً مباشرةً (تسجيل دخول تلقائيّ). الدور يُثبَّت
// 'farmer' خادم-جانبيّاً (منع تصعيد الصلاحيّات) — لا يُرسَل دور من العميل.
export const register = (payload: RegisterPayload): Promise<AuthResponse> =>
  MOCK_MODE
    ? Promise.resolve({ access_token:'demo_token', refresh_token:'demo_refresh',
        user:{ username:payload.email, email:payload.email, role:'farmer', full_name:payload.full_name } } as AuthResponse)
    : authApi.post('/auth/register', payload).then(r => {
    const d = r.data as { access_token: string; refresh_token?: string; role?: string;
      full_name?: string; tenant_id?: string };
    return {
      access_token: d.access_token,
      refresh_token: d.refresh_token ?? '',
      tenant_id: d.tenant_id,
      role: d.role,
      user: { username: payload.email, email: payload.email, role: d.role ?? 'farmer',
        tenant_id: d.tenant_id, full_name: d.full_name ?? payload.full_name },
    } as AuthResponse;
  });

export const logout = () =>
  tryReal(() => authApi.post('/auth/logout').then(r => r.data), () => ({ status:'ok' }));

// ── Password Reset & MFA & Change-Password ─────────────────────────
// ربط حيّ مع auth-service (لا fallback وهميّ — مسارات أمان حسّاسة). الأشكال
// تطابق services/auth/main.py تماماً. أخطاء FastAPI تُقرأ عبر apiErrorMessage.

/** طلب إعادة تعيين كلمة المرور بالبريد. الخادم يردّ دائماً برسالة موحّدة
 *  (منع تعداد البريد) — حتى لو لم يكن مسجّلاً. */
export const requestPasswordReset = (email: string): Promise<{ message: string }> =>
  authApi.post<{ message: string }>('/auth/password-reset/request', { email }).then(r => r.data);

/** تأكيد إعادة التعيين برمز من البريد + كلمة مرور جديدة. 400 لرمز غير صالح/منتهٍ. */
export const confirmPasswordReset = (
  token: string,
  newPassword: string,
): Promise<{ message: string }> =>
  authApi
    .post<{ message: string }>('/auth/password-reset/confirm', { token, new_password: newPassword })
    .then(r => r.data);

export interface MfaSetupResponse {
  secret: string;            // سرّ base32 — يُعرَض مرّة واحدة فقط
  provisioning_uri: string;  // otpauth://… (لتطبيق المصادقة / QR)
  message: string;
}

/** يبدأ اقتران MFA: يولّد سرّاً ويُعيد provisioning_uri. لا يُفعّل بعد —
 *  التفعيل يتطلّب تأكيد أوّل رمز عبر mfaActivate. (يتطلّب توكناً صالحاً) */
export const mfaSetup = (): Promise<MfaSetupResponse> =>
  authApi.post<MfaSetupResponse>('/auth/mfa/setup').then(r => r.data);

/** يفعّل MFA بعد تأكيد أوّل رمز صحيح من تطبيق المصادقة. */
export const mfaActivate = (code: string): Promise<{ message: string; mfa_enabled: boolean }> =>
  authApi
    .post<{ message: string; mfa_enabled: boolean }>('/auth/mfa/activate', { code })
    .then(r => r.data);

/** يعطّل MFA — يتطلّب رمزاً صحيحاً حاليّاً (لا يُعطّله توكن مسروق بلا الجهاز). */
export const mfaDisable = (code: string): Promise<{ message: string; mfa_enabled: boolean }> =>
  authApi
    .post<{ message: string; mfa_enabled: boolean }>('/auth/mfa/disable', { code })
    .then(r => r.data);

/** تغيير كلمة المرور لمستخدم مُصادَق (يتطلّب الحاليّة + الجديدة). */
export const changePassword = (
  currentPassword: string,
  newPassword: string,
): Promise<{ message: string }> =>
  authApi
    .post<{ message: string }>('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
    .then(r => r.data);

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
// REPORTS — تقارير وتحليلات (حيّة، tenant-scoped + RBAC field:view)
// تجميع من جداول قائمة (مزارع/حقول/مواسم/عمليّات/تنبيهات) عبر COUNT/SUM/GROUP BY.
// لا fallback وهميّ — الخطأ (503 DB / 404 / 403) يُرفع لتعرض الواجهة حالة صادقة.
// ══════════════════════════════════════════════════════════════════
export interface AreaByCrop {
  crop:    string;
  area_ha: number;
}
export interface FarmSummary {
  farms_count:          number;
  fields_count:         number;
  total_area_ha:        number;
  active_seasons_count: number;
  activities_total:     number;
  activities_by_status: Record<string, number>;
  open_alerts_count:    number;
  area_by_crop:         AreaByCrop[];
}
export const getFarmSummary = (): Promise<FarmSummary> =>
  kongApi.get<FarmSummary>('/api/v1/reports/farm-summary').then(r => r.data);

export interface ReportAlert {
  alert_id:   string;
  field_id:   string | null;
  alert_type: string;
  severity:   string;
  title_ar:   string | null;
  message_ar: string | null;
  status:     string;
  created_at: string | null;
}
export interface FieldReportSeason {
  season_id:   string;
  crops:       string[];
  cultivar:    string | null;
  sowing_date: string | null;
  season_end:  string | null;
  status:      string;
}
export interface FieldReportSummary {
  field_id:             string;
  name:                 string;
  area_ha:              number;
  crop:                 string | null;
  soil_type:            string | null;
  current_season:       FieldReportSeason | null;
  activities_total:     number;
  activities_by_type:   Record<string, number>;
  activities_by_status: Record<string, number>;
  recent_alerts:        ReportAlert[];
}
export const getFieldReportSummary = (fieldId: string): Promise<FieldReportSummary> =>
  kongApi.get<FieldReportSummary>(`/api/v1/reports/field/${fieldId}/summary`).then(r => r.data);

export interface SeasonReportSummary {
  season_id:        string;
  field_id:         string;
  crops:            string[];
  cultivar:         string | null;
  irrigation_type:  string | null;
  sowing_date:      string | null;
  season_end:       string | null;
  status:           string;
  stage_count:      number;
  activities_count: number;
}
export const getSeasonReportSummary = (seasonId: string): Promise<SeasonReportSummary> =>
  kongApi.get<SeasonReportSummary>(`/api/v1/reports/season/${seasonId}/summary`).then(r => r.data);

// ── محاكاة الموسم (Crop-model simulation, RUE/FAO-56) — v39 ──────────
// تقديرات نموذجيّة (إنتاج/GDD/LAI/ماء) بنطاق وثقة صريحة — لا أرقام قاطعة.
export interface SeasonSimResult {
  season_id:           string;
  crop:                string;
  crop_recognized:     boolean;
  days_simulated:      number;
  gdd_total:           number;
  gdd_to_maturity:     number;
  maturity_reached:    boolean;
  lai_max:             number;
  biomass_kg_ha:       number;
  yield_kg_ha:         number;
  yield_low_kg_ha:     number;
  yield_high_kg_ha:    number;
  water_need_mm:       number;
  water_supply_mm:     number | null;
  water_stress_factor: number;
  confidence:          number;
  rationale_ar:        string;
  assumptions_ar:      string[];
  warnings_ar:         string[];
  sim_ran_at:          string;
}
// يشغّل محاكاة محصوليّة للموسم ويحفظ ناتجها على الخادم (FIELD_EDIT). 503 عند تعذّر
// الطقس/القاعدة، 404 إن غاب الموسم عن المستأجِر.
export const simulateSeason = (seasonId: string): Promise<SeasonSimResult> =>
  kongApi.post<SeasonSimResult>(`/api/v1/seasons/${seasonId}/simulate`).then(r => r.data);

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
// FIELD ACTIVITIES — العمليّات الزراعيّة لكلّ حقل (sahool-platform v35).
// ربط حيّ بلا تلفيق: field:view للقراءة، field:edit للتسجيل. عند الخطأ
// (503 DB / 404 حقل / 403 RBAC) يُرمى ليعرض الـUI حالة صادقة.
// ══════════════════════════════════════════════════════════════════
export type ActivityType =
  | 'planting' | 'fertilization' | 'irrigation'
  | 'spraying' | 'pruning' | 'harvest' | 'scouting';

export interface Activity {
  activity_id:   string;
  field_id:      string;
  season_id:     string | null;
  activity_type: ActivityType | string;
  title_ar:      string | null;
  details:       Record<string, unknown>;
  scheduled_for: string | null;
  performed_on:  string | null;
  status:        string; // planned | done | skipped (من الخادم)
  created_at:    string | null;
}

export interface ActivityCreateInput {
  activity_type: ActivityType;
  title_ar?:     string;
  details?:      Record<string, unknown>;
  scheduled_for?: string;
  performed_on?: string;
  season_id?:    string;
}

export const fetchActivities = (fieldId: string): Promise<Activity[]> =>
  kongApi.get<Activity[]>(`/api/v1/fields/${fieldId}/activities`).then(r => r.data);

export const createActivity = (
  fieldId: string,
  payload: ActivityCreateInput,
): Promise<Activity> =>
  kongApi.post<Activity>(`/api/v1/fields/${fieldId}/activities`, payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// WEATHER ADVICE — توصية ريّ (FAO-56) + مخاطر أمراض لكلّ حقل (Sprint 5a).
// تُحسبان من الطقس الحيّ (Open-Meteo) ومحصول الموسم النشط. ربط حيّ بلا تلفيق:
// عند الخطأ (503 طقس/قاعدة، 404 حقل، 422 بلا إحداثيّات، 403 RBAC) يُرمى
// ليعرض الـUI حالة صادقة (StateViews).
// ══════════════════════════════════════════════════════════════════
export interface IrrigationAdvice {
  recommended_mm: number;
  urgency:        'none' | 'low' | 'moderate' | 'high' | string;
  timing_ar:      string;
  et0:            number;
  kc:             number;
  rationale_ar:   string;
  field_id:       string;
  crop:           string | null;
  stage:          string;
  source:         string;
}

export interface DiseaseRisk {
  risk_level:     'low' | 'moderate' | 'high' | string;
  diseases_ar:    string[];
  advice_ar:      string;
  field_id:       string;
  crop:           string | null;
  temperature_c:  number;
  humidity_pct:   number;
  rain_mm_3d:     number;
  source:         string;
}

export const fetchIrrigationAdvice = (fieldId: string): Promise<IrrigationAdvice> =>
  kongApi.get<IrrigationAdvice>(`/api/v1/fields/${fieldId}/weather/irrigation-advice`).then(r => r.data);

export const fetchDiseaseRisk = (fieldId: string): Promise<DiseaseRisk> =>
  kongApi.get<DiseaseRisk>(`/api/v1/fields/${fieldId}/weather/disease-risk`).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// UNIFIED RECOMMENDATIONS — عمود التوصيات الموحَّد لكلّ حقل.
// يجمع الخادم (api.recommendations_hub، نقيّ) الريّ + التسميد + الأمراض + الحصاد
// في قائمة واحدة مفروزة بالأولويّة. تدهور رشيق: عند تعذّر الطقس يُرجع توصيات
// التسميد/الحصاد فقط (weather_available=false) — لا بيانات وهميّة. عند الخطأ
// (503 لا سياق كافٍ، 404 حقل، 403 RBAC) يُرفع ليعرض الـUI حالة صادقة.
// ══════════════════════════════════════════════════════════════════
export type RecommendationCategory = 'irrigation' | 'fertilizer' | 'disease' | 'yield';
export type RecommendationPriority = 'high' | 'medium' | 'low';

export interface FieldRecommendation {
  category:  RecommendationCategory | string;
  priority:  RecommendationPriority | string;
  title_ar:  string;
  detail_ar: string;
  source:    string;
}

export interface FieldRecommendationsResult {
  field_id:           string;
  crop:               string | null;
  stage:              string;
  weather_available:  boolean;
  recommendations:    FieldRecommendation[];
}

export const fetchFieldRecommendations = (fieldId: string): Promise<FieldRecommendationsResult> =>
  kongApi
    .get<FieldRecommendationsResult>(`/api/v1/fields/${fieldId}/recommendations`)
    .then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// ALERTS — التنبيهات الزراعيّة المُصنَّفة لكلّ مستأجِر (sahool-platform v36).
// ربط حيّ بلا fallback وهميّ: عند الخطأ (503 DB / 403 RBAC) يُرمى ليعرض الـUI
// حالة صادقة. field:view للقراءة، field:edit للإنشاء/الإقرار.
// ══════════════════════════════════════════════════════════════════
export type AlertType =
  | 'low_moisture' | 'heavy_rain' | 'disease_risk'
  | 'heat_stress' | 'frost_risk' | 'other';

export type AlertSeverity = 'info' | 'warning' | 'critical';
export type AlertStatus = 'active' | 'acknowledged' | 'resolved';

export interface AlertRecord {
  alert_id:    string;
  field_id:    string | null;
  alert_type:  AlertType | string;
  severity:    AlertSeverity | string;
  title_ar:    string | null;
  message_ar:  string | null;
  status:      AlertStatus | string;
  created_at:  string | null;
}

export interface AlertCreateInput {
  alert_type: AlertType;
  severity:   AlertSeverity;
  title_ar?:  string;
  message_ar?: string;
  field_id?:  string;
}

export interface AlertListFilters {
  status?:   AlertStatus;
  severity?: AlertSeverity;
}

export const fetchAlerts = (filters: AlertListFilters = {}): Promise<AlertRecord[]> =>
  kongApi.get<AlertRecord[]>('/api/v1/alerts', { params: filters }).then(r => r.data);

export const createAlert = (payload: AlertCreateInput): Promise<AlertRecord> =>
  kongApi.post<AlertRecord>('/api/v1/alerts', payload).then(r => r.data);

export const acknowledgeAlert = (alertId: string): Promise<AlertRecord> =>
  kongApi.patch<AlertRecord>(`/api/v1/alerts/${alertId}/acknowledge`).then(r => r.data);

// تقييم تلقائيّ لتنبيهات حقل: يُولّد تنبيهات مُصنَّفة من ظروف الحقل الحاليّة
// (الطقس الحيّ) ويُدرِجها في جدول alerts (v36) مع حذف تكرار النوع النشط.
export interface AlertEvaluateResult {
  created:           AlertRecord[];
  skipped_existing:  number;
}

export const evaluateFieldAlerts = (fieldId: string): Promise<AlertEvaluateResult> =>
  kongApi.post<AlertEvaluateResult>(`/api/v1/fields/${fieldId}/alerts/evaluate`).then(r => r.data);

// تشغيل تقييم التنبيهات لكلّ حقول المستأجِر دفعةً واحدة (أتمتة عند الطلب). معزول
// لكلّ حقل: الحقل المتعثّر يظهر بـerror دون إسقاط البقيّة (تدهور رشيق، لا 500).
export interface AlertsRunFieldSummary {
  field_id:  string;
  created:    number;
  skipped:    number;
  error?:     string;
}
export interface AlertsRunResult {
  fields_total:      number;
  fields_evaluated:  number;
  fields_failed:     number;
  created_total:     number;
  skipped_total:     number;
  per_field:         AlertsRunFieldSummary[];
}

export const runAllFieldsAlerts = (): Promise<AlertsRunResult> =>
  kongApi.post<AlertsRunResult>('/api/v1/automation/alerts/run').then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// NOTIFICATION PREFERENCES — قنوات تسليم التنبيهات لكلّ مستخدم (sahool-platform
// v9+v38). القنوات (بريد/SMS/Push/واتساب) + عناوينها + أنواع الأحداث المُشترَك بها
// + أرضيّة خطورة دنيا. ربط حيّ بلا تلفيق: عند الخطأ (503 DB / 403 RBAC) يُرمى
// لتعرض الواجهة حالة صادقة. field:view للقراءة، field:edit للحفظ (UPSERT).
// ══════════════════════════════════════════════════════════════════
export type NotifEventType =
  | 'satellite' | 'weather_alert' | 'pest_alert' | 'irrigation_rec'
  | 'fertilizer_rec' | 'low_stock' | 'task_assigned' | 'economic_analysis'
  | 'low_moisture' | 'heavy_rain' | 'disease_risk' | 'heat_stress'
  | 'frost_risk' | 'other';

export interface NotificationPreferences {
  email_enabled:    boolean;
  email_address:    string | null;
  sms_enabled:      boolean;
  sms_number:       string | null;
  push_enabled:     boolean;
  push_token:       string | null;
  whatsapp_enabled: boolean;
  whatsapp_number:  string | null;
  event_types:      string[];
  min_severity:     AlertSeverity | null;
}

export const fetchNotificationPreferences = (): Promise<NotificationPreferences> =>
  kongApi.get<NotificationPreferences>('/api/v1/notifications/preferences').then(r => r.data);

export const updateNotificationPreferences = (
  payload: NotificationPreferences,
): Promise<NotificationPreferences> =>
  kongApi.put<NotificationPreferences>('/api/v1/notifications/preferences', payload).then(r => r.data);

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

/** أحدث قراءة رطوبة تربة (٪) لأجهزة الحقل من telemetry الحيّ. reading=null إن لا قراءة. */
export interface SoilMoistureReading {
  soil_moisture_pct: number;
  recorded_at:       string;
  device_id:         string | null;
  unit:              string | null;
}

export interface FieldSoilMoisture {
  field_id: string;
  reading:  SoilMoistureReading | null;
}

/** أحدث رطوبة تربة لحقل من أجهزته (field:view). reading=null عند غياب قراءة صالحة. */
export const getFieldSoilMoisture = (fieldId: string): Promise<FieldSoilMoisture> =>
  kongApi.get<FieldSoilMoisture>(`/api/v1/fields/${fieldId}/soil-moisture`).then(r => r.data);

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
  key_id:       string;
  key_prefix?:  string;
  scope?:       string;
  created_by?:  string;
  expires_at?:  string | null;
  revoked_at?:  string | null; // الخادم يُرجِع طابعاً زمنيّاً (أو null) لا boolean
  [k: string]: unknown; // الخادم قد يُرجِع حقولاً إضافيّة — لا نقصّها
}
// SharingScope على الخادم = 'read' | 'read_write' (لا 'write').
export type SharingScope = 'read' | 'read_write';
export interface NewSharingKey {
  scope?:            SharingScope;
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
// FARMS — المزارع (أب الحقول). إنشاء/سرد حيّ عبر البوابة (kong)، مُقيَّد بالدور
// farm:create / farm:view وبالمستأجِر (RLS). لا fallback وهميّ — 503 عند تعطيل
// قاعدة البيانات. تُستخدم لبوّابة التأهيل: مستخدم جديد يُنشئ مزرعة قبل اللوحة.
// ══════════════════════════════════════════════════════════════════
export type FarmUnits = 'metric' | 'imperial';

export interface Farm {
  farm_id:        string;
  name:           string;
  location:       string | null;
  area_ha:        number | null;
  centroid_lat:   number | null;
  centroid_lon:   number | null;
  country?:       string | null;
  region?:        string | null;
  timezone?:      string | null;
  units?:         FarmUnits | null;
  currency?:      string | null;
  description?:   string | null;
  activity_type?: string | null;
  created_at?:    string | null;
}

export interface FarmCreateInput {
  name:           string;
  location?:      string;
  area_ha?:       number;
  country?:       string;
  region?:        string;
  timezone?:      string;
  units?:         FarmUnits;
  currency?:      string;
  description?:   string;
  activity_type?: string;
}

export interface FarmCreated {
  farm_id:    string;
  name:       string;
  message_ar: string;
}

export const fetchFarms = (): Promise<Farm[]> =>
  kongApi.get<Farm[]>('/api/v1/farms').then(r => r.data);

export const createFarm = (payload: FarmCreateInput): Promise<FarmCreated> =>
  kongApi.post<FarmCreated>('/api/v1/farms', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// FIELD DETAIL — تفاصيل الحقل المتقدّمة (sahool-platform v37). ملء تدريجيّ
// بعد الإنشاء: كيمياء التربة + المناخ الدقيق + الملكيّة. ربط حيّ بلا تلفيق —
// field:view للقراءة (GET /fields/{id})، field:edit للتحديث الجزئيّ (PATCH).
// عند الخطأ (503 DB / 404 حقل / 403 RBAC) يُرمى ليعرض الـUI حالة صادقة.
// ══════════════════════════════════════════════════════════════════
export interface FieldDetail {
  field_id:        string;
  farm_id:         string;
  name_ar:         string;
  crop:            string;
  area_ha:         number;
  quality_grade:   string;
  health_summary_ar: string;
  soil_type?:      string | null;
  manager?:        string | null;
  field_code?:     string | null;
  description?:    string | null;
  water_source?:   string | null;
  ownership_type?: string | null;
  country?:        string | null;
  region?:         string | null;
  lat?:            number | null;
  lon?:            number | null;
  geometry?:       Record<string, unknown> | null;
  // كيمياء التربة (نتائج مختبر)
  soil_ph?:        number | null;
  soil_ec?:        number | null;
  soil_om?:        number | null; // المادّة العضويّة %
  soil_n?:         number | null;
  soil_p?:         number | null;
  soil_k?:         number | null;
  // المناخ الدقيق / التضاريس
  elevation_m?:        number | null;
  slope_pct?:          number | null;
  aspect?:             string | null;
  climate_zone?:       string | null;
  annual_rainfall_mm?: number | null;
  // تفاصيل الملكيّة
  owner_name?:     string | null;
  lease_years?:    number | null;
  registry_no?:    string | null;
}

// تحديث جزئيّ: كلّ الحقول اختياريّة — تُرسَل المُعدَّلة فقط (الخادم يحدّثها فقط).
export interface FieldUpdatePatch {
  soil_ph?:            number | null;
  soil_ec?:            number | null;
  soil_om?:            number | null;
  soil_n?:             number | null;
  soil_p?:             number | null;
  soil_k?:             number | null;
  elevation_m?:        number | null;
  slope_pct?:          number | null;
  aspect?:             string | null;
  climate_zone?:       string | null;
  annual_rainfall_mm?: number | null;
  owner_name?:         string | null;
  lease_years?:        number | null;
  registry_no?:        string | null;
}

/** تفاصيل حقل كاملة (field:view). 404 لو ليس للمستأجِر، 503 عند تعطيل DB. */
export const fetchFieldDetail = (fieldId: string): Promise<FieldDetail> =>
  kongApi.get<FieldDetail>(`/api/v1/fields/${fieldId}`).then(r => r.data);

/** تحديث جزئيّ لتفاصيل حقل (field:edit). تُرسَل الحقول المُعدَّلة فقط. */
export const updateField = (fieldId: string, patch: FieldUpdatePatch): Promise<FieldDetail> =>
  kongApi.patch<FieldDetail>(`/api/v1/fields/${fieldId}`, patch).then(r => r.data);

// ── استيراد حدّ حقل من ملفّ (GeoJSON/KML) أو نقاط GPS (field:create) ──
// بدل الرسم اليدويّ: نرسل نصّ الملفّ (content) أو نقاط GPS (points) للخادم،
// الذي يحلّلها إلى GeoJSON Polygon ثمّ يعيد استخدام نفس مسار التحقّق/الحفظ
// كإنشاء حقل مرسوم. 400 = تحليل تالف، 422 = هندسة غير صالحة (يُعرَضان بصدق).
export interface FieldImportInput {
  format:        'geojson' | 'kml' | 'gps';
  content?:      string;          // نصّ ملفّ GeoJSON/KML
  points?:       number[][];      // مسار GPS [[lon,lat],...]
  name:          string;
  crop?:         string;
  soil_type?:    string;
  manager?:      string;
  field_code?:   string;
  water_source?: string;
  country?:      string;
  region?:       string;
}

/** يستورد حقلاً من ملفّ/نقاط GPS. يُرجع FieldSummary المُنشأ من ردّ الخادم. */
export const importField = (payload: FieldImportInput): Promise<unknown> =>
  kongApi.post('/api/v1/fields/import', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// INDICATORS DASHBOARD — لوحة المؤشّرات المُجمَّعة (حيّة عبر البوّابة)
// صدق المصدر: indicators-service خدمة stub صحّيّة فقط (لا منطق). اللوحة والكتالوج
// الحقيقيّان مُخدَّمان من sahool-platform عبر /api/v1/indicators/* (تجميع من
// fields/seasons/alerts، tenant-scoped + FIELD_VIEW). لا fallback وهميّ — عند
// الخطأ (503 DB / 403) يُرمى لتعرض الواجهة حالة صادقة (إلّا في MOCK_MODE الصريح).
// ══════════════════════════════════════════════════════════════════

/** لوحة المؤشّرات المُجمَّعة للمستأجِر: kpis + alerts + fields_summary */
export const fetchDashboard = () =>
  tryReal(
    () => kongApi.get('/api/v1/indicators/dashboard').then(r => r.data),
    () => MOCK_DASHBOARD
  );

/** كتالوج المؤشّرات المُنفَّذة فعلاً + مصادرها (لا ٣٣ مؤشّراً مُلفَّقاً) */
export const fetchIndicatorCatalog = () =>
  tryReal(
    () => kongApi.get('/api/v1/indicators/catalog').then(r => r.data),
    () => ({ total:14, categories:{} })
  );

// ملحوظة صدق: المؤشّرات الطيفيّة لكلّ حقل (NDVI/EVI/...) تُجلب من vegetation/raster
// لكلّ حقل (شاشة الأقمار) لا من نقطة 33-مؤشّر وهميّة. لذا fetchFieldIndicators/
// fetchSingleIndicator/fetchNatsStatus (التي كانت تستهدف indicators-service الـstub
// بلا خلفيّة حقيقيّة) أُزيلت لمصلحة الربط الحيّ الموحَّد عبر vegetation/raster.

/** Probes */
export const fetchIndicatorsHealth = () =>
  indicatorsApi.get('/health').then(r => r.data).catch(() => ({ status:'unavailable' }));

// ══════════════════════════════════════════════════════════════════
// VEGETATION SERVICE — مسارات حيّة مطابقة لـvegetation-analysis-service
// ربط حقيقيّ بلا تلفيق (إلّا MOCK_MODE الصريح). صدق المصدر: المؤشّرات تقديرات
// متوسّط-حقل من نطاقات تركيبيّة (real_data=false) — البكسلات الحقيقيّة في
// raster-service. أُصلحت المسارات/الأفعال لتطابق الخادم الفعليّ (GET /v1/*).
// ══════════════════════════════════════════════════════════════════

/** تحليل صورة + مؤشّرات + نشر NATS — GET /v1/analyze (الخادم يقبل GET بمعاملات) */
export const analyzeVegetation = (fieldId: string, _satellite = 'sentinel-2', tenantId = 'default') =>
  tryReal(
    () => vegetationApi.get('/v1/analyze', { params:{ field_id:fieldId, tenant_id:tenantId } }).then(r => r.data),
    () => mockVegetationAnalysis(fieldId)
  );

/** سلسلة زمنية NDVI — GET /v1/timeseries/{fieldId} */
export const fetchVegetationTimeseries = (fieldId: string, days = 30) =>
  tryReal(
    () => vegetationApi.get(`/v1/timeseries/${fieldId}`, { params:{ days } }).then(r => r.data),
    () => mockTimeseries(fieldId, days)
  );

/** NDVI الحالي — GET /v1/ndvi/current/{fieldId} */
export const fetchCurrentNDVI = (fieldId: string) =>
  tryReal(
    () => vegetationApi.get(`/v1/ndvi/current/${fieldId}`).then(r => r.data),
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
