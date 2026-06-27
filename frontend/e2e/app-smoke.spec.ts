import { test, expect } from '@playwright/test';

test('app boots to authentication screen without backend', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(err.message));
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()); });

  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toContainText(/سَهول|SAHOOL|تسجيل|دخول|login/i, { timeout: 30000 });
  const realErrors = errors.filter((e) => !/Failed to load resource|ERR_/i.test(e));
  expect(realErrors).toEqual([]);
});
