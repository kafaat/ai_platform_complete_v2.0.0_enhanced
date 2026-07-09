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
import { clearAccessToken, getAccessToken, getTenantId } from '../../lib/authStorage';
import { isAccessTokenExpired } from '../../lib/jwt';
import { ENDPOINTS } from '../../config/endpoints';

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
      // UI hotfix: 401 من خدمة ميزة (vegetation/raster…) لا يعني بالضرورة انتهاء جلسة
      // المنصّة (قد تُرجِعه الخدمة لسبب داخليّ خاصّ بها)، فطردُ المستخدم لتسجيل الدخول عليه
      // مُضلِّل. نحصر الخروج القسريّ في نقاط auth (تسجيل/تحقّق/تجديد) — دلالة انتهاء
      // الاعتماد الفعليّة. انتهاء التوكن الحقيقيّ يلتقطه فحص الصلاحيّة جهة-العميل أعلاه.
      const url = String(err.config?.url || '');
      const isAuthEndpoint = url.startsWith('/auth/');
      if (isAuthEndpoint && err.response?.status === 401) {
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
export async function tryReal<T>(fn: () => Promise<T>, fallback: () => T): Promise<T> {
  if (MOCK_MODE) return fallback();
  return fn();
}

