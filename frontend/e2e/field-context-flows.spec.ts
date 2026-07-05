// ═══════════════════════════════════════════════════════════════
// SAHOOL — E2E: تدفّقات سياق الحقل (اختيار الحقل → الشاشات التشغيليّة)
// ───────────────────────────────────────────────────────────────
// يتحقّق أنّ توصيل «الحقل المشترك» (الجولات 1–4) وصل فعليّاً: كلّ شاشة تشغيليّة
// تُحمَّل مُصادَقةً، تعرض هيكلها (تسمية القائمة في الشريط) بلا أعطال console، والشاشات
// ذات منتقي الحقل تُظهر قائمة اختيار حقيقيّة (combobox) مُغذّاة من /api/v1/fields.
// هرمسيّ: كلّ /api/** مُعترَض بتركيبات seed — لا خلفيّة. لا تفاعل WebGL/Terra Draw
// (تلك في maphub-webgl.spec) فيبقى حتميّاً تحت SwiftShader headless.
import { test, expect, type Page, type ConsoleMessage } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

// تسمية الشاشة تظهر دائماً في شريط التنقّل (AppShell) ⇒ إشارة حتميّة أنّ الهيكل صُيّر.
const CTX_ROUTES: Array<{ path: string; label: RegExp; fieldSelect: boolean }> = [
  { path: '/health/satellite', label: /الأقمار الصناعية/, fieldSelect: false },
  { path: '/health/spatial', label: /المؤشرات المكانية/, fieldSelect: true },
  { path: '/health/lab-sampling', label: /عينات وتحاليل/, fieldSelect: false },
  { path: '/health/maestro', label: /المايسترو/, fieldSelect: true },
  { path: '/irrigation/plan', label: /خطّة الريّ/, fieldSelect: true },
];

function collectRealErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(err.message));
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  return errors;
}

for (const r of CTX_ROUTES) {
  test(`سياق الحقل: ${r.path} يُحمَّل مُصادَقةً بلا أعطال ويعرض الهيكل`, async ({ page }) => {
    const errors = collectRealErrors(page);
    await seedAuthAndRoutes(page);
    await page.goto(r.path, { waitUntil: 'domcontentloaded' });

    // لم يُطرَد إلى الدخول (الجلسة مبثوثة في seed) — بقي على المسار المطلوب.
    await expect.poll(() => new URL(page.url()).pathname, { timeout: 20_000 }).toBe(r.path);
    // الهيكل صُيّر: تسمية الشاشة حاضرة في شريط التنقّل.
    await expect(page.locator('body')).toContainText(r.label, { timeout: 20_000 });

    if (r.fieldSelect) {
      // منتقي الحقل المشترك مُغذّى من /api/v1/fields (seed) — قائمة اختيار حقيقيّة.
      await expect
        .poll(() => page.getByRole('combobox').count(), { timeout: 20_000 })
        .toBeGreaterThan(0);
    }

    // لا أعطال حقيقيّة. نتجاهل ضجيج البنية في التمهيد الهرمسيّ (بلا خلفيّة): فشل
    // تحميل موارد الشبكة المُعترَضة، وفشل مصافحة WebSocket الإشعارات (لا خادم WS —
    // التطبيق يعالجه بلطف؛ رسالة المتصفّح ليست عطلاً في التطبيق).
    const realErrors = errors.filter(
      (e) => !/Failed to load resource|ERR_|net::|WebSocket connection|ws:\/\/|\/ws\//i.test(e),
    );
    expect(realErrors).toEqual([]);
  });
}
