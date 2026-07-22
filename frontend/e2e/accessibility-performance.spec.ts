import { expect, test } from '@playwright/test';

test('login has keyboard-visible accessible controls', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });

  await expect(page.getByRole('main')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'سهول' })).toBeVisible();
  await expect(page.getByLabel('البريد الإلكتروني')).toHaveAttribute('autocomplete', 'email');
  await expect(page.getByLabel('كلمة المرور')).toHaveAttribute('autocomplete', 'current-password');
  await expect(page.getByRole('button', { name: 'إظهار كلمة المرور' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'تسجيل الدخول' })).toBeVisible();

  await page.keyboard.press('Tab');
  await expect(page.getByLabel('البريد الإلكتروني')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('كلمة المرور')).toBeFocused();
});

test('production login stays inside local navigation and asset budgets', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });

  const metrics = await page.evaluate(() => {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
    const scripts = performance.getEntriesByType('resource')
      .filter((entry) => entry.name.includes('/assets/') && entry.name.endsWith('.js')) as PerformanceResourceTiming[];
    return {
      domContentLoadedMs: navigation.domContentLoadedEventEnd,
      loadMs: navigation.loadEventEnd,
      scriptCount: scripts.length,
      maxScriptDecodedBytes: Math.max(0, ...scripts.map((entry) => entry.decodedBodySize)),
      totalScriptDecodedBytes: scripts.reduce((total, entry) => total + entry.decodedBodySize, 0),
    };
  });

  expect(metrics.domContentLoadedMs).toBeLessThan(5_000);
  expect(metrics.loadMs).toBeLessThan(8_000);
  expect(metrics.scriptCount).toBeGreaterThan(0);
  expect(metrics.maxScriptDecodedBytes).toBeLessThanOrEqual(1_050_000);
  expect(metrics.totalScriptDecodedBytes).toBeLessThanOrEqual(2_500_000);
});
