/// <reference types="vite/client" />

// تعريف متغيّرات البيئة المستخدمة في التطبيق (Vite import.meta.env)
// يمنع فشل `tsc && vite build` على خاصّيّة env غير المعرّفة.
interface ImportMetaEnv {
  // وضع التوجيه: 'gateway' (افتراضيّ، مسارات نسبيّة عبر nginx :80/وكيل vite) أو 'dev'.
  readonly VITE_API_MODE: string;
  // قواعد العملاء (يَسبق الصريحُ الافتراضَ؛ '' فارغة مقصودة لـkong/auth).
  readonly VITE_API_BASE_URL: string;
  readonly VITE_AUTH_BASE_URL: string;
  readonly VITE_RASTER_BASE_URL: string;
  readonly VITE_VEGETATION_BASE_URL: string;
  readonly VITE_INDICATORS_BASE_URL: string;
  readonly VITE_WEATHER_BASE_URL: string;
  readonly VITE_SOIL_BASE_URL: string;
  readonly VITE_WS_BASE_URL: string;
  readonly VITE_MOCK_MODE: string;
  // أعلام الميزات: إخفاء الشاشات بلا خلفيّة جاهزة (الافتراضيّ مُخفاة).
  readonly VITE_ENABLE_WEATHER: string;
  readonly VITE_ENABLE_SOIL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
