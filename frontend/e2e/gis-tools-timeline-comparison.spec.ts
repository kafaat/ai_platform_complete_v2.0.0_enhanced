// SAHOOL — E2E حي/هرمسي لميزة Timeline + Comparison Mode في GIS Tools.
// يتحقق من مسار المستخدم الكامل: مصادقة seeded، تحميل الحقول من /api/v1/fields،
// تحميل /geometry/history، تفعيل الوضع، اختيار مراجعتين، وظهور فروقات المساحة/الرؤوس.
import { test, expect } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

const GIS_TOOLS_PATH = '/analysis/gis-tools';

test.beforeEach(async ({ page }) => {
  await seedAuthAndRoutes(page);
  await page.goto(GIS_TOOLS_PATH, { waitUntil: 'domcontentloaded' });
});

// السبب الجذريّ للتأجيل السابق (مُصحَّح الآن): resolveActiveFieldId يختار أوّل حقل
// فور تحميل القائمة، فيُطلِق useFieldGeometryHistory طلب /geometry/history **أثناء
// تحميل الصفحة** — قبل أن يُركّب الاختبار مُستمِع الطلبات في جسمه (بعد ملاحة
// beforeEach)، فيفوته العدّ ويفشل expect.poll. الإصلاح: نُركّب المستمع أوّلاً ثمّ
// نُعيد التحميل كي يُلتقَط الطلب وقت إقلاعه (لا تزييف — التدفّق الحيّ نفسه).
test('Timeline + Comparison Mode يعرض مراجعات الخادم ويحسب فرق المساحة والرؤوس @gating', async ({ page }) => {
  const historyRequests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/geometry/history')) historyRequests.push(request.url());
  });
  // إعادة تحميل بعد تركيب المستمع ⇒ يُلتقَط طلب السجلّ الذي يُطلَق عند اختيار أوّل حقل.
  await page.reload({ waitUntil: 'domcontentloaded' });

  await expect(page.getByRole('heading', { name: /أدوات الهندسة المكانيّة/ })).toBeVisible();
  await expect(page.getByText(/معاينة فقط/).first()).toBeVisible();

  await page.getByRole('button', { name: 'تفعيل' }).click();

  await expect(page.getByText('خط الأساس')).toBeVisible();
  await expect(page.getByText('المقارنة', { exact: true })).toBeVisible();
  // «مراجعة 1/2» تظهر كـ<option> داخل <select> (مخفيّة في Playwright حتى يُفتح
  // المنسدِل) ⇒ نتحقّق من وجودها (attached) لا ظهورها.
  await expect(page.getByText('مراجعة 1').first()).toBeAttached();
  await expect(page.getByText('مراجعة 2').first()).toBeAttached();

  await page.getByLabel('خط الأساس').selectOption('1');
  await page.getByLabel('المقارنة').selectOption('2');

  await expect(page.getByText('فرق المساحة').first()).toBeVisible();
  await expect(page.getByText('فرق الرؤوس').first()).toBeVisible();
  await expect(page.getByText(/م²/).first()).toBeVisible();
  await expect(page.getByText(/تعديل حدود بعد رفع مسار GPS/)).toBeVisible();

  await expect.poll(() => historyRequests.length, { timeout: 10_000 }).toBeGreaterThan(0);
});
