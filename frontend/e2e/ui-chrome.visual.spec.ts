// ═══════════════════════════════════════════════════════════════
// SAHOOL — انحدار بصريّ (Visual Regression) · كسوة DOM حتميّة فقط
// ───────────────────────────────────────────────────────────────
// سويت opt-in (مشروع playwright «visual»، تُفعَّل بـPW_VISUAL=1) تلتقط لقطات
// مرجعيّة لسطوح DOM **حتميّة** وتقارن البكسل ضدّها عبر toHaveScreenshot. تكشف
// انحدارات التصميم غير المقصودة (تخطيط/لون/تباعد/طباعة) التي لا تلتقطها اختبارات
// الوحدة (منطق) ولا E2E الوظيفيّة (سلوك) — الطبقة المفقودة بعد تفكيك MapHub/Settings.
//
// نطاق صادق — لماذا DOM فقط لا الخريطة:
//   • تصيير MapLibre/WebGL تحت SwiftShader headless غير حتميّ بكسليّاً (نصّ رأس
//     playwright.config.ts صراحةً: «لا تطابق بكسل على GPU»). إخضاعه لـtoHaveScreenshot
//     يُنتج فشلاً كاذباً — فنستثنيه عمداً. الخريطة تُغطّى وظيفيّاً في maphub-webgl.spec.ts.
//   • الأهداف هنا كسوة مستقرّة: شاشة الدخول (بلا خلفيّة) + كسوة الإعدادات (DS: بطاقات/
//     حقول/أزرار، بلا canvas). حتميّة عبر viewport ثابت + reduced-motion + animations
//     مُعطَّلة (playwright.config.ts) + إخفاء المؤشّر النابض.
//
// تفعيل واعتماد اللقطات (لا تحجب البوّابة):
//   • البوّابة العامّة (`npx playwright test`) تتجاهل *.visual.spec.ts (testIgnore في
//     مشروع chromium) — فانحرافُ تصييرٍ بيئيّ لا يُسقِط CI الوظيفيّ.
//   • تشغيل المقارنة: `npm run e2e:visual`. تحديث اللقطات بعد تغيير تصميميّ مقصود:
//     `npm run e2e:visual:update`. اللقطات تُصان في e2e/__screenshots__/ باسم مستقلّ
//     عن النظام (snapshotPathTemplate) على Chromium المُثبَّت لـPlaywright (بنية موحّدة
//     عبر البيئات) — فتُقارَن حتميّاً على أيّ عدّاء Linux.
//   • اللقطات المرجعيّة مُودَعة في المستودع (وُلِّدت على حاوية Linux مكافئة لـCI). عند
//     تغيير خطّ/لون/تخطيط مقصود يُعاد توليدها بـ:update وتُراجَع الفروق في PR.
import { test, expect } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

// حجب الدخول قبل التقاط اللقطة: نتأكّد أنّ الخطوط/الأصول حُمِّلت واستقرّ التخطيط.
async function settle(page: import('@playwright/test').Page) {
  await page.waitForLoadState('networkidle').catch(() => { /* interception قد يُبقي طلبات */ });
  await page.evaluate(() => (document as unknown as { fonts?: { ready: Promise<unknown> } }).fonts?.ready);
}

test.describe('Visual regression — deterministic DOM chrome (@visual)', () => {
  test('شاشة الدخول (بلا خلفيّة) — لقطة مرجعيّة كاملة', async ({ page }) => {
    // بلا seed: نريد شاشة المصادقة نفسها (لا القشرة المُصادَقة).
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('body')).toContainText(/سَهول|SAHOOL|تسجيل|دخول|login/i, { timeout: 30_000 });
    await settle(page);
    await expect(page).toHaveScreenshot('login-screen.png', { fullPage: true });
  });

  test('كسوة الإعدادات — تبويب «عام» (DS: بطاقات/حقول/أزرار، بلا خريطة)', async ({ page }) => {
    // /settings محجوبة عن worker (agronomist+ فقط) — نُصادِق بدور agronomist كي
    // تُعرَض الصفحة (لا Team tab: isOwner=false ⇒ التبويب الافتراضيّ «عام» فقط).
    await seedAuthAndRoutes(page, 'agronomist');
    await page.goto('/settings', { waitUntil: 'domcontentloaded' });
    const root = page.getByTestId('settings-page');
    await expect(root).toBeVisible({ timeout: 30_000 });
    // تبويب «عام» هو الافتراضيّ — نتأكّد من ظهور عنصر ثابت فيه قبل اللقطة.
    await expect(root).toContainText('اللغة والعرض', { timeout: 15_000 });
    await settle(page);
    // لقطة لمنطقة الإعدادات فقط (لا القشرة المحيطة) — أكثر استقراراً وتحديداً.
    await expect(root).toHaveScreenshot('settings-general.png');
  });
});
