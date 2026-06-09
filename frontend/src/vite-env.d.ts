/// <reference types="vite/client" />

// تعريف متغيّرات البيئة المستخدمة في التطبيق (Vite import.meta.env)
// يمنع فشل `tsc && vite build` على خاصّيّة env غير المعرّفة.
interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_AUTH_URL: string;
  readonly VITE_INDICATORS_URL: string;
  readonly VITE_SOIL_URL: string;
  readonly VITE_VEGETATION_URL: string;
  readonly VITE_WEATHER_URL: string;
  readonly VITE_WS_URL: string;
  readonly VITE_MOCK_MODE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
