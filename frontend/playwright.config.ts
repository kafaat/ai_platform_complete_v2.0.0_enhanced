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
const BASE_URL = `http://127.0.0.1:${PORT}`;

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
  expect: {
    timeout: 15_000,
    // انحدار بصريّ (toHaveScreenshot): تسامح صغير مع فروق البكسل غير الجوهريّة
    // (تنعيم الخطّ/ضغط PNG) كي لا تتحوّل فروق التصيير التافهة إلى فشل كاذب — مع
    // إبقاء الحسّاسيّة لتغيّرات التخطيط/اللون الحقيقيّة. تُطبَّق على مشروع visual.
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
      animations: 'disabled',
      caret: 'hide',
    },
  },
  // لقطات مرجعيّة مستقرّة الاسم بمعزل عن نظام التشغيل/المعمارية: نمنع لاحقة النظام
  // التلقائيّة كي تُصان اللقطات على العدّاء الأساسيّ (Linux CI) وتُقارَن به. اسم
  // ثابت: <spec>-snapshots/<title>.png (لا -linux/-darwin) — انظر رأس الملفّ البصريّ.
  snapshotPathTemplate: '{testDir}/__screenshots__/{testFilePath}/{arg}{ext}',
  use: {
    baseURL: BASE_URL,
    // أدلّة جنائيّة عند الفشل: أثر + لقطة + فيديو — تُرفَق بتقرير HTML لإعادة التشخيص.
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      // البوّابة الوظيفيّة لا تُشغّل سويت الانحدار البصريّ (*.visual.spec.ts): تلك
      // تقارن بكسلات ضدّ لقطات مرجعيّة مصونة، وتُشغَّل صراحةً عبر مشروع visual
      // (PW_VISUAL=1) كي لا يحجب انحراف تصيير بيئيّ البوّابةَ العامّة.
      testIgnore: /\.visual\.spec\.ts$/,
      use: {
        ...devices['Desktop Chrome'],
        // في CI: متصفّح Playwright المُدار (channel من Desktop Chrome). إن وُجد
        // تجاوز PW_CHROMIUM_PATH (بيئة محجوبة) نُلغي القناة ونُشير للتنفيذيّ مباشرة.
        ...(CHROMIUM_PATH ? { channel: undefined } : {}),
        launchOptions: {
          ...(CHROMIUM_PATH ? { executablePath: CHROMIUM_PATH } : {}),
          // تفعيل WebGL البرمجيّ (SwiftShader) في headless داخل الحاوية.
          args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--use-gl=angle',
            '--use-angle=swiftshader',
            '--enable-unsafe-swiftshader',
            '--ignore-gpu-blocklist',
          ],
        },
      },
    },
    // متصفّحات إضافيّة **اختياريّة** (WebKit/Safari-iOS · Firefox) — لا تعمل افتراضيّاً
    // (CI يثبّت Chromium فقط)؛ تُفعَّل بـPW_ALL_BROWSERS=1 بعد `playwright install webkit
    // firefox`. تُغلق فجوة تعدّد المتصفّحات (WebKit الأقرب لـiOS) دون كسر بوّابة Chromium.
    ...(process.env.PW_ALL_BROWSERS === '1'
      ? [
          { name: 'webkit', use: { ...devices['Desktop Safari'], testIgnore: /\.visual\.spec\.ts$/ } },
          { name: 'firefox', use: { ...devices['Desktop Firefox'], testIgnore: /\.visual\.spec\.ts$/ } },
        ]
      : []),
    // ── مشروع الانحدار البصريّ (opt-in، PW_VISUAL=1) ────────────────────────
    // يُشغّل *.visual.spec.ts فقط: لقطات DOM حتميّة (شاشة الدخول + كسوة الإعدادات
    // DS) — لا canvas/WebGL (تصييره غير حتميّ تحت SwiftShader headless، انظر رأس
    // الملفّ). منفصل عن البوّابة كي لا يحجب انحرافُ بيئةٍ التطويرَ حتى تُصان اللقطات
    // على العدّاء الأساسيّ. viewport ثابت + خطّ نظام + reduced-motion للحتميّة.
    ...(process.env.PW_VISUAL === '1'
      ? [
          {
            name: 'visual',
            testMatch: /\.visual\.spec\.ts$/,
            use: {
              ...devices['Desktop Chrome'],
              viewport: { width: 1280, height: 800 },
              deviceScaleFactor: 1,
              // نُثبّت التفضيل «تقليل الحركة» كي تُعطَّل الانتقالات (framer-motion)
              // فتستقرّ اللقطة. animations:'disabled' في expect يكمّله.
              reducedMotion: 'reduce',
              colorScheme: 'light',
              ...(CHROMIUM_PATH ? { channel: undefined } : {}),
              launchOptions: {
                ...(CHROMIUM_PATH ? { executablePath: CHROMIUM_PATH } : {}),
                args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
              },
            },
          },
        ]
      : []),
  ],
  // يبني الواجهة بمحرّك maplibre ثمّ يخدمها (preview بلا وكيل ⇒ same-origin /api).
  webServer: {
    command: 'npm run build && npm run verify:bundle-budget && npm run preview -- --host 127.0.0.1',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { VITE_MAP_ENGINE: 'maplibre', VITE_E2E_HOOKS: '1' },
  },
});
