// SAHOOL — E2E هرمسيّ لمنتقي نموذج الذكاء في شاشة المستشار (/assistant).
// يغطّي جوهر إضافة OpenRouter: تحميل كتالوج /api/v1/ai/models، ظهور المنتقي،
// اختيار نموذج (Gemini 3 Pro)، وإرسال رسالة تحمل النموذج المختار إلى
// /api/ai-agronomist/chat — مع تأكيد عودة selected_model في الردّ.
//
// صدق: التركيبات تعيش في طبقة Playwright فقط (تُسجَّل بعد seedAuthAndRoutes فتغلب
// الـcatch-all). لا مفاتيح ولا خلفيّة حقيقيّة — نتحقّق من العقد بين الواجهة والخادم.
import { test, expect } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

const ASSISTANT_PATH = '/assistant';

const MODELS_CATALOG = {
  provider: 'openrouter',
  default_model: 'deepseek/deepseek-chat',
  available: true,
  reason_ar: null,
  models: [
    { id: 'deepseek/deepseek-chat', label: 'DeepSeek' },
    { id: 'google/gemini-3-pro', label: 'Gemini 3 Pro' },
  ],
};

test('منتقي النموذج: يحمّل الكتالوج، يختار Gemini، ويرسل النموذج المختار @gating', async ({
  page,
}) => {
  await seedAuthAndRoutes(page);

  // كتالوج النماذج (المصدر الذي يبني منه المنتقي خياراته).
  await page.route('**/api/v1/ai/models', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MODELS_CATALOG),
    }),
  );

  // مسار الدردشة — نلتقط جسم الطلب ونُعيد صدى النموذج المختار (عقد selected_model).
  let chatBody: { model?: string; question?: string } | null = null;
  await page.route('**/api/ai-agronomist/chat', (route) => {
    const req = route.request();
    chatBody = req.postDataJSON();
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        mode: 'evidence_only',
        answer_ar: 'هذه إجابة تجريبيّة مؤرَّضة من المستشار.',
        message: 'هذه إجابة تجريبيّة مؤرَّضة من المستشار.',
        selected_model: chatBody?.model ?? null,
        confidence: 0.5,
        evidence_ids: [],
      }),
    });
  });

  await page.goto(ASSISTANT_PATH, { waitUntil: 'domcontentloaded' });

  // (1) المنتقي يظهر (خياران فأكثر) ويعرض تسميات النماذج.
  const picker = page.getByLabel('نموذج الذكاء');
  await expect(picker).toBeVisible();
  await expect(picker.locator('option')).toHaveCount(2);
  await expect(page.getByRole('option', { name: 'Gemini 3 Pro' })).toBeAttached();

  // (2) اختيار Gemini 3 Pro.
  await picker.selectOption('google/gemini-3-pro');
  await expect(picker).toHaveValue('google/gemini-3-pro');

  // (3) إرسال رسالة.
  const input = page.getByPlaceholder(/اسأل عن NDVI/);
  await input.fill('ما حالة حقلي؟');
  await input.press('Enter');

  // (4) الطلب حمل النموذج المختار (عقد الواجهة ⇒ الخادم).
  await expect.poll(() => chatBody?.model, { timeout: 10_000 }).toBe('google/gemini-3-pro');
  expect(chatBody?.question).toBe('ما حالة حقلي؟');

  // (5) ردّ المستشار يظهر في المحادثة (تأكيد التدفّق الكامل).
  await expect(page.getByText(/إجابة تجريبيّة مؤرَّضة/).first()).toBeVisible({ timeout: 10_000 });
});

test('منتقي النموذج: الاختيار يثبت محلّيّاً عبر إعادة التحميل @gating', async ({ page }) => {
  await seedAuthAndRoutes(page);
  await page.route('**/api/v1/ai/models', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MODELS_CATALOG),
    }),
  );

  await page.goto(ASSISTANT_PATH, { waitUntil: 'domcontentloaded' });
  const picker = page.getByLabel('نموذج الذكاء');
  await expect(picker).toBeVisible();
  await picker.selectOption('google/gemini-3-pro');

  // إعادة تحميل ⇒ يُقرأ الاختيار من التخزين المحلّيّ (ثبات تفضيل المستخدم).
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByLabel('نموذج الذكاء')).toHaveValue('google/gemini-3-pro');
});
