// ═══════════════════════════════════════════════════════════════
// SAHOOL — Playwright E2E config · بوّابة QA لـMapLibre/WebGL
// ───────────────────────────────────────────────────────────────
// تُشغّل سويت E2E الوظيفيّة لمركز الخرائط على متصفّح Chromium حقيقيّ (لا jsdom)،
// فتتحقّق من إنشاء سياق WebGL + أسلاك طبقات الحقول + التفاعل + قيم القياس — لا
// تطابق البكسل على GPU (تلك تبقى توقيعاً بصريّاً يدويّاً على عتاد حقيقيّ).
//
// هرمسيّة: لا خلفيّة. الـwebServer يبني الواجهة بعَلَم VITE_MAP_ENGINE=maplibre
// ثمّ يخدمها عبر `vite preview` على :4173 (بلا وكيل ⇒ كلّ نداءات /api/** تُعترَض
// في طبقة اختبار Playwright بتركيبات ثابتة — انظر e2e/support/seed.ts).
//
// WebGL في headless: SwiftShader (برمجيّ) عبر وسائط الإطلاق أدناه — ANGLE +
// swiftshader، مع تجاوز قائمة حظر GPU كي يُنشَأ سياق WebGL داخل الحاوية.
import { defineConfig, devices } from '@playwright/test';

const PORT = 4173;
const BASE_URL = `http://localhost:${PORT}`;

// تجاوز اختياريّ لمسار تنفيذيّ للمتصفّح (بيئات محجوبة عن تنزيل متصفّحات Playwright):
// إن ضُبِط PW_CHROMIUM_PATH نُشغّل ذلك المتصفّح بدل متصفّح Playwright المُدار. في CI
// يُترَك غير مضبوط (يُستعمل المتصفّح المُنزَّل عبر `playwright install`).
const CHROMIUM_PATH = process.env.PW_CHROMIUM_PATH;

export default defineConfig({
  testDir: './e2e',
  // البصريّ (@visual) قد يطلب لقطات مرجعيّة؛ نُبقيه خارج الحجب (انظر سكربت CI).
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['html', { open: 'never' }], ['github'], ['list']],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // في CI: متصفّح Playwright المُدار (channel من Desktop Chrome). إن وُجد
        // تجاوز PW_CHROMIUM_PATH (بيئة محجوبة) نُلغي القناة ونُشير للتنفيذيّ مباشرة.
        ...(CHROMIUM_PATH ? { channel: undefined } : {}),
        launchOptions: {
          ...(CHROMIUM_PATH ? { executablePath: CHROMIUM_PATH } : {}),
          // تفعيل WebGL البرمجيّ (SwiftShader) في headless داخل الحاوية.
          args: [
            '--use-gl=angle',
            '--use-angle=swiftshader',
            '--enable-unsafe-swiftshader',
            '--ignore-gpu-blocklist',
          ],
        },
      },
    },
  ],
  // يبني الواجهة بمحرّك maplibre ثمّ يخدمها (preview بلا وكيل ⇒ same-origin /api).
  webServer: {
    command: 'npm run build && npm run preview',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { VITE_MAP_ENGINE: 'maplibre' },
  },
});
