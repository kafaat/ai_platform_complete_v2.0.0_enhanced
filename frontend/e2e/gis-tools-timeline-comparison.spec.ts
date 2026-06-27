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

test('Timeline + Comparison Mode يعرض مراجعات الخادم ويحسب فرق المساحة والرؤوس @gating', async ({ page }) => {
  await expect(page.getByRole('heading', { name: /أدوات الهندسة المكانيّة/ })).toBeVisible();
  await expect(page.getByText(/معاينة فقط/).first()).toBeVisible();

  const historyRequests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/geometry/history')) historyRequests.push(request.url());
  });

  await page.getByRole('button', { name: 'تفعيل' }).click();

  await expect(page.getByText('خط الأساس')).toBeVisible();
  await expect(page.getByText('المقارنة')).toBeVisible();
  await expect(page.getByText('مراجعة 1')).toBeVisible();
  await expect(page.getByText('مراجعة 2')).toBeVisible();

  await page.getByLabel('خط الأساس').selectOption('1');
  await page.getByLabel('المقارنة').selectOption('2');

  await expect(page.getByText('فرق المساحة')).toBeVisible();
  await expect(page.getByText('فرق الرؤوس')).toBeVisible();
  await expect(page.getByText(/م²/)).toBeVisible();
  await expect(page.getByText(/تعديل حدود بعد رفع مسار GPS/)).toBeVisible();

  await expect.poll(() => historyRequests.length, { timeout: 10_000 }).toBeGreaterThan(0);
});
