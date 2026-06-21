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
import { clearAccessToken, getAccessToken, getTenantId } from '../lib/authStorage';
import { isAccessTokenExpired } from '../lib/jwt';

// ── توجيه العملاء: البوّابة (nginx/Kong :80) هي المرجع القانونيّ ──────────────
// القرار التصميميّ: الإنتاج المرجعيّ هو nginx/Kong على :80، فتنادي الواجهةُ
// مساراتٍ نسبيّةً تُوجَّه عبر البوّابة (لا اكتشاف اسم مضيف، لا منافذ مباشرة). أمّا
// `vite dev` فللتطوير فقط عبر وكيل vite (vite.config.ts) الذي يُحاكي نفس مسارات
// nginx. الوضع يُضبَط صراحةً بـVITE_API_MODE (الافتراضيّ 'gateway').
//
// مهمّ: مسارات الاستدعاء تحمل بادئاتها أصلاً (kongApi ينادي '/api/v1/...' و
// '/api/agent/...' و'/api/guardrails/...'، وauthApi ينادي '/auth/...')، لذا
// قاعدة kong/auth فارغة ('') كي لا تتكرّر البادئة:
//   kongApi.get('/api/v1/fields') + base '' = '/api/v1/fields' → nginx /api/v1/ ✓
// (الخلل السابق: base='/api' + '/api/v1/...' = '/api/api/v1/...' → 404).
// أمّا raster/vegetation/weather/soil فمساراتها لا تحمل بادئة البوّابة، فقاعدتها
// هي مسار البوّابة الذي يُجرّده nginx:
//   rasterApi.get('/v1/.../tilejson') + base '/api/raster' = '/api/raster/v1/...'
//   → nginx /api/raster/ يُجرّد ⇒ الخدمة تتلقّى '/v1/...' ✓
//
// VITE_API_MODE=gateway (الافتراضيّ): مسارات نسبيّة (nginx :80 أو وكيل vite).
// VITE_API_MODE=dev: منافذ localhost المباشرة (تشغيل الخدمات بلا بوّابة).
// أيّ VITE_*_BASE_URL صريح يَسبق الافتراضَين (يُحترَم حتى لو كان سلسلةً فارغة).
const API_MODE = import.meta.env.VITE_API_MODE || 'gateway';
const _dev = API_MODE === 'dev';

// يَحُلّ قاعدة عميل: المتغيّر الصريح إن عُرّف (?? يحترم '' الفارغة)، وإلّا
// الافتراضيّ حسب الوضع. قيم import.meta.env إمّا سلسلة أو undefined.
function resolveBase(envVal: string | undefined, gateway: string, dev: string): string {
  return envVal ?? (_dev ? dev : gateway);
}

const KONG_URL       = resolveBase(import.meta.env.VITE_API_BASE_URL,        '',                'http://localhost:8000');
const AUTH_URL       = resolveBase(import.meta.env.VITE_AUTH_BASE_URL,       '',                'http://localhost:8120');
const RASTER_URL     = resolveBase(import.meta.env.VITE_RASTER_BASE_URL,     '/api/raster',     'http://localhost:8001');
const VEGETATION_URL = resolveBase(import.meta.env.VITE_VEGETATION_BASE_URL, '/api/vegetation', 'http://localhost:8090');
const INDICATORS_URL = resolveBase(import.meta.env.VITE_INDICATORS_BASE_URL, '/api/indicators', 'http://localhost:8091');
const WEATHER_URL    = resolveBase(import.meta.env.VITE_WEATHER_BASE_URL,    '/api/weather',    'http://localhost:8092');
const SOIL_URL       = resolveBase(import.meta.env.VITE_SOIL_BASE_URL,       '/api/soil',       'http://localhost:8094');
const MOCK_MODE      = import.meta.env.VITE_MOCK_MODE === 'true' || false;

