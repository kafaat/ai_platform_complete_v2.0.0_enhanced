// ═══════════════════════════════════════════════════════════════
// SAHOOL — أساس عملاء HTTP (مُستخرَج من api.ts)
// عملاء axios السبعة + المُعترِضات (JWT/401/HTML-guard) + tryReal.
// مُستخرَج لتقليل ضخامة api.ts وكسر أيّ دورة استيراد عند تقسيم المجالات لاحقاً:
// وحدات المجال تستورد العملاء من هنا، وapi.ts يعيد تصديرها للمستهلِكين القائمين.
// السلوك محفوظ بالكامل (نسخ حرفيّ للإعداد والمُعترِضات).
// ═══════════════════════════════════════════════════════════════

import axios, { type AxiosInstance } from 'axios';
import { clearAccessToken, getAccessToken, getTenantId } from '../lib/authStorage';
import { isAccessTokenExpired } from '../lib/jwt';
import { ENDPOINTS } from '../config/endpoints';

// ── توجيه العملاء: البوّابة (nginx/Kong :80) هي المرجع القانونيّ ──────────────
// مسارات الاستدعاء تحمل بادئاتها أصلاً (kongApi ينادي '/api/v1/...'، authApi '/auth/...')،
// فقاعدة kong/auth فارغة كي لا تتكرّر البادئة. أمّا raster/vegetation/weather/soil فقاعدتها
// مسار البوّابة الذي يُجرّده nginx. الوضع يُضبَط بـVITE_API_MODE (الافتراضيّ 'gateway').
const KONG_URL = ENDPOINTS.kong;
const AUTH_URL = ENDPOINTS.auth;
const RASTER_URL = ENDPOINTS.raster;
const VEGETATION_URL = ENDPOINTS.vegetation;
const INDICATORS_URL = ENDPOINTS.indicators;
const WEATHER_URL = ENDPOINTS.weather;
const SOIL_URL = ENDPOINTS.soil;
export const MOCK_MODE = import.meta.env.VITE_MOCK_MODE === 'true' || false;

// ── Axios instances ────────────────────────────────────────────
function makeClient(baseURL: string): AxiosInstance {
  const client = axios.create({
    baseURL,
    timeout: 15000,
    headers: { 'Content-Type': 'application/json' },
  });
  // JWT interceptor
  client.interceptors.request.use((config) => {
    // useAuth يكتب التوكن/المستأجِر في sessionStorage (مصدر الحقيقة) — نقرأ منه.
    const token = getAccessToken();
    // فحص انتهاء الصلاحيّة جهة-العميل: نكتشف التوكن المنتهي محلياً فنُنظّف الجلسة ونُطلق
    // حدث الخروج ونمنع طلباً محكوماً بالفشل. وضع التجريب مُستثنى. fail-closed للمشوَّه.
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
      // بدل تمرير نصّ HTML للمكوّنات فتنهار.
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

export const kongApi = makeClient(KONG_URL);
export const weatherApi = makeClient(WEATHER_URL);
export const soilApi = makeClient(SOIL_URL);
export const indicatorsApi = makeClient(INDICATORS_URL);
export const vegetationApi = makeClient(VEGETATION_URL);
export const rasterApi = makeClient(RASTER_URL);
export const authApi = makeClient(AUTH_URL);

// ── Helper: real data, with mock ONLY in explicit MOCK_MODE ───────
// منصّة قرار زراعي لا تُلفّق توصيات ثابتة عند فشل الخادم وتعرضها كحقيقيّة. الـmock
// يقتصر على وضع التجريب الصريح (VITE_MOCK_MODE)، وأخطاء الإنتاج تُرمى ليعالجها الـUI.
export async function tryReal<T>(fn: () => Promise<T>, fallback: () => T): Promise<T> {
  if (MOCK_MODE) return fallback();
  return fn();
}
