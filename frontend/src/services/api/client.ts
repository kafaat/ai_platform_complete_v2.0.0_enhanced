// ═══════════════════════════════════════════════════════════════
// SAHOOL v9.0 — Unified API Client
// ربط حقيقي مع 6 خدمات خلفية + mock fallback ذكي
//
// الخدمات:
//   indicators-service  → :8091  (ownership/catalog contract only)
//   vegetation-service  → :8090  (7 مؤشرات Sentinel-2)
//   weather-service     → :8092  (الطقس + WOFOST format)
//   soil-service        → :8094  (تربة + N recommendation)
//   satellite-tiles     → :8098  (XYZ tiles)
//   auth-service        → :8120  (JWT)
//   kong-gateway        → :8000  (البوابة الموحدة)
// ═══════════════════════════════════════════════════════════════

import axios, { type AxiosInstance, type AxiosResponse } from 'axios';
import { clearAccessToken, getAccessToken, getTenantId, getAuthScope } from '../../lib/authStorage';
import { isAccessTokenExpired } from '../../lib/jwt';
import { ENDPOINTS } from '../../config/endpoints';

declare module 'axios' {
  interface AxiosRequestConfig { expectedAuthScope?: string; sahoolRequestAccessToken?: string | null; }
}

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
const KONG_URL       = ENDPOINTS.kong;
const AUTH_URL       = ENDPOINTS.auth;
const RASTER_URL     = ENDPOINTS.raster;
const VEGETATION_URL = ENDPOINTS.vegetation;
const INDICATORS_URL = ENDPOINTS.indicators;
const WEATHER_URL    = ENDPOINTS.weather;
const SOIL_URL       = ENDPOINTS.soil;
export const MOCK_MODE      = import.meta.env.VITE_MOCK_MODE === 'true' || false;

// ── Axios instances ────────────────────────────────────────────
// حارس: لو رجع HTML (SPA fallback لمسار API غير مُوجَّه) بدل JSON ⇒ عامله خطأً
// بدل تمرير نصّ HTML للمكوّنات فتنهار (مثل alerts.slice(...).map is not a function).
function rejectHtmlResponse(r: AxiosResponse): AxiosResponse | Promise<never> {
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
}

function makeClient(baseURL: string): AxiosInstance {
  const client = axios.create({ baseURL, timeout: 15000, headers: { 'Content-Type': 'application/json' } });
  // JWT interceptor
  client.interceptors.request.use((config) => {
    // MAP-05: a request bound to a session (tenant + user) must never leave under another one.
    if (config.expectedAuthScope && config.expectedAuthScope !== getAuthScope()) {
      return Promise.reject(new Error('session changed before request'));
    }
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
    config.sahoolRequestAccessToken = token;
    return config;
  });
  // 401 → logout
  client.interceptors.response.use(
    rejectHtmlResponse,
    (err) => {
      // UI hotfix: 401 من خدمة ميزة (vegetation/raster…) لا يعني بالضرورة انتهاء جلسة
      // المنصّة (قد تُرجِعه الخدمة لسبب داخليّ خاصّ بها)، فطردُ المستخدم لتسجيل الدخول عليه
      // مُضلِّل. نحصر الخروج القسريّ في نقاط auth (تسجيل/تحقّق/تجديد) — دلالة انتهاء
      // الاعتماد الفعليّة. انتهاء التوكن الحقيقيّ يلتقطه فحص الصلاحيّة جهة-العميل أعلاه.
      const url = String(err.config?.url || '');
      const isAuthEndpoint = url.startsWith('/auth/');
      if (isAuthEndpoint && err.response?.status === 401 &&
          err.config?.sahoolRequestAccessToken === getAccessToken()) {
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

// ── عميل «إثبات تسجيل MFA» (bootstrap enrollment) ────────────────
// /auth/mfa/setup و/auth/mfa/activate في تدفّق الحساب الحسّاس غير المُسجَّل يُصادَقان
// بـ`Authorization: Bearer <enrollment_token>` (إثبات كلمة مرور قصير الأجل، لمرّة واحدة)
// لا بتوكن الجلسة. لذا عميلٌ مستقلّ عن makeClient عمداً:
//   • لا interceptor طلب: لا يكتب فوق الترويسة الصريحة توكناً مخزَّناً (قديماً أو لحساب
//     آخر)، ولا يرفض الطلب ويُطلق خروجاً لأنّ توكناً مخزَّناً انتهى، ولا يُرسل X-Tenant-ID
//     (الإثبات يحمل هويّته؛ لا مستأجِر قبل الدخول).
//   • لا 401→logout: انتهاء الإثبات أو استهلاكه (401) يُعالَج في شاشة التسجيل نفسها
//     («سجّل الدخول من جديد»)، لا بمسح جلسة وإطلاق 'sahool:auth:unauthorized'.
// يبقى حارس HTML وحده. الإثبات يُمرَّر لكلّ طلب ولا يُخزَّن هنا ولا في أيّ Storage.
function makeEnrollmentProofClient(baseURL: string): AxiosInstance {
  const client = axios.create({ baseURL, timeout: 15000, headers: { 'Content-Type': 'application/json' } });
  client.interceptors.response.use(rejectHtmlResponse);
  return client;
}

export const authEnrollmentApi = makeEnrollmentProofClient(AUTH_URL);

// ── Helper: real data, with mock ONLY in explicit MOCK_MODE ───────
// H2 FIX: لا يجوز لمنصّة قرار زراعي أن تُلفّق توصيات تسميد/ريّ ثابتة عند فشل
// الخادم (انقطاع/مهلة) وتعرضها كأنّها حقيقيّة — ضرر زراعي ومالي حقيقي. الآن
// الـmock يقتصر على وضع التجريب الصريح (VITE_MOCK_MODE)، وأخطاء الإنتاج
// تُرمى ليتعامل معها الـUI (حالة خطأ/بيانات قديمة) بدل قيمة مخترعة صامتة.
export async function tryReal<T>(fn: () => Promise<T>, fallback: () => T): Promise<T> {
  if (MOCK_MODE) return fallback();
  return fn();
}