// ── Axios instances ────────────────────────────────────────────
function makeClient(baseURL: string): AxiosInstance {
  const client = axios.create({ baseURL, timeout: 15000, headers: { 'Content-Type': 'application/json' } });
  // JWT interceptor
  client.interceptors.request.use((config) => {
    // FIX (مراجعة): useAuth يكتب التوكن/المستأجِر في sessionStorage، فكانت قراءة
    // localStorage هنا تُرجِع فارغاً ⇒ كلّ طلبات kongApi غير مُصادَقة. نقرأ من
    // sessionStorage حيث يُكتَب فعلاً (مصدر الحقيقة في useAuth.ts).
    const token = getAccessToken();
    // فحص انتهاء الصلاحيّة جهة-العميل (Phase 2): بدل انتظار 401 من الخادم، نكتشف
    // التوكن المنتهي محلياً فنُنظّف الجلسة ونُطلق حدث الخروج (يُسقطه App على شاشة
    // الدخول) ونمنع إطلاق طلب محكوم بالفشل. وضع التجريب مُستثنى (isAccessTokenExpired
    // يعيد false لتوكن التجريب) فلا يُكسَر. fail-closed: توكن مشوّه ⇒ يُعدّ منتهياً.
    if (token && isAccessTokenExpired(token)) {
      clearAccessToken();
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('sahool:auth:unauthorized'));
      }
      return Promise.reject(new Error('access token expired'));
    }
    if (token) config.headers.Authorization = `Bearer ${token}`;
    config.headers['X-Tenant-ID'] = getTenantId();
    return config;
  });
  // 401 → logout
  client.interceptors.response.use(
    (r) => {
      // حارس: لو رجع HTML (SPA fallback لمسار API غير مُوجَّه) بدل JSON ⇒ عامله خطأً
      // بدل تمرير نصّ HTML للمكوّنات فتنهار (مثل alerts.slice(...).map is not a function).
      const ct = (r.headers?.['content-type'] || '') as string;
      if (
        typeof r.data === 'string' &&
        (ct.includes('text/html') || r.data.trimStart().startsWith('<'))
      ) {
        return Promise.reject(
          new Error('استجابة غير صالحة من الخادم (مسار API غير مُوجَّه للخلفيّة؟)')
        );
      }
      return r;
    },
    (err) => {
      if (err.response?.status === 401) {
        clearAccessToken();
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
// auth-service يردّ حقولاً مسطّحة (TokenResponse: user_id/role/full_name/tenant_id،
// بلا كائن user مُتداخل). نُطبّعها أدناه إلى {user:{...}} كي يقرأها useAuth بثبات.
// user اختياريّ (غائب في الردّ الخام) ويحوي id (من user_id) لتفادي ضياعه.
export interface AuthResponse {
  access_token: string;
  // قد تكون null حين لا يتوفّر Redis (auth-service لا يُصدِر refresh) — نُبقيها كما
  // هي بدل طمسها بـ'' (سلسلة فارغة تُلتبَس كتوكن صالح). يطابق عقد TokenResponse.
  refresh_token: string | null;
  tenant_id?: string;
  role?: string;
  user_id?: number;
  full_name?: string;
  user?: { id?: number; username?: string; role: string; tenant_id?: string; email?: string; full_name?: string };
}

export const login = (payload: LoginPayload): Promise<AuthResponse> =>
  // أمان (P0-2): المصادقة لا تسقط على fallback وهمي. الفشل يظهر بوضوح
  // بدل منح admin زائف. وضع التجريب فقط عبر MOCK_MODE الصريح، وبدور farmer.
  // mfa_code يُرسَل فقط إن وُجد (الخادم يتطلّبه للحسابات المُفعّل لها MFA).
  MOCK_MODE
    ? Promise.resolve({ access_token:'demo_token', refresh_token:'demo_refresh', user:{ username:payload.email, email:payload.email, role:'farmer' } } as AuthResponse)
    : authApi.post('/auth/login', {
        email: payload.email,
        password: payload.password,
        ...(payload.mfa_code ? { mfa_code: payload.mfa_code } : {}),
      }).then(r => {
        // الردّ الخام مسطّح ⇒ نطبّعه إلى {user:{...}} (كان login يُعيد الخام مباشرةً
        // فيصبح data.user = undefined وقت التشغيل، فيضيع user_id/full_name).
        const d = r.data as { access_token: string; refresh_token?: string | null; role?: string;
          full_name?: string; tenant_id?: string; user_id?: number };
        return {
          access_token: d.access_token,
          refresh_token: d.refresh_token ?? null,
          tenant_id: d.tenant_id,
          role: d.role,
          user_id: d.user_id,
          full_name: d.full_name,
          user: { id: d.user_id, username: payload.email, email: payload.email,
            role: d.role ?? 'farmer', tenant_id: d.tenant_id, full_name: d.full_name },
        } as AuthResponse;
      });

// شكل خطأ أكسيوس/FastAPI كما تقرؤه الواجهة (response.status/data.detail + message).
// نوع موحّد بدل any المتناثر في معالِجات catch وحُرّاس .response?.status عبر الشاشات.
export interface ApiErrorDetailItem { msg?: string; message_ar?: string }
export interface ApiError {
  response?: {
    status?: number;
    headers?: Record<string, string | boolean | undefined>;
    data?: {
      detail?: string | ApiErrorDetailItem[] | { message_ar?: string; msg?: string };
      message_ar?: string;
    };
  };
  message?: string;
}

// يضيّق unknown → ApiError بأمان (يقرأ الحقول كاختياريّة فقط، لا يفترض شكلاً صلباً).
export function asApiError(e: unknown): ApiError {
  return (e ?? {}) as ApiError;
}

/** يفحص ما إذا كان خطأ تسجيل الدخول يعني "MFA مطلوب" (الخادم يردّ 401 مع
 *  الرأس X-MFA-Required: true حين تصحّ كلمة المرور لكن يلزم رمز TOTP). */
export function isMfaRequiredError(e: unknown): boolean {
  const err = asApiError(e);
  const status = err.response?.status;
  const header = err.response?.headers?.['x-mfa-required'];
  return status === 401 && (header === 'true' || header === true);
}

// يستخرج رسالة خطأ مقروءة من ردّ FastAPI (detail قد يكون نصّاً أو مصفوفة كائنات).
export function apiErrorMessage(e: unknown, fallback: string): string {
  const err = asApiError(e);
  const d = err.response?.data?.detail ?? err.response?.data?.message_ar;
  if (Array.isArray(d)) {
    const msgs = d.map((x) => x?.msg || x?.message_ar || '').filter(Boolean);
    return msgs.length ? msgs.join('، ') : fallback;
  }
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object') return d.message_ar || d.msg || fallback;
  return err.message || fallback;
}

export interface RegisterPayload { full_name: string; email: string; password: string }
// التسجيل: الخلفيّة تُصدر توكناً مباشرةً (تسجيل دخول تلقائيّ). الدور يُثبَّت
// 'farmer' خادم-جانبيّاً (منع تصعيد الصلاحيّات) — لا يُرسَل دور من العميل.
export const register = (payload: RegisterPayload): Promise<AuthResponse> =>
  MOCK_MODE
    ? Promise.resolve({ access_token:'demo_token', refresh_token:'demo_refresh',
        user:{ username:payload.email, email:payload.email, role:'farmer', full_name:payload.full_name } } as AuthResponse)
    : authApi.post('/auth/register', payload).then(r => {
    const d = r.data as { access_token: string; refresh_token?: string | null; role?: string;
      full_name?: string; tenant_id?: string; user_id?: number };
    return {
      access_token: d.access_token,
      refresh_token: d.refresh_token ?? null,
      tenant_id: d.tenant_id,
      role: d.role,
      user_id: d.user_id,
      full_name: d.full_name ?? payload.full_name,
      user: { id: d.user_id, username: payload.email, email: payload.email, role: d.role ?? 'farmer',
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

// ── Email/Phone Verification (تأكيد البريد/الهاتف — soft) ──────────
// تحقّق ناعم بعد التسجيل: المستخدم يطلب رمز OTP من ٦ أرقام (Redis قصير الأجل
// على الخادم) ثمّ يؤكّده فيُعلَّم الحساب verified_email/verified_phone. التسليم
// STUB خادميّاً (سجلّ، لا بوّابة بريد/SMS فعليّة بعد). لا fallback وهميّ.
export type VerifyChannel = 'email' | 'phone';

export interface VerificationStatus {
  verified_email: boolean;
  verified_phone: boolean;
}

/** حالة تحقّق الحساب الحاليّة (بريد/هاتف) من الخادم. (يتطلّب توكناً) */
export const getVerificationStatus = (): Promise<VerificationStatus> =>
  authApi.get<VerificationStatus>('/auth/verify/status').then(r => r.data);

/** يطلب إصدار رمز تحقّق للقناة (بريد/هاتف). محدود المعدّل خادميّاً (429). */
export const requestVerification = (
  channel: VerifyChannel,
): Promise<{ message: string; channel: VerifyChannel; expires_in: number }> =>
  authApi
    .post<{ message: string; channel: VerifyChannel; expires_in: number }>(
      '/auth/verify/request',
      { channel },
    )
    .then(r => r.data);

/** يؤكّد رمز التحقّق للقناة. 400 لرمز غير صالح/منتهٍ. */
export const confirmVerification = (
  channel: VerifyChannel,
  code: string,
): Promise<{ message: string; channel: VerifyChannel; verified: boolean }> =>
  authApi
    .post<{ message: string; channel: VerifyChannel; verified: boolean }>(
      '/auth/verify/confirm',
      { channel, code },
    )
    .then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// SAHOOL-PLATFORM (core) — وحدات قرار حيّة عبر البوابة الموحّدة (kong)
// ربط حقيقيّ: لا fallback وهميّ (قرارات زراعيّة — الخطأ يُعلَن للـUI).
// ══════════════════════════════════════════════════════════════════
// ── Tenant Config (#206): تكوين المستأجِر للعلامة التجاريّة + الوحدات/اللغة ──
// GET /api/v1/tenant/config → {branding:{logo_url, primary_color, name_ar}, units,
// language, crops}. الحقول كلّها اختياريّة/قد تكون null (الافتراضيّ): الواجهة
// تتجاهل أيّ حقل غائب وتُبقي سلوكها الحاليّ. أفضل-جهد: عند أيّ خطأ نُرجِع null
// (لا fallback مُفبرَك، ولا كسر) فتعمل الواجهة بالافتراضيّات كما هي اليوم.
export interface TenantBranding {
  logo_url:      string | null;
  primary_color: string | null;
  name_ar:       string | null;
}
export interface TenantConfig {
  branding: TenantBranding | null;
  units:    string | null;
  language: string | null;
  crops:    string[] | null;
}

/** يجلب تكوين المستأجِر (#206). أفضل-جهد: أيّ خطأ/استجابة غير صالحة ⇒ null
 *  فتُبقي الواجهة الافتراضيّات (لا كسر، لا علامة تجاريّة مُفبرَكة). */
export const fetchTenantConfig = (): Promise<TenantConfig | null> =>
  kongApi
    .get<TenantConfig>('/api/v1/tenant/config')
    .then((r) => (r.data && typeof r.data === 'object' ? r.data : null))
    .catch(() => null);

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

// ── خطّة الريّ التنبّؤيّة (POST /api/v1/irrigation-plan) — خطّ «مركز المحاصيل» ──
// نسيج+عمق ⇒ TAW ⇒ سياسة ⇒ جدول ريّ عبر أفق التنبّؤ (FAO-56). كلّ القيم موسومة calibrated.
export interface ForecastDayInput {
  et0_mm: number; kc: number; rain_mm?: number; runoff_mm?: number;
}
export interface IrrigationPlanInput {
  forecast: ForecastDayInput[];
  soil_texture?: string | null;
  root_depth_m?: number | null;
  taw_mm?: number | null;
  raw_fraction?: number;
  policy?: string;
  initial_depletion_mm?: number;
  max_application_mm?: number | null;
  season_budget_mm?: number | null;
  water_price_per_m3?: number | null;
  yield_value_per_ha?: number | null;
}
export interface SoilWaterParams {
  texture: string | null;
  texture_known: boolean;
  taw_mm_per_m: number;
  root_depth_m: number;
  taw_mm: number;
  raw_fraction: number;
  raw_mm: number;
  calibrated: boolean;
  warnings_ar: string[];
}
export interface PlannedDay {
  day_index: number;
  etc_mm: number;
  eff_rain_mm: number;
  dr_before_irrig_mm: number;
  irrigation_mm: number;
  dr_end_mm: number;
  deep_perc_mm: number;
  stressed: boolean;
}
export interface IrrigationPlan {
  policy: string;
  taw_mm: number;
  raw_mm: number;
  total_irrigation_mm: number;
  total_irrigation_m3_ha: number;
  n_events: number;
  stress_days: number[];
  total_deep_perc_mm: number;
  final_depletion_mm: number;
  budget_exhausted: boolean;
  calibrated: boolean;
  notes_ar: string[];
  days: PlannedDay[];
}
export interface DataQuality {
  confidence: number;       // مقياس اكتمال/جودة مدخلات شفّاف [0,1] (لا فاصل إحصائيّ)
  data_quality: string;     // low | medium | high
  assumptions: string[];    // رموز آليّة
  assumptions_ar: string[]; // وصف عربيّ للمستخدم
  calibrated: boolean;
}
export interface IrrigationPlanResult {
  soil: SoilWaterParams;
  taw_mm_used: number;
  quality: DataQuality;
  plan: IrrigationPlan;
}
export const computeIrrigationPlan = (payload: IrrigationPlanInput): Promise<IrrigationPlanResult> =>
  kongApi.post<IrrigationPlanResult>('/api/v1/irrigation-plan', payload).then(r => r.data);

// ── توزيع ماء المزرعة (POST /api/v1/field-portfolio/allocate) ──
// يوزّع ماء آبار محدودة على حقول متعدّدة وفق الأولويّة والحدّ الأدنى لكلّ حقل،
// فيُظهر أيّ الحقول مَحميّ وأيّها مُجهَد/غير مُلبّى — قرار محفظة لا حقل واحد.
export interface PortfolioFieldInput {
  field_id: string;
  expected_margin: number;
  water_demand_m3: number;
  priority?: number;
  min_water_fraction?: number;
  source_ids?: string[];
}
export interface PortfolioSourceInput {
  source_id: string;
  capacity_m3: number;
}
export interface PortfolioAllocInput {
  fields: PortfolioFieldInput[];
  sources: PortfolioSourceInput[];
}
export interface PortfolioFieldResult {
  field_id: string;
  priority: number;
  water_demand_m3: number;
  allocated_m3: number;
  fraction: number;
  water_productivity: number | null;
  expected_margin_captured: number;
  stressed: boolean;
  status: string; // full | partial | protected_min | unmet
  sources_used: Record<string, number>;
}
export interface PortfolioSourceResult {
  source_id: string;
  capacity_m3: number;
  used_m3: number;
  remaining_m3: number;
}
export interface PortfolioAllocResult {
  fields: PortfolioFieldResult[];
  sources: PortfolioSourceResult[];
  total_expected_margin: number;
  total_allocated_m3: number;
  protected_fields: string[];
  stressed_fields: string[];
  unmet_fields: string[];
  calibrated: boolean;
  warnings_ar: string[];
}
export const computePortfolioAllocation = (payload: PortfolioAllocInput): Promise<PortfolioAllocResult> =>
  kongApi.post<PortfolioAllocResult>('/api/v1/field-portfolio/allocate', payload).then(r => r.data);

// ── استعلام GIS باللغة الطبيعيّة (POST /api/v1/nl-gis/query) — قراءة فقط ──
// يصنّف استعلاماً عربيّاً حرّاً إلى نيّة مغلقة (تنبيه/انخفاض NDVI/فجوة ريّ) ويُعيد
// معاينة قراءة-فقط للحقول المطابقة من بيانات المستأجِر — لا تنفيذ ولا تعديل (read_only).
// خلف العلم FEATURE_NATURAL_LANGUAGE_GIS؛ مُطفأً ⇒ 404 (تلتقطه الواجهة برسالة «الميزة
// غير مُفعَّلة»). 503 ⇒ القاعدة غير متاحة (حالة خطأ صادقة). العناصر متغايرة المفاتيح
// حسب النيّة (تُعرَض أعمدةً ديناميكيّةً)، وقيمها بدائيّات JSON (نصّ/رقم/null؛ التواريخ
// مُنصَّصة مسبقاً). لا fallback وهميّ: الخطأ يُرفع لتعرض الواجهة حالة صادقة عبر
// .response?.status (مطابقةً لبقيّة الصفحات التي تكشف 404).
export interface NlGisQueryInput {
  query: string;
}
// عنصر نتيجة متغاير المفاتيح حسب النيّة — قيمه بدائيّات JSON فقط (لا كائنات متداخلة).
export type NlGisItem = Record<string, string | number | boolean | null>;
export interface NlGisResult {
  read_only:   boolean;
  intent:      string;                 // alert_filter | ndvi_drop | irrigation_gap | unsupported
  supported:   boolean;
  status:      string;                 // ok | needs_data | unsupported
  slots?:      Record<string, string | number | null>;
  confidence?: number;
  api_called?: string;
  items:       NlGisItem[];
  count:       number;
  note_ar?:    string | null;          // شرح الفراغ/الحاجة للبيانات
  reason_ar?:  string | null;          // سبب عدم الدعم (intent=unsupported)
  tenant_id?:  string;
}
/** يستعلم GIS باللغة الطبيعيّة (POST /api/v1/nl-gis/query) — قراءة فقط لا تنفيذ.
 *  يرمي عند الخطأ (404 العلم مُطفأ — تلتقطه الواجهة برسالة «الميزة غير مُفعَّلة»؛
 *  503 القاعدة غير متاحة تُعرَض كحالة خطأ صادقة). */
export const queryNlGis = (payload: NlGisQueryInput): Promise<NlGisResult> =>
  kongApi.post<NlGisResult>('/api/v1/nl-gis/query', payload).then(r => r.data);

// ── مركز قيادة المحفظة (POST /api/v1/portfolio/command) ──
// يقارن سياسات ريّ متعدّدة عبر حقول المزرعة تحت قيود مصادر الماء، فيُراكِب الربح×المخاطرة
// لكلّ سياسة ويوصي بأفضلها — توصية فقط لا تنفيذ ولا حجز ماء. خلف العلم
// FEATURE_PORTFOLIO_COMMAND؛ مُطفأً ⇒ 404 (تتعامل معه الواجهة برسالة «الميزة غير مُفعَّلة»).
// kind للمصدر: well | pump | pivot | network. للمضخّة: السعة الفعليّة =
// min(capacity, max_rate_m3_per_day × window_days). source_ids على الحقل = أيّ المصادر
// تخدمه (تغطية المحور)؛ فارغة ⇒ كلّ المصادر.
export type PortfolioCommandSourceKind = 'well' | 'pump' | 'pivot' | 'network';
export interface PortfolioCommandFieldInput {
  field_id: string;
  expected_margin: number;
  water_demand_m3: number;
  priority?: number;
  min_water_fraction?: number;
  source_ids?: string[];
}
export interface PortfolioCommandSourceInput {
  source_id: string;
  capacity_m3: number;
  kind?: PortfolioCommandSourceKind;
  max_rate_m3_per_day?: number | null;
  window_days?: number | null;
}
export interface PortfolioCommandScenarioInput {
  policy_label: string;
  fields: PortfolioCommandFieldInput[];
  sources: PortfolioCommandSourceInput[];
}
export interface PortfolioCommandInput {
  scenarios: PortfolioCommandScenarioInput[];
  risk_aversion?: number;
}
// قيد مصدر مُحلّ لسياسة (السعة الفعليّة مقابل الاسميّة + هل قيَّده تدفّقه/نافذته).
export interface PortfolioCommandConstraint {
  source_id: string;
  kind: PortfolioCommandSourceKind | string;
  capacity_m3: number;
  effective_capacity_m3: number;
  throughput_bound: boolean;
}
// التوزيع التفصيليّ لسياسة (نفس عقد field-portfolio/allocate تقريباً) — شكل مرن.
export interface PortfolioCommandAllocation {
  fields: Array<Record<string, unknown>>;
  sources: Array<Record<string, unknown>>;
  total_expected_margin: number;
  total_allocated_m3: number;
  protected_fields: string[];
  stressed_fields: string[];
  unmet_fields: string[];
  calibrated: boolean;
  warnings_ar: string[];
}
export interface PortfolioCommandPolicyResult {
  policy: string;
  total_expected_margin: number;
  total_allocated_m3: number;
  total_demand_m3: number;
  served_fraction: number;
  risk_score: number;
  fields_count: number;
  protected_count: number;
  stressed_count: number;
  unmet_count: number;
  constraints: PortfolioCommandConstraint[];
  constraints_bound: string[];
  objective_score: number;
  allocation: PortfolioCommandAllocation;
}
export interface PortfolioCommandResult {
  policies: PortfolioCommandPolicyResult[];
  recommended_policy: string;
  risk_aversion: number;
  calibrated: boolean;
  warnings_ar: string[];
  tenant_id: string;
}
/** يقارن سياسات الريّ عبر الحقول تحت قيود المصادر (POST /api/v1/portfolio/command).
 *  توصية فقط لا تنفيذ. يرمي عند الخطأ (404 العلم مُطفأ — تلتقطه الواجهة برسالة
 *  «الميزة غير مُفعَّلة»؛ 503/422 تُعرَض كحالة خطأ صادقة). */
export const computePortfolioCommand = (payload: PortfolioCommandInput): Promise<PortfolioCommandResult> =>
  kongApi.post<PortfolioCommandResult>('/api/v1/portfolio/command', payload).then(r => r.data);

// ── توأم شبكة الريّ (irrigation network feasibility) ──────────────────────────
// المستخدم يُعرّف شبكة ريّ (عُقد + حوافّ: بئر→مضخّة→…→منطقة)، والمحرّك يفحص جدوى
// التنفيذ قبل أيّ ريّ (اتّصاليّة/توفّر ماء/تدفّق/ضغط) ويُبرِز الاختناقات. توصية فقط
// لا تنفيذ ولا فتح صمّامات. القيود غير المحدَّدة تُعرَض صراحةً كـunchecked (لا تُفترَض ناجحة).
export type IrrigationNetworkNodeKind =
  'well' | 'pump' | 'filter' | 'fertilizer' | 'main_line' | 'submain' | 'valve' | 'zone';
export interface IrrigationNetworkNode {
  node_id: string;
  kind: IrrigationNetworkNodeKind;
  capacity_m3?: number | null;
  max_throughput_m3?: number | null;
  max_pressure_bar?: number | null;
  min_pressure_bar?: number | null;
  demand_m3?: number | null;
}
export interface IrrigationNetworkEdge {
  from_id: string;
  to_id: string;
}
export interface IrrigationNetworkInput {
  nodes: IrrigationNetworkNode[];
  edges: IrrigationNetworkEdge[];
}
// حالة جدوى المنطقة: feasible (كلّ الفحوص المعروفة تمرّ ولا شيء غير مفحوص)،
// feasible_unverified (تمرّ المعروفة لكن توجد قيود غير مفحوصة — تُعرَض بلون كهرمانيّ
// مع قائمة unchecked)، infeasible (انتهاك صلب في reasons_ar).
export type IrrigationZoneStatus = 'feasible' | 'feasible_unverified' | 'infeasible';
export interface IrrigationZoneFeasibility {
  zone_id: string;
  demand_m3: number;
  status: IrrigationZoneStatus;
  path: string[] | null;
  reasons_ar?: string[];
  bottlenecks: string[];
  unchecked: string[];
}
export interface IrrigationWellLoad {
  well_id: string;
  capacity_m3: number;
  load_m3: number;
  over_capacity: boolean;
}
export interface IrrigationNetworkResult {
  zones: IrrigationZoneFeasibility[];
  wells: IrrigationWellLoad[];
  overall_feasible: boolean;
  zone_count: number;
  feasible_count: number;
  calibrated: string;
  warnings_ar: string[];
  tenant_id: string;
}
/** يفحص جدوى تنفيذ شبكة الريّ قبل أيّ ريّ (POST /api/v1/irrigation/network/feasibility).
 *  توصية فقط لا تنفيذ ولا فتح صمّامات. يرمي عند الخطأ (404 العلم مُطفأ
 *  FEATURE_IRRIGATION_NETWORK — تلتقطه الواجهة برسالة «الميزة غير مُفعَّلة»؛
 *  503/422 تُعرَض كحالة خطأ صادقة). */
export const checkIrrigationNetworkFeasibility = (payload: IrrigationNetworkInput): Promise<IrrigationNetworkResult> =>
  kongApi.post<IrrigationNetworkResult>('/api/v1/irrigation/network/feasibility', payload).then(r => r.data);

// ── حالة المعايرة الإقليميّة (GET /api/v1/calibration) — قراءة فقط ──
// يكشف لكلّ إقليم يمنيّ هل ثوابته الأغرونوميّة مُتحقَّق منها ميدانيّاً أم ما تزال
// افتراضات FAO عامّة — فيرى المستخدم أين تنقص بيانات المعايرة الحقيقيّة. صدق: لا
// تلفيق؛ الأقاليم غير المُتحقَّق منها (validated=false) ترث الافتراضات العامّة.
export interface CalibrationProfile {
  region:                string;
  region_ar:             string;
  validated:             boolean;
  source_ar:             string;
  raw_fraction:          number;
  root_depth_m:          number;
  kc_dyn_min:            number;
  kc_dyn_max:            number;
  forecast_infiltration: number;
  uptake_fractions:      Record<string, number>;
  yield_uncertainty:     number;
  price_uncertainty:     number;
  evidence_level:        'none' | 'expert_opinion' | 'field_preliminary' | 'field_verified' | string;
  sample_count:          number;
  last_evaluated_at:     string | null;
  notes_ar:              string[];
}
export interface CalibrationOverview {
  generic:         CalibrationProfile;
  regions:         CalibrationProfile[];
  validated_count: number;
  note_ar:         string;
}
export const fetchCalibration = (): Promise<CalibrationOverview> =>
  kongApi.get<CalibrationOverview>('/api/v1/calibration').then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// CALIBRATION WORKBENCH — منضدة معايرة الخبير الزراعيّ (مقارنة/اقتراح/موافقة/رفض/تدقيق)
// تستهلك نقاط calibration.py الحقيقيّة: القاعدة (GET /{region}) مقابل المُدام
// (GET /{region}/resolved)، التحقّق (POST /{region}/propose-values — يقترح لا يكتب)،
// الإدامة (POST /{region}/override مع source_ar) وعكسها (DELETE /{region}/override)،
// وتطبيق التكيّف بدليل مُدام (POST /{region}/adapt-from-evidence/apply, confirm=true).
// صدق: لا قيمة بلا API؛ POST/DELETE ترمي عند الخطأ ليعرض الـUI حالة صادقة؛ لا any.
// ══════════════════════════════════════════════════════════════════

// ملفّ المنطقة بعد دمج التجاوز المُدام (GET /{region}/resolved) — يطابق
// apply_region_override: CalibrationProfile + وسما المصدر/الحقول المُطبَّقة.
export interface ResolvedCalibration extends CalibrationProfile {
  override_applied: string[];               // الحقول التي طُبِّق فيها تجاوز مُدام
  override_source:  'db_override' | 'inherited' | string;
}
/** القاعدة الموروثة لمنطقة (GET /api/v1/calibration/{region}). */
export const fetchRegionCalibration = (region: string): Promise<CalibrationProfile> =>
  kongApi
    .get<CalibrationProfile>(`/api/v1/calibration/${encodeURIComponent(region)}`)
    .then(r => r.data);
/** الملفّ المُحلّ مع التجاوز المُدام (GET /api/v1/calibration/{region}/resolved). */
export const fetchResolvedCalibration = (region: string): Promise<ResolvedCalibration> =>
  kongApi
    .get<ResolvedCalibration>(`/api/v1/calibration/${encodeURIComponent(region)}/resolved`)
    .then(r => r.data);

// نتيجة التحقّق (validate_region_calibration) — مشتركة بين propose-values/override.
export interface CalibrationRejection { field: string; value: unknown; reason_ar: string }
export interface CalibrationValidation {
  region:           string;
  accepted:         Record<string, number | Record<string, number>>;
  rejected:         CalibrationRejection[];
  override_block:   Record<string, number | Record<string, number>>;
  validated:        boolean;
  source_ar:        string | null;
  ready_to_persist: boolean;
  calibrated:       false;
  warnings_ar:      string[];
}
// مدخلات الاقتراح/الإدامة (ProposeValuesRequest) — كلّ الحقول اختياريّة؛ نرسل
// المُعرَّف فقط. source_ar إلزاميّ للإدامة (الخادم يرفض 422 بلا مصدر).
export interface CalibrationValuesInput {
  raw_fraction?:          number;
  root_depth_m?:          number;
  kc_dyn_min?:            number;
  kc_dyn_max?:            number;
  forecast_infiltration?: number;
  yield_uncertainty?:     number;
  price_uncertainty?:     number;
  uptake_fractions?:      Record<string, number>;
  source_ar?:             string;
}
/** يتحقّق من قيم مقترَحة ضدّ حدود آمنة (POST /{region}/propose-values) — يقترح لا يكتب.
 *  الخادم يُرجِع 200 مع accepted/rejected (لا 422 هنا)؛ أخطاء الشبكة/503 تُرمى. */
export const proposeCalibrationValues = (
  region: string,
  values: CalibrationValuesInput,
): Promise<CalibrationValidation> =>
  kongApi
    .post<CalibrationValidation>(
      `/api/v1/calibration/${encodeURIComponent(region)}/propose-values`,
      values,
    )
    .then(r => r.data);

// نتيجة الإدامة الناجحة (set_region_override) — يُعيد المقبول + الملفّ المُحلّ.
export interface CalibrationOverrideResult {
  region:    string;
  persisted: true;
  accepted:  Record<string, number | Record<string, number>>;
  source_ar: string | null;
  resolved:  ResolvedCalibration;
}
/** يُدِيم قيماً مُتحقَّقة لمنطقة (POST /{region}/override). source_ar إلزاميّ.
 *  يرمي عند الخطأ (422 رفض/نقص مصدر، 503 DB) ليعرض الـUI سببه بصدق. */
export const setRegionOverride = (
  region: string,
  values: CalibrationValuesInput,
): Promise<CalibrationOverrideResult> =>
  kongApi
    .post<CalibrationOverrideResult>(
      `/api/v1/calibration/${encodeURIComponent(region)}/override`,
      values,
    )
    .then(r => r.data);

/** يحذف التجاوز المُدام ويعيد المنطقة للوراثة (DELETE /{region}/override).
 *  يرمي عند الخطأ (503 DB) — لا حذف تفاؤليّ صامت. */
export const deleteRegionOverride = (
  region: string,
): Promise<{ region: string; reverted: boolean }> =>
  kongApi
    .delete<{ region: string; reverted: boolean }>(
      `/api/v1/calibration/${encodeURIComponent(region)}/override`,
    )
    .then(r => r.data);

// تطبيق التكيّف بدليل مُدام (apply_region_adaptation_from_evidence) — confirm=true
// إلزاميّ صريح. الردّ هو الاقتراح (propose_calibration_adjustment) + applied/persisted.
// الشكل دفاعيّ: غير مؤهَّل ⇒ applied=false ويُعاد الاقتراح كما هو (لا تطبيق خفيّ).
export interface AdaptProposalItem {
  parameter: string;
  current?:  number;
  proposed?: number;
  [k: string]: unknown;
}
export interface AdaptApplyResult {
  status:              string;            // auto_apply_eligible | gated | …
  applied:             boolean;           // أُدِيم فعلاً؟ (false ⇒ لم يُطبَّق)
  proposals:           AdaptProposalItem[];
  decision_id?:        string;
  evidence_used?:      Record<string, unknown>;
  source_ar?:          string | null;
  persisted_override?: Record<string, number>;
  resolved?:           ResolvedCalibration;
  warnings_ar?:        string[];
  [k: string]:         unknown;
}
export interface AdaptApplyInput {
  confirm: boolean;                       // يجب أن يكون true (الخادم يرفض 422 بلا تأكيد)
  source_ar?:          string;
  mean_stress_delta?:  number;
  decision_id?:        string;
}
/** يُطبّق تكيّف المعايرة المحروس بالدليل المُدام (POST /{region}/adapt-from-evidence/apply).
 *  confirm=true إلزاميّ. يرمي عند الخطأ (422 بلا تأكيد/خارج الأمان، 503 DB). */
export const applyAdaptFromEvidence = (
  region: string,
  input: AdaptApplyInput,
): Promise<AdaptApplyResult> =>
  kongApi
    .post<AdaptApplyResult>(
      `/api/v1/calibration/${encodeURIComponent(region)}/adapt-from-evidence/apply`,
      input,
    )
    .then(r => r.data);

// كلّ التجاوزات المُدامة للمستأجِر (GET /api/v1/calibration/overrides/all) — لإدارة
// أيّ المناطق صار لها قيم مُدامة ومصدرها/وقت تحديثها (بديل سجلّ التدقيق إن غاب).
export interface CalibrationOverrideEntry {
  region:          string;
  override_values: Record<string, number | Record<string, number>>;
  source_ar:       string | null;
  validated:       boolean;
  updated_at:      string | null;
}
export interface CalibrationOverridesResult {
  overrides: CalibrationOverrideEntry[];
  count:     number;
}
export const fetchCalibrationOverrides = (): Promise<CalibrationOverridesResult> =>
  kongApi
    .get<CalibrationOverridesResult>('/api/v1/calibration/overrides/all')
    .then(r => ({
      overrides: Array.isArray(r.data?.overrides) ? r.data.overrides : [],
      count: typeof r.data?.count === 'number' ? r.data.count : 0,
    }));

// سجلّ التدقيق لمنطقة (GET /api/v1/calibration/{region}/audit) — قد لا تتوفّر النقطة
// بعد. صدق: نستهلكها إن نجحت، ونُعيد null عند 404 (لا تلفيق) فترتدّ المنضدة إلى
// overrides/all (source_ar + updated_at). أيّ خطأ آخر يُعاد null كذلك (أفضل-جهد).
// الشكل دفاعيّ (كلّ الحقول اختياريّة) لتفادي افتراض عقد غير مُثبَّت في هذا الفرع.
export interface CalibrationAuditEntry {
  action?:     string;
  field?:      string;
  old_value?:  unknown;
  new_value?:  unknown;
  source_ar?:  string | null;
  actor?:      string | null;
  created_at?: string | null;
  [k: string]: unknown;
}
export interface CalibrationAudit {
  region:  string;
  entries: CalibrationAuditEntry[];
}
/** يجلب سجلّ تدقيق منطقة. أفضل-جهد: 404 (نقطة غير متاحة) أو أيّ خطأ ⇒ null،
 *  فترتدّ المنضدة إلى overrides/all (حالة صادقة لا تلفيق). الأحدث أوّلاً يُتوقَّع
 *  من الخادم؛ نطبّع المصفوفة دفاعيّاً إن غابت/اختلف شكلها. */
export const fetchCalibrationAudit = (region: string): Promise<CalibrationAudit | null> =>
  kongApi
    .get<{ entries?: CalibrationAuditEntry[]; audit?: CalibrationAuditEntry[] }>(
      `/api/v1/calibration/${encodeURIComponent(region)}/audit`,
    )
    .then((r) => {
      const raw = r.data ?? {};
      const entries = Array.isArray(raw.entries)
        ? raw.entries
        : Array.isArray(raw.audit)
          ? raw.audit
          : [];
      return { region, entries };
    })
    .catch(() => null);

// ── سلسلة النَّسَب المُدامة + الدليل المتراكم (قراءة فقط) ──
// تُظهر للمستخدم أثر القرار المحفوظ ونتائجه التالية (decision → outcomes)، وتراكم
// الدليل الميدانيّ لكلّ منطقة نحو التحقّق. صدق: الدليل المتراكم تقديريّ غير مُعايَر
// (calibrated=false, source=persisted_outcomes) حتى تُجمَع عيّنات كافية — تُعرَض
// warnings_ar صراحةً. لا fallback وهميّ: الخطأ (404/503) يُرفع لتعرض الواجهة حالة صادقة.
export interface LineageDecision {
  decision_id:    string;
  field_id:       string;
  decision_type:  string;
  region:         string;
  stage:          string;
  decision_value: Record<string, unknown>;
  confidence:     number | null;
  created_by:     string;
  created_at:     string;
}
export interface LineageOutcome {
  outcome_id:  string;
  decision_id: string;
  field_id:    string;
  region:      string;
  stage:       string;
  planned:     Record<string, unknown>;
  actual:      Record<string, unknown>;
  metrics:     Record<string, unknown>;
  success:     boolean | null;
  created_at:  string;
}
export interface DecisionLineage {
  decision_id:    string;
  decision:       LineageDecision | null;
  outcomes:       LineageOutcome[];
  outcome_count:  number;
  stages_present: string[];
}
export const fetchDecisionLineage = (decisionId: string): Promise<DecisionLineage> =>
  kongApi
    .get<DecisionLineage>(`/api/v1/decision/${encodeURIComponent(decisionId)}/lineage`)
    .then(r => r.data);

export type EvidenceLevel = 'none' | 'field_preliminary' | 'field_verified' | 'expert_opinion';
export interface PersistedEvidence {
  region:                     string;
  sample_count:               number;
  evidence_level:             EvidenceLevel;
  success_rate:               number | null;
  success_flag_counts:        Record<string, number>;
  last_evaluated_at:          string | null;
  field_verified_min_samples: number;
  samples_to_verified:        number;
  calibrated:                 false;
  source:                     'persisted_outcomes';
  persisted_rows:             number;
  warnings_ar:                string[];
}
export const fetchPersistedEvidence = (region: string): Promise<PersistedEvidence> =>
  kongApi
    .get<PersistedEvidence>(`/api/v1/calibration/${encodeURIComponent(region)}/evidence/persisted`)
    .then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// AGRONOMIC REPLAY — إعادة تشغيل الموسم: خطّ زمنيّ واحد قابل للـscrub يعيد
// تشغيل موسم الحقل كاملاً (NDVI/طقس/ريّ/قرار/نتيجة ميدانيّة) من سجلّات مُدامة
// فقط. تستهلك GET /api/v1/fields/{field_id}/agronomic-replay.
// صدق: العلم مُطفأً (FEATURE_REPLAY_MAP) ⇒ 404؛ القاعدة غير متاحة ⇒ 503. span قد
// يكون null (لا أحداث) ⇒ حالة فارغة صادقة لا خطّ زمنيّ مخترَع. value متغايرة
// (رقم/منطقيّ/كائن/null) — تُصيَّر دفاعيّاً. الأحداث مرتّبة تصاعديّاً بالتاريخ.
// ══════════════════════════════════════════════════════════════════
export type ReplayTrackKey = 'ndvi' | 'weather' | 'irrigation' | 'decision' | 'outcome';

/** وصف مسار (track) واحد: المفتاح + تسميته العربيّة. */
export interface ReplayTrackMeta {
  track:    ReplayTrackKey;
  track_ar: string;
}
/** حدث واحد على الخطّ الزمنيّ. value متغايرة (رقم/منطقيّ/كائن/null). */
export interface ReplayEvent {
  date:     string;          // ISO (تاريخ فقط أو طابع زمنيّ كامل)
  track:    ReplayTrackKey;
  track_ar: string;
  label_ar: string;
  value:    number | boolean | Record<string, unknown> | null;
  ref_id:   string | null;
}
/** نتيجة إعادة التشغيل الكاملة (يطابق عقد agronomic-replay). */
export interface AgronomicReplayResult {
  field_id:        string;
  generated_at:    string;
  tracks:          ReplayTrackMeta[];
  events:          ReplayEvent[];
  counts_by_track: Record<string, number>;
  event_count:     number;
  span:            { start: string; end: string } | null; // null حين لا أحداث
  provenance:      { calibrated: string; note_ar: string };
  tenant_id:       string;
}

export const fetchAgronomicReplay = (fieldId: string): Promise<AgronomicReplayResult> =>
  kongApi
    .get<AgronomicReplayResult>(`/api/v1/fields/${encodeURIComponent(fieldId)}/agronomic-replay`)
    .then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// EVIDENCE MAP — خريطة الدليل (GET /api/v1/evidence/map) — قراءة فقط ──
// لكلّ حقل للمستأجِر: مستوى الدليل خلف قراراته (مؤكَّد/مدعوم/إرشاديّ/يحتاج بيانات)
// على خريطة 2D حقيقيّة + قائمة. خلف العلم FEATURE_EVIDENCE_MAP؛ مُطفأً ⇒ 404
// (تلتقطه الواجهة برسالة «الميزة غير مُفعَّلة»). 503 ⇒ القاعدة غير متاحة (حالة خطأ
// صادقة). صدق: مستوى الدليل من القرارات/القياسات المُدامة فقط؛ عتبة التحقّق الميدانيّ
// تقديريّة. الحقول بلا إحداثيّات (has_coords=false) لا تُرسَم (لا إحداثيّات مُختلَقة).
// needs_data «لا دليل بعد» صادق (رماديّ) لا حالة إيجابيّة. لا fallback وهميّ: الخطأ
// يُرفع لتعرض الواجهة حالة صادقة عبر .response?.status (مطابقةً لبقيّة صفحات العلم).
export type EvidenceMapTier =
  | 'field_verified' | 'field_preliminary' | 'indicative' | 'needs_data';
// لون الفئة من الخادم — يُربَط بألوان CSS/علامات محدّدة في الواجهة (لا فئات إضافيّة).
export type EvidenceMapColor = 'green' | 'amber' | 'blue' | 'gray';
export interface EvidenceMapLegendItem {
  tier:    EvidenceMapTier;
  tier_ar: string;
  color:   EvidenceMapColor | string;
}
export interface EvidenceMapField {
  field_id:            string;
  name:                string;
  crop:                string;
  gov:                 string;
  lat:                 number | null;
  lon:                 number | null;
  has_coords:          boolean;       // false ⇒ لا يُرسَم (لا إحداثيّات مُختلَقة)
  decisions:           number;
  outcomes:            number;
  successes:           number;
  success_rate:        number | null; // null ⇒ «—» (لا تلفيق)
  samples_to_verified: number;
  last_outcome_at:     string | null;
  tier:                EvidenceMapTier;
  tier_ar:             string;
  color:               EvidenceMapColor | string;
}
export interface EvidenceMapResult {
  generated_at:       string;
  legend:             EvidenceMapLegendItem[];
  fields:             EvidenceMapField[];
  totals_by_tier:     Record<string, number>;
  field_count:        number;
  plottable_count:    number;
  verified_threshold: number;
  provenance:         { calibrated: string; note_ar: string };
  tenant_id:          string;
}
/** يجلب خريطة الدليل (GET /api/v1/evidence/map) — قراءة فقط لا تنفيذ.
 *  يرمي عند الخطأ (404 العلم مُطفأ — تلتقطه الواجهة برسالة «الميزة غير مُفعَّلة»؛
 *  503 القاعدة غير متاحة تُعرَض كحالة خطأ صادقة). */
export const fetchEvidenceMap = (): Promise<EvidenceMapResult> =>
  kongApi.get<EvidenceMapResult>('/api/v1/evidence/map').then(r => r.data);

// ── توائم الأجهزة وثقة الحسّاس (Device Twin & Sensor Confidence) — قراءة فقط ──
// لكلّ جهاز IoT توأم رقميّ: هويّة + حالة + درجة صحّة/ثقة شفّافة (موزونة على الإشارات
// المتوفّرة فقط)، مع تلخيص ثقة الأسطول. صدق: missing_signals مُعلَنة لا مُفترَضة؛
// health_score/fleet_confidence قد تكون null ⇒ «غير محسوبة» لا 0. لا أوامر تشغيل.
// level من الخادم (healthy|degraded|stale|offline|poor|unknown) — تُربَط بألوان الواجهة.
export type DeviceTwinLevel =
  | 'healthy' | 'degraded' | 'stale' | 'offline' | 'poor' | 'unknown';
export interface DeviceTwin {
  device_id:       string;
  name:            string;
  type:            string;
  field_id:        string | null;
  status:          string;
  firmware:        string | null;
  age_sec:         number | null;            // ثوانٍ منذ آخر ظهور؛ null ⇒ لم يُرسِل بعد
  health_score:    number | null;            // 0..1، أو null عند الغياب ⇒ «—»
  level:           DeviceTwinLevel | string;
  level_ar:        string;
  factors:         Record<string, number>;   // الإشارات المتوفّرة فقط
  missing_signals: string[];                  // مُعلَنة لا مُفترَضة
  note_ar:         string | null;
}
export interface DeviceTwinResult {
  generated_at:     string;
  devices:          DeviceTwin[];
  device_count:     number;
  scored_count:     number;
  by_level:         Record<string, number>;
  fleet_confidence: number | null;           // متوسّط المُسجَّلين؛ null ⇒ «غير محسوبة»
  provenance:       { calibrated: string; note_ar: string };
  tenant_id:        string;
}
/** يجلب توائم الأجهزة (GET /api/v1/devices/twin) — قراءة فقط لا أوامر.
 *  يرمي عند الخطأ (404 العلم FEATURE_DEVICE_TWIN مُطفأ — تلتقطه الواجهة برسالة
 *  «الميزة غير مُفعَّلة»؛ 503 القاعدة غير متاحة تُعرَض كحالة خطأ صادقة). */
export const fetchDeviceTwin = (): Promise<DeviceTwinResult> =>
  kongApi.get<DeviceTwinResult>('/api/v1/devices/twin').then(r => r.data);

// ── رصد حلقة التنفيذ (Execution Feedback) — قراءة فقط ──
// تستهلك GET /api/v1/execution/feedback: لكلّ قرار حديث هل نُفِّذ (من سجلّ التنفيذ)
// وهل طابقت النتيجة الخطّة — إغلاق حلقة القرار→التنفيذ→النتيجة. لا إصدار أوامر ولا
// إعادة تنفيذ. صدق: loop_status من سجلّات مُدامة فقط؛ execution_unknown «يحتاج بيانات»
// (رماديّ) لا «نُفِّذ»؛ executed_unmeasured كهرمانيّ لا نجاح؛ closure_rate قد تكون null.
export type ExecutionLoopStatus =
  | 'closed_ok' | 'executed_off_plan' | 'executed_unmeasured' | 'execution_failed' | 'execution_unknown';
export interface ExecutionFeedbackDecision {
  decision_id:       string;
  decision_type:     string;
  field_id:          string | null;
  created_at:        string;
  execution_outcome: 'executed' | 'failed' | null; // null ⇒ لا قيد في سجلّ التنفيذ
  executed_at:       string | null;
  exec_note_ar:      string | null;
  outcome_measured:  boolean;
  outcome_success:   boolean | null;               // null حين لا تُقاس ⇒ «—» لا false
  loop_status:       ExecutionLoopStatus;
  loop_status_ar:    string;
  color:             'green' | 'red' | 'amber' | 'gray';
  note_ar:           string | null;                // تفسير صادق للحالة المجهولة/غير المقيسة
}
export interface ExecutionFeedbackResult {
  generated_at:   string;
  decisions:      ExecutionFeedbackDecision[];
  decision_count: number;
  by_status:      Record<ExecutionLoopStatus, number>;
  totals:         { executed: number; failed: number; measured: number; closed_ok: number };
  closure_rate:   number | null;                   // closed_ok/executed؛ null حين لا تنفيذ ⇒ «غير محسوبة»
  provenance:     { calibrated: string; note_ar: string };
  tenant_id:      string;
}
/** يجلب رصد حلقة التنفيذ (GET /api/v1/execution/feedback) — قراءة فقط لا أوامر.
 *  يرمي عند الخطأ (404 العلم FEATURE_EXECUTION_FEEDBACK مُطفأ — تلتقطه الواجهة برسالة
 *  «الميزة غير مُفعَّلة»؛ 503 القاعدة غير متاحة تُعرَض كحالة خطأ صادقة). */
export const fetchExecutionFeedback = (): Promise<ExecutionFeedbackResult> =>
  kongApi.get<ExecutionFeedbackResult>('/api/v1/execution/feedback').then(r => r.data);

// ── ثقة القرار الموحَّدة (Decision Confidence) — قراءة فقط، نطاق حقل ──
// GET /api/v1/fields/{id}/decision-confidence: درجة ثقة موحَّدة مدموجة من أربعة
// مصادر (حسّاس + دليل ميدانيّ + استشعار + طقس)، كلٌّ بوزنه وقيمته وتوفّره. صدق:
// confidence/level قد تكونان null/«insufficient» حين لا مصدر متاح ⇒ «غير كافية»
// (رماديّ) لا 0%. كلّ مكوّن يُعلِن available — غير المتوفّر رماديّ «يحتاج بيانات» لا
// مساهم بصفر. الدرجة المدموجة محسوبة خادميّاً على المتوفّر فقط — عرض فقط لا تعديل.
// العلم FEATURE_DECISION_CONFIDENCE مُطفأً ⇒ 404 (تلتقطه الواجهة برسالة «الميزة غير
// مُفعَّلة»)؛ 503 ⇒ القاعدة غير متاحة (حالة خطأ صادقة). لا fallback وهميّ.
export type DecisionConfidenceLevel = 'high' | 'medium' | 'low' | 'insufficient';
export interface DecisionConfidenceComponent {
  source:    string;          // sensor | evidence | satellite | weather
  label_ar:  string;
  weight:    number;          // 0..1
  value:     number | null;   // 0..1، أو null حين غير متوفّر ⇒ «—» (لا 0)
  available: boolean;         // false ⇒ رماديّ «يحتاج بيانات» (لا مساهم بصفر)
  detail_ar: string;
}
export interface DecisionConfidenceResult {
  generated_at:  string;
  confidence:    number | null;            // 0..1، أو null حين لا مصدر ⇒ «غير كافية» (لا 0)
  level:         DecisionConfidenceLevel | string;
  level_ar:      string;
  components:    DecisionConfidenceComponent[];
  present_count: number;
  missing:       string[];
  provenance:    { calibrated: string; note_ar: string };
  field_id:      string;
  tenant_id:     string;
}
/** يجلب ثقة القرار الموحَّدة لحقل (GET /api/v1/fields/{id}/decision-confidence) — قراءة فقط.
 *  يرمي عند الخطأ (404 العلم FEATURE_DECISION_CONFIDENCE مُطفأ — تلتقطه الواجهة برسالة
 *  «الميزة غير مُفعَّلة»؛ 503 القاعدة غير متاحة تُعرَض كحالة خطأ صادقة). */
export const fetchDecisionConfidence = (fieldId: string): Promise<DecisionConfidenceResult> =>
  kongApi
    .get<DecisionConfidenceResult>(`/api/v1/fields/${encodeURIComponent(fieldId)}/decision-confidence`)
    .then(r => r.data);

// ── لوحة رصد التعلّم/النَّسَب (قراءة فقط) — سرد القرارات المُدامة + تلخيص حلقة التعلّم ──
// تستهلك GET /api/v1/decision/records (سرد القرارات المُدامة للمستأجِر، معزولة بـRLS):
//   {decisions: DecisionRecord[], count}. شكل القرار مطابق لـ_shape_decision_row
//   (نفس LineageDecision: decision_id/field_id/decision_type/region/stage/decision_value/
//   confidence/created_by/created_at). صدق: لا fallback وهميّ — 503 (تعذّر القاعدة)
//   يُرفع لتعرض الواجهة حالة صادقة.
export type DecisionRecord = LineageDecision;
export interface DecisionRecordsResult {
  decisions: DecisionRecord[];
  count:     number;
}
export const fetchDecisionRecords = (limit = 200): Promise<DecisionRecordsResult> =>
  kongApi
    .get<DecisionRecordsResult>('/api/v1/decision/records', { params: { limit } })
    .then(r => ({
      decisions: Array.isArray(r.data?.decisions) ? r.data.decisions : [],
      count: typeof r.data?.count === 'number' ? r.data.count : 0,
    }));

// تلخيص حلقة التعلّم لكلّ منطقة (GET /api/v1/learning/summary) — قد لا تتوفّر النقطة بعد.
// صدق: نستهلكها إن نجحت، ونُعيد null عند 404/أيّ خطأ (لا تلفيق) فتعرض الواجهة حالةً
// فارغة صادقة بدل أرقام مُختلَقة. الشكل دفاعيّ (كلّ الحقول اختياريّة) لتفادي افتراض
// عقد غير مُثبَّت في هذا الفرع.
export interface LearningSummaryRegion {
  region?:                     string;
  sample_count?:               number;
  evidence_level?:             EvidenceLevel | string;
  success_rate?:               number | null;
  outcome_count?:              number;
  samples_to_verified?:        number;
  field_verified_min_samples?: number;
  calibrated?:                 boolean;
  warnings_ar?:                string[];
}
export interface LearningSummary {
  regions?:           LearningSummaryRegion[];
  decision_count?:    number;
  outcome_count?:     number;
  success_rate?:      number | null;
  regions_verified?:  number;
  calibrated?:        boolean;
  warnings_ar?:       string[];
  [k: string]:        unknown;
}
/** يجلب تلخيص حلقة التعلّم. أفضل-جهد: أيّ خطأ/استجابة غير صالحة (404 نقطة غير
 *  مُتاحة بعد، 503 DB) ⇒ null فتعرض الواجهة حالةً فارغة صادقة (لا تلفيق). */
export const fetchLearningSummary = (): Promise<LearningSummary | null> =>
  kongApi
    .get<LearningSummary>('/api/v1/learning/summary')
    .then((r) => (r.data && typeof r.data === 'object' ? r.data : null))
    .catch(() => null);

// ══════════════════════════════════════════════════════════════════
// DECISION STUDIO — شرح القرار (Signals → Policy → Constraints → Final) + إعادة
// التشغيل (قراءة فقط). تستهلك أوّلاً GET /api/v1/decision/{id}/explain (خلف العلم
// FEATURE_DECISION_STUDIO؛ قد يكون مُطفأً ⇒ 404)، وترتدّ عند 404 إلى السلسلة
// المُدامة GET /api/v1/decision/{id}/lineage فتشتقّ منها شرحاً صادقاً من
// decision_value (policy_decision.reasons_ar/risks/confidence). صدق: لا تلفيق —
// القرار غير المُدام يُعرَض «غير متاح»، وغياب المعايرة (calibrated=false) يُبرَز.
// ══════════════════════════════════════════════════════════════════

/** إشارة قرار واحدة (مدخَل أثّر في القرار) — مع حالة لونيّة صادقة من الخادم. */
export interface DecisionSignal {
  key:      string;
  label_ar: string;
  value:    unknown;
  status:   string; // ok | warn | risk | info | neutral … (من الخادم، لا نفترض حصراً)
}
/** قرار السياسة المُحلّ (auto/manual) مع أسبابه العربيّة. */
export interface DecisionPolicyView {
  resolved:   string | null;
  applied:    string | null;
  auto:       boolean;
  reasons_ar: string[];
}
/** قيد واحد على القرار (سقف ميزانيّة/تطبيق…). شكل مرن (الخادم قد يثريه). */
export interface DecisionConstraint {
  key?:      string;
  label_ar?: string;
  value?:    unknown;
  [k: string]: unknown;
}
/** جوهر الشرح: ثقة + إشارات + سياسة + قيود + القرار النهائيّ. */
export interface DecisionExplanation {
  confidence:  number | null;
  calibrated:  boolean;          // false ⇒ تقديريّ غير مُعايَر (يُبرَز صراحةً)
  signals:     DecisionSignal[];
  policy:      DecisionPolicyView | null;
  constraints: DecisionConstraint[];
  final:       Record<string, unknown>;
  warnings_ar: string[];
}
/** نتيجة الشرح الكاملة: شرح + «ماذا حدث فعلاً» (outcomes) + دليل. */
export interface DecisionExplainResult {
  decision_id:   string;
  decision_type: string;
  found:         boolean;        // false ⇒ القرار غير مُدام (لا نختلق شرحاً)
  source:        'explain' | 'lineage_derived'; // من أين جاء الشرح (شفافيّة)
  explanation:   DecisionExplanation | null;
  outcomes:      LineageOutcome[];
  evidence:      Record<string, unknown> | null;
}

// شكل ردّ /explain الخام من الخادم (حين يكون العلم مُفعَّلاً) — كلّ الحقول دفاعيّة.
interface RawExplainResponse {
  decision_id?:   string;
  decision_type?: string;
  found?:         boolean;
  explanation?: {
    confidence?:  number | null;
    calibrated?:  boolean;
    signals?:     Partial<DecisionSignal>[];
    policy?: {
      resolved?:   string | null;
      applied?:    string | null;
      auto?:       boolean;
      reasons_ar?: string[];
    } | null;
    constraints?: DecisionConstraint[];
    final?:       Record<string, unknown>;
    warnings_ar?: string[];
  } | null;
  outcomes?: LineageOutcome[];
  evidence?: Record<string, unknown> | null;
}

// يطبّع ردّ /explain الخام إلى DecisionExplainResult (حقول غائبة ⇒ افتراضات صادقة).
function _normalizeExplain(d: RawExplainResponse, decisionId: string): DecisionExplainResult {
  const ex = d.explanation ?? null;
  return {
    decision_id:   d.decision_id ?? decisionId,
    decision_type: d.decision_type ?? '—',
    found:         d.found ?? !!ex,
    source:        'explain',
    explanation: ex
      ? {
          confidence:  typeof ex.confidence === 'number' ? ex.confidence : null,
          calibrated:  ex.calibrated === true,
          signals:     (ex.signals ?? []).map((s) => ({
            key:      String(s.key ?? ''),
            label_ar: String(s.label_ar ?? s.key ?? ''),
            value:    s.value ?? null,
            status:   String(s.status ?? 'neutral'),
          })),
          policy: ex.policy
            ? {
                resolved:   ex.policy.resolved ?? null,
                applied:    ex.policy.applied ?? null,
                auto:       ex.policy.auto === true,
                reasons_ar: Array.isArray(ex.policy.reasons_ar) ? ex.policy.reasons_ar : [],
              }
            : null,
          constraints: Array.isArray(ex.constraints) ? ex.constraints : [],
          final:       ex.final && typeof ex.final === 'object' ? ex.final : {},
          warnings_ar: Array.isArray(ex.warnings_ar) ? ex.warnings_ar : [],
        }
      : null,
    outcomes: Array.isArray(d.outcomes) ? d.outcomes : [],
    evidence: d.evidence && typeof d.evidence === 'object' ? d.evidence : null,
  };
}

// يقرأ مصفوفة نصوص عربيّة بأمان من قيمة مجهولة (reasons_ar/risks/warnings الخام).
function _strList(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v
    .map((x) =>
      typeof x === 'string'
        ? x
        : typeof x === 'object' && x
          ? String(
              (x as Record<string, unknown>).label_ar ??
                (x as Record<string, unknown>).level_ar ??
                '',
            )
          : String(x ?? ''),
    )
    .filter(Boolean);
}

// يشتقّ شرحاً صادقاً من decision_value المُدام (ارتداد عند 404 على /explain).
// الإشارات تُبنى من الحقائق المُدامة فعلاً فقط (لا اختلاق): ثقة/سياسة/مخاطر/تحذيرات.
function _deriveFromLineage(lin: DecisionLineage): DecisionExplainResult {
  const dec = lin.decision;
  if (!dec) {
    return {
      decision_id:   lin.decision_id,
      decision_type: '—',
      found:         false,
      source:        'lineage_derived',
      explanation:   null,
      outcomes:      lin.outcomes,
      evidence:      null,
    };
  }
  const val = dec.decision_value ?? {};
  const pd = (val.policy_decision ?? null) as Record<string, unknown> | null;
  const confidence =
    typeof dec.confidence === 'number'
      ? dec.confidence
      : typeof val.confidence === 'number'
        ? (val.confidence as number)
        : null;
  const calibrated = val.calibrated === true;

  // إشارات من الحقائق المُدامة (كلّ إشارة مرتبطة بقيمة فعليّة موجودة — لا اختلاق).
  const signals: DecisionSignal[] = [];
  const ws = (val.water_state ?? null) as Record<string, unknown> | null;
  if (ws && typeof ws.needs_irrigation === 'boolean') {
    signals.push({
      key: 'needs_irrigation',
      label_ar: 'حاجة الريّ',
      value: ws.needs_irrigation ? 'نعم' : 'لا',
      status: ws.needs_irrigation ? 'warn' : 'ok',
    });
  }
  const irr = (val.irrigation ?? null) as Record<string, unknown> | null;
  if (irr && typeof irr.stress_days === 'number') {
    signals.push({
      key: 'stress_days',
      label_ar: 'أيّام الإجهاد',
      value: irr.stress_days,
      status: (irr.stress_days as number) > 0 ? 'risk' : 'ok',
    });
  }
  if (typeof val.data_quality === 'string') {
    signals.push({ key: 'data_quality', label_ar: 'جودة البيانات', value: val.data_quality, status: 'info' });
  }
  for (const r of (Array.isArray(val.risks) ? val.risks : []) as Record<string, unknown>[]) {
    if (r && typeof r === 'object') {
      signals.push({
        key: String(r.key ?? 'risk'),
        label_ar: String(r.label_ar ?? 'مخاطرة'),
        value: String(r.level_ar ?? ''),
        status: 'risk',
      });
    }
  }

  const policy: DecisionPolicyView | null = pd
    ? {
        resolved:   (pd.resolved_policy as string) ?? null,
        applied:    (pd.applied_policy as string) ?? null,
        auto:       pd.auto === true,
        reasons_ar: _strList(pd.reasons_ar),
      }
    : null;

  // القيود: سقوف التطبيق/الميزانيّة إن أُدِيمت فعلاً (لا نخترعها).
  const constraints: DecisionConstraint[] = [];
  if (irr && irr.policy != null) constraints.push({ key: 'policy', label_ar: 'سياسة الريّ', value: irr.policy });
  if (irr && irr.total_mm != null) constraints.push({ key: 'total_mm', label_ar: 'إجماليّ الريّ (مم)', value: irr.total_mm });

  // القرار النهائيّ: ملخّص الأفعال المُدامة (ريّ/تسميد) — أرقام حقيقيّة لا مُلفَّقة.
  const final: Record<string, unknown> = {};
  if (irr && irr.action_ar != null) final['الريّ'] = irr.action_ar;
  const fert = (val.fertilization ?? null) as Record<string, unknown> | null;
  if (fert && fert.action_ar != null) final['التسميد'] = fert.action_ar;

  return {
    decision_id:   lin.decision_id,
    decision_type: dec.decision_type,
    found:         true,
    source:        'lineage_derived',
    explanation: {
      confidence,
      calibrated,
      signals,
      policy,
      constraints,
      final,
      warnings_ar: _strList(val.warnings_ar),
    },
    outcomes: lin.outcomes,
    evidence: null,
  };
}

/** يجلب شرح القرار: يجرّب /explain أوّلاً، ويرتدّ عند 404 (العلم مُطفأ) إلى
 *  /lineage فيشتقّ شرحاً صادقاً من decision_value. أيّ خطأ آخر (503/403) يُرفع
 *  لتعرض الواجهة حالة خطأ صادقة. */
export const fetchDecisionExplain = (decisionId: string): Promise<DecisionExplainResult> => {
  const id = decisionId.trim();
  return kongApi
    .get<RawExplainResponse>(`/api/v1/decision/${encodeURIComponent(id)}/explain`)
    .then((r) => _normalizeExplain(r.data ?? {}, id))
    .catch((e: unknown) => {
      // 404 فقط ⇒ العلم FEATURE_DECISION_STUDIO مُطفأ/النقطة غير موجودة: ارتدّ للنسَب.
      if (asApiError(e).response?.status === 404) {
        return fetchDecisionLineage(id).then(_deriveFromLineage);
      }
      throw e;
    });
};

// ══════════════════════════════════════════════════════════════════
// AGRONOMIC TIMELINE — الخطّ الزمنيّ الموحّد للحقل (مثل Git history، قراءة فقط).
// تستهلك GET /api/v1/fields/{field_id}/unified-timeline (assemble_timeline:
// تصنيف+فرز+إحصاءات عبر RLS). صدق: عند تعطّل القاعدة يُرجِع خطّاً فارغاً + note_ar
// (لا تاريخ مخترَع) — تعرضه الواجهة EmptyState. لا fallback وهميّ.
// ══════════════════════════════════════════════════════════════════
export type AgronomicTimelineCategory =
  | 'lifecycle' | 'operation' | 'observation' | 'calibration' | 'weather' | 'system' | string;

/** حدث واحد في الخطّ الزمنيّ (يطابق TimelineEvent.to_dict الخلفيّ). */
export interface UnifiedTimelineEvent {
  timestamp:   string;
  event_type:  string;
  category:    AgronomicTimelineCategory;
  summary_ar:  string;
  actor_id:    string | null;
  payload:     Record<string, unknown>;
}
/** الخطّ الزمنيّ الكامل (يطابق FieldTimeline.to_dict). */
export interface UnifiedTimeline {
  field_id:        string;
  total_events:    number;
  earliest_at:     string | null;
  latest_at:       string | null;
  category_counts: Record<string, number>;
  events:          UnifiedTimelineEvent[];
  note_ar?:        string; // يظهر عند تعطّل القاعدة (لا تاريخ حيّ) — حالة فارغة صادقة
  error?:          string; // يظهر عند فشل الجلب الداخليّ (الخادم يُعلنه لا يخترع)
}

export const fetchUnifiedTimeline = (
  fieldId: string,
  opts: { limit?: number; newestFirst?: boolean; category?: string } = {},
): Promise<UnifiedTimeline> => {
  const { limit = 200, newestFirst = true, category } = opts;
  return kongApi
    .get<UnifiedTimeline>(`/api/v1/fields/${encodeURIComponent(fieldId)}/unified-timeline`, {
      params: {
        limit,
        newest_first: newestFirst,
        ...(category ? { category } : {}),
      },
    })
    .then((r) => {
      const d = r.data ?? ({} as UnifiedTimeline);
      return {
        field_id:        d.field_id ?? fieldId,
        total_events:    typeof d.total_events === 'number' ? d.total_events : 0,
        earliest_at:     d.earliest_at ?? null,
        latest_at:       d.latest_at ?? null,
        category_counts: d.category_counts && typeof d.category_counts === 'object' ? d.category_counts : {},
        events:          Array.isArray(d.events) ? d.events : [],
        note_ar:         d.note_ar,
        error:           d.error,
      };
    });
};

// ── قرار المحصول الموحّد (POST /api/v1/crop-twin/decision) ──
// ريّ + تسميد + مخاطر + ثقة من حالة محصول واحدة. الاقتصاد محجوز (not_configured).
export interface CropDecisionForecastDay {
  t_min_c: number; t_max_c: number; et0_mm: number;
  kc?: number | null; rain_mm?: number; irrigation_mm?: number; runoff_mm?: number;
}
export interface CropDecisionInput {
  field_id?: string | null;
  crop?: string | null;
  stage?: string;
  forecast: CropDecisionForecastDay[];
  ndvi?: number | null;
  soil?: { texture?: string | null; root_depth_m?: number | null; raw_fraction?: number; taw_mm?: number | null };
  management?: { target_uptake_kg_ha?: number; initial_depletion_mm?: number; auto_irrigate?: boolean };
  policy?: string;
  max_application_mm?: number | null;
  season_budget_mm?: number | null;
  water_price_per_m3?: number | null;
  yield_value_per_ha?: number | null;
}
export interface UnifiedRisk { key: string; label_ar: string; level_ar: string }
export interface UnifiedFlag { code: string; label_ar: string }
export interface CropDecisionResult {
  crop: string | null;
  crop_known: boolean;
  dynamic_kc: number;
  phenology: { stage: string; progress: number; past_maturity: boolean; gdd_cumulative?: number };
  water_state: { taw_mm: number; raw_mm: number; depletion_mm: number; depletion_pct?: number; needs_irrigation: boolean };
  nutrient_state: { stage: string | null; target_uptake_kg_ha: number; uptake_to_date_kg_ha: number };
  irrigation: {
    policy: string; total_mm: number; n_events: number;
    next_event_day: number | null; next_event_mm: number; stress_days: number; action_ar: string;
  };
  fertilization: {
    stage: string | null; uptake_to_date_kg_ha: number; remaining_need_kg_ha: number; due: boolean; action_ar: string;
  };
  risks: UnifiedRisk[];
  stress_flags: UnifiedFlag[];
  confidence: number;
  data_quality: string;
  assumptions: string[];
  assumptions_ar: string[];
  economic_state: EconomicState;
  calibrated: boolean;
  warnings_ar: string[];
}
export interface EconomicState {
  status: string;                       // not_configured | partial | ok
  required_inputs?: string[];
  gross_revenue?: number | null;
  water_cost?: number | null;
  energy_cost?: number | null;
  fertilizer_cost?: number | null;
  total_cost?: number | null;
  expected_margin?: number | null;
  margin_uncertainty?: number | null;
  confidence?: number;
  missing_inputs?: string[];
}
export const computeCropDecision = (payload: CropDecisionInput): Promise<CropDecisionResult> =>
  kongApi.post<CropDecisionResult>('/api/v1/crop-twin/decision', payload).then(r => r.data);

// ── القرار الواعي بالربح (POST /api/v1/crop-twin/decision/profit-aware) ──
export interface ProfitAwareDecisionInput extends CropDecisionInput {
  auto_policy?: boolean;
  water_source?: string | null;
  water_cost?: string | null;
  energy_cost?: string | null;
  region?: string | null;
  expected_yield_t_ha?: number | null;
  crop_price_per_t?: number | null;
  energy_kwh_ha?: number | null;
  energy_price_per_kwh?: number | null;
  fertilizer_price_per_kg?: number | null;
}
export interface PolicyDecision {
  resolved_policy: string;
  applied_policy: string;
  auto: boolean;
  reasons_ar: string[];
}
export interface ProfitAwareDecisionResult extends CropDecisionResult {
  policy_decision: PolicyDecision;
}
export const computeProfitAwareDecision = (payload: ProfitAwareDecisionInput): Promise<ProfitAwareDecisionResult> =>
  kongApi.post<ProfitAwareDecisionResult>('/api/v1/crop-twin/decision/profit-aware', payload).then(r => r.data);

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

// ── مواسم الحقل (مع نتائج المحاكاة المُخزَّنة sim_*) — حيّة عبر البوّابة ──
// GET /api/v1/fields/{field_id}/seasons (SeasonSummary[]، الأحدث أولاً، tenant-scoped
// + FIELD_VIEW). حقول sim_* تكون مملوءة فقط بعد تشغيل /simulate (تقديريّة)، وإلّا null
// ⇒ تعرضها الواجهة كحالة "—" صادقة لا أرقاماً مُلفَّقة. لا fallback وهميّ.
export interface SeasonSummary {
  season_id:        string;
  field_id:         string;
  crops:            string[];
  cultivar:         string | null;
  irrigation_type:  string | null;
  seed_rate_kg_ha:  number | null;
  land_leveling_date: string | null;
  plowing_date:     string | null;
  sowing_date:      string | null;
  season_end:       string | null;
  stages:           Record<string, unknown>[];
  status:           string; // active | closed | ...
  created_at:       string | null;
  // مؤشّرات الموسم الزراعيّة (v42) — تُدخَل عند الإنشاء/التحديث، وإلّا null
  target_yield_kg_ha:  number | null; // الغلّة المستهدفة كجم/هـ
  plant_density:       number | null; // كثافة النبات (نبتة/م²)
  row_spacing_cm:      number | null; // المسافة بين الخطوط (سم)
  seed_variety_source: string | null; // مصدر/صنف البذور
  // حقول أغرونوميّة (v52) — اختياريّة، وإلّا null
  maturity:            string | null; // فترة النضج (early/medium/late)
  tillage_type:        string | null; // نوع الحراثة
  actual_yield_kg_ha:  number | null; // الغلّة الفعليّة بعد الحصاد كجم/هـ
  notes_ar:            string | null; // ملاحظات
  // نتائج المحاكاة (تُملأ عند تشغيل /simulate، وإلّا null — تقديريّة بنطاق وثقة)
  sim_yield_kg_ha:   number | null;
  sim_biomass_kg_ha: number | null;
  sim_gdd_total:     number | null;
  sim_lai_max:       number | null;
  sim_water_mm:      number | null;
  sim_ran_at:        string | null;
}

export const fetchSeasons = (fieldId: string): Promise<SeasonSummary[]> =>
  kongApi.get<SeasonSummary[]>(`/api/v1/fields/${fieldId}/seasons`).then(r => (Array.isArray(r.data) ? r.data : []));

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
  kongApi.get<InventoryItem[]>('/api/v1/inventory/items').then(r => (Array.isArray(r.data) ? r.data : []));

export const getExpiringBatches = (days = 30): Promise<ExpiringBatch[]> =>
  kongApi.get<ExpiringBatch[]>('/api/v1/inventory/expiring', { params: { days } }).then(r => (Array.isArray(r.data) ? r.data : []));

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
  kongApi.get<Equipment[]>('/api/v1/equipment').then(r => (Array.isArray(r.data) ? r.data : []));

export const createEquipment = (payload: EquipmentCreateInput): Promise<Equipment> =>
  kongApi.post<Equipment>('/api/v1/equipment', payload).then(r => r.data);

export const fetchMaintenance = (equipmentId: string): Promise<MaintenanceRecord[]> =>
  kongApi.get<MaintenanceRecord[]>(`/api/v1/equipment/${equipmentId}/maintenance`).then(r => (Array.isArray(r.data) ? r.data : []));

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
  kongApi.get<Activity[]>(`/api/v1/fields/${fieldId}/activities`).then(r => (Array.isArray(r.data) ? r.data : []));

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
  safety?:   boolean;   // توصية سلامة (تُبرَز) — تُرسلها الخلفيّة (recommendations_hub)
}

// حالة الحقل القانونيّة المُرفقة بالتوصيات (تُرسلها الخلفيّة أصلاً — Provenance UX).
export interface RecFieldState {
  validity?:         string;
  execution_mode?:   string;
  confidence_level?: string | null;  // high | medium | low | none — نصّ لا رقم
  reasons_ar?:       string[];
}

export interface FieldRecommendationsResult {
  field_id:           string;
  crop:               string | null;
  stage:              string;
  weather_available:  boolean;
  recommendations:    FieldRecommendation[];
  requires_review?:   boolean;        // execution_mode != auto ⇒ مراجعة بشريّة
  field_state?:       RecFieldState;
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
  kongApi.get<AlertRecord[]>('/api/v1/alerts', { params: filters }).then(r => (Array.isArray(r.data) ? r.data : []));

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
  kongApi.get<Device[]>('/api/v1/devices').then(r => (Array.isArray(r.data) ? r.data : []));

/** تسجيل جهاز جديد (device:manage). */
export const registerDevice = (payload: DeviceRegisterInput): Promise<Device> =>
  kongApi.post<Device>('/api/v1/devices', payload).then(r => r.data);

/** قياسات حديثة لجهاز (device:view). */
export const getDeviceTelemetry = (deviceId: string, limit = 20): Promise<TelemetryPoint[]> =>
  kongApi.get<TelemetryPoint[]>(`/api/v1/devices/${deviceId}/telemetry`, { params: { limit } }).then(r => (Array.isArray(r.data) ? r.data : []));

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
  kongApi.get<Valve[]>('/api/v1/irrigation/valves').then(r => (Array.isArray(r.data) ? r.data : []));

export const createValve = (payload: CreateValveInput): Promise<Valve> =>
  kongApi.post<Valve>('/api/v1/irrigation/valves', payload).then(r => r.data);

export const setValveState = (valveId: string, status: ValveStateIntent): Promise<Valve> =>
  kongApi.post<Valve>(`/api/v1/irrigation/valves/${valveId}/state`, { status }).then(r => r.data);

export const listSchedules = (fieldId?: string): Promise<IrrigationSchedule[]> =>
  kongApi.get<IrrigationSchedule[]>('/api/v1/irrigation/schedules', {
    params: fieldId ? { field_id: fieldId } : {},
  }).then(r => (Array.isArray(r.data) ? r.data : []));

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
  kongApi.get<MasterDataEntry[]>('/api/v1/master-data', { params: { category } }).then(r => (Array.isArray(r.data) ? r.data : []));

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
  }).then(r => (Array.isArray(r.data) ? r.data : []));

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
  kongApi.get<Farm[]>('/api/v1/farms').then(r => (Array.isArray(r.data) ? r.data : []));

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
  // ملفّ الريّ/المياه التفصيليّ (v41) — يعيدها الخادم؛ تُعرَض للقراءة بحالة "—" صادقة
  irrigation_type?:           string | null;
  irrigation_efficiency_pct?: number | null;
  flow_rate_m3h?:             number | null; // تدفّق المضخّة م³/ساعة
  pump_type?:                 string | null;
  well_depth_m?:              number | null;
  water_ec?:                  number | null; // ملوحة الماء dS/m
  zone_key?:                  string | null; // مفتاح الإقليم القانوني (v49)
  manager_user_id?:           number | null; // FK إلى users(id) (v47)
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
// FIELD WORKSPACE — مساحة عمل الحقل (المصدر الأساسيّ لكرت «Field Workspace Map»)
// GET /api/v1/fields/{field_id}/workspace (fields.py:508 ⇒ assemble_workspace):
// ملخّص الحقل + كتالوج طبقات قابلة للتبديل (كلّ طبقة تُعلن توفّرها بصدق:
// available/on_demand/missing) + تفسير التضاريس + خطّ زمنيّ من أحداث مسجّلة فقط.
// عرض صرف (display_only) — لا قرار مفروض. لا fallback وهميّ: عند الخطأ (404 حقل
// ليس للمستأجِر / 503 DB) يُرمى ليعرض الـUI حالة صادقة. الحدود (geometry) تُجلب
// عبر fetchFieldDetail، وطبقة NDVI الحقيقيّة من خدمة الراستر (rasterApi) عند الطلب.
// ══════════════════════════════════════════════════════════════════

/** حالة توفّر طبقة كما يُعلنها الخادم بصدق. */
export type WorkspaceLayerStatus = 'available' | 'on_demand' | 'missing';

/** طبقة عرض واحدة في كتالوج مساحة العمل (display_only — لا تفرض قراراً). */
export interface WorkspaceLayer {
  key:          string;
  label_ar:     string;
  category:     string; // vegetation | terrain | soil | water
  available:    boolean;
  status:       WorkspaceLayerStatus | string;
  display_only: boolean;
  note_ar:      string;
}

/** ملخّص الحقل المُضمَّن في مساحة العمل (مأخوذ من أعمدة الحقل، قد يكون null). */
export interface WorkspaceFieldSummary {
  name_ar:   string | null;
  crop:      string | null;
  area_ha:   number | null;
  soil_type: string | null;
}

/** بطاقة خطّ زمنيّ واحدة (من أحداث مسجّلة فقط — لا تاريخ مخترَع). */
export interface WorkspaceTimelineCard {
  occurred_at: string;
  event_type:  string;
  op_ar:       string;
  category:    string;
  issue_tags:  string[];
}

/** تفسير التضاريس المُضمَّن (enrich_terrain) — شكل مفتوح، اختياريّ بالكامل. */
export interface WorkspaceTerrain {
  field_id?:        string;
  elevation_m?:     number | null;
  slope_pct?:       number | null;
  aspect?:          string | null;
  [k: string]:      unknown;
}

/** مساحة عمل الحقل الكاملة (GET /workspace) — عرض صرف. */
export interface FieldWorkspace {
  field_id:               string | null;
  display_only:           boolean;
  field:                  WorkspaceFieldSummary;
  layers:                 WorkspaceLayer[];
  available_layer_count:  number;
  terrain:                WorkspaceTerrain | null;
  timeline:               WorkspaceTimelineCard[];
  timeline_total:         number;
  honesty_note_ar:        string;
}

/** يجلب مساحة عمل الحقل (field:view). 404 لو ليس للمستأجِر، 503 عند تعطيل DB.
 *  لا fallback وهميّ — الخطأ يُرمى ليعرض الـUI حالة صادقة. */
export const fetchFieldWorkspace = (
  fieldId: string,
  timelineLimit = 50,
): Promise<FieldWorkspace> =>
  kongApi
    .get<FieldWorkspace>(`/api/v1/fields/${fieldId}/workspace`, {
      params: { timeline_limit: timelineLimit },
    })
    .then(r => r.data);

/** قاعدة عنوان خدمة الراستر (بلا شرطة لاحقة) — لبناء رابط قالب بلاطات NDVI
 *  الحقيقيّة ({z}/{x}/{y}) التي يفسّرها Leaflet. نفس مصدر FieldIndicatorMap. */
export const rasterBaseUrl = (): string =>
  (rasterApi.defaults.baseURL || '').replace(/\/+$/, '');

/** رابط قالب بلاطات مؤشّر حقل من خدمة الراستر (NDVI افتراضيّاً). نُبقي
 *  {z}/{x}/{y} حرفيّاً ليفسّرها Leaflet. لا تلوين مفبرك: إن لم تتوفّر صورة COG
 *  صافية للحقل/التاريخ تُرجِع الخدمة بلاطات فارغة (لا طبقة مُختلَقة). */
export const fieldIndicatorTileUrl = (
  fieldId: string,
  index = 'ndvi',
  date = 'latest',
): string => {
  const qs = `index=${encodeURIComponent(index)}&date=${encodeURIComponent(date)}`;
  // eslint-disable-next-line no-template-curly-in-string
  return `${rasterBaseUrl()}/v1/fields/${fieldId}/tiles/{z}/{x}/{y}.png?${qs}`;
};

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
// FLEET HEALTH — صحّة أسطول الأجهزة (كشف استباقي للأجهزة الصامتة، مرتّب بالخطورة).
// تستهلك GET /api/v1/devices/fleet-health (devices.py ⇒ assess_fleet): ملخّص عدديّ
// + قائمة الأجهزة الصامتة. مُقيَّد device:view. لا fallback وهميّ: عند الخطأ (503 DB
// مُعطَّلة / 403 RBAC) يُرمى ليعرض الـUI حالة صادقة (بلاطة المعدّات لها حالة خطأ مستقلّة).
// ══════════════════════════════════════════════════════════════════
export type DeviceCriticalityLevel = 'critical' | 'important' | 'optional';

/** جهاز صامت واحد في تقرير صحّة الأسطول (مرتّب: الحرج أوّلاً). */
export interface SilentDeviceHealth {
  device_id:            string;
  name:                 string;
  type:                 string;
  field_id:             string | null;
  silent:               boolean;
  criticality:          DeviceCriticalityLevel | string;
  detail_ar:            string;
  criticality_note_ar:  string;
  threshold_minutes:    number;
}

/** صحّة الأسطول كاملة (ملخّص عدديّ + الأجهزة الصامتة مرتّبة بالخطورة). */
export interface FleetHealth {
  total_devices:    number;
  online:           number;
  silent:           number;
  critical_silent:  number;
  fleet_status_ar:  string;
  silent_devices:   SilentDeviceHealth[];
  proactive_note_ar?: string;
}

/** يجلب صحّة الأسطول (device:view). الخطأ (503/403) يُرفع لحالة صادقة. نطبّع
 *  silent_devices دفاعيّاً إن اختلف شكلها (لا انهيار .map). */
export const fetchFleetHealth = (): Promise<FleetHealth> =>
  kongApi.get<FleetHealth>('/api/v1/devices/fleet-health').then((r) => {
    const d = (r.data ?? {}) as Partial<FleetHealth>;
    return {
      total_devices:   typeof d.total_devices === 'number' ? d.total_devices : 0,
      online:          typeof d.online === 'number' ? d.online : 0,
      silent:          typeof d.silent === 'number' ? d.silent : 0,
      critical_silent: typeof d.critical_silent === 'number' ? d.critical_silent : 0,
      fleet_status_ar: typeof d.fleet_status_ar === 'string' ? d.fleet_status_ar : '',
      silent_devices:  Array.isArray(d.silent_devices) ? d.silent_devices : [],
      proactive_note_ar: typeof d.proactive_note_ar === 'string' ? d.proactive_note_ar : undefined,
    };
  });

// ══════════════════════════════════════════════════════════════════
// OPERATION CENTER WALL — التلخيص التشغيليّ الموحّد للمستأجِر (جدار مركز العمليّات).
// المصدر الأساسيّ: GET /api/v1/operations/summary خلف العلم FEATURE_OPERATIONS_WALL
// (حقول/تنبيهات بالخطورة/معدّات+أجهزة/قرارات/ريّ). أفضل-جهد: قد يكون العلم مُطفأً أو
// النقطة غير منشورة ⇒ 404. fetchOperationsSummary يُرجِع null عند 404/أيّ خطأ (لا
// تلفيق)، فترتدّ الصفحة إلى النقاط المنفصلة لكلّ بلاطة (تدهور رشيق، صدق المصدر).
// كلّ الحقول اختياريّة (عقد غير مُثبَّت في هذا الفرع) ⇒ قراءة دفاعيّة، لا any.
// ══════════════════════════════════════════════════════════════════
export interface OpsSeverityCounts {
  critical?: number;
  warning?:  number;
  info?:     number;
}

export interface OperationsSummary {
  fields_total?:    number | null;
  alerts?:          OpsSeverityCounts | null;
  alerts_total?:    number | null;
  fleet?:           Partial<FleetHealth> | null;
  decisions_total?: number | null;
  irrigation?: {
    valves_total?:    number | null;
    valves_open?:     number | null;
    schedules_total?: number | null;
  } | null;
  generated_at?:    string | null;
  // صدق التشغيل (source/freshness-aware): partial=أيّ قسم ليس ok؛ sections لكلّ قسم
  // status حيّ/متدهور/غير متاح + عمر البيانات + سبب — يُمكّن الجدار من إظهار ما هو
  // حيّ وما هو متدهور وما هو غير متاح بصدق (لا تلفيق).
  partial?:         boolean | null;
  sections?:        Record<
    string,
    { status: 'ok' | 'degraded' | 'unavailable'; freshness_sec?: number; error?: string }
  > | null;
  [k: string]:      unknown;
}

/** يجلب التلخيص التشغيليّ الموحّد. أفضل-جهد: 404 (العلم مُطفأ / النقطة غير منشورة)
 *  أو أيّ خطأ/استجابة غير كائن ⇒ null، فترتدّ الصفحة لكلّ بلاطة لنقطتها المنفصلة.
 *  لا تلفيق: null حالةٌ صريحة لا خطأ. */
export const fetchOperationsSummary = (): Promise<OperationsSummary | null> =>
  kongApi
    .get<OperationsSummary>('/api/v1/operations/summary')
    .then((r) => (r.data && typeof r.data === 'object' && !Array.isArray(r.data) ? r.data : null))
    .catch(() => null);

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
