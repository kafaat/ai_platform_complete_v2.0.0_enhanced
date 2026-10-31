/** Real-browser, hermetic UI contract informed by Impeccable/Hallmark; no external package. */
import { test, expect } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

// The shell's placeholder combobox is not the operational field selector.
// Fail on unnamed or disabled selectors, without gating subjective aesthetics.
const ROUTES = [
  { path: '/health/spatial', name: 'الحقل للمؤشرات المكانية' },
  { path: '/health/maestro', name: 'الحقل للتحليل' },
  { path: '/irrigation/plan', name: 'الحقل الذي ستُبنى عليه خطة الري' },
] as const;

for (const { path, name } of ROUTES) {
  test(`operational field selector is named and keyboard-operable: ${path}`, async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (error) => exceptions.push(error.message));
    await seedAuthAndRoutes(page);
    await page.goto(path, { waitUntil: 'domcontentloaded' });
    await expect.poll(() => new URL(page.url()).pathname, { timeout: 20_000 }).toBe(path);

    const control = page.getByTestId('operational-field-selector');
    await expect(control).toHaveCount(1);
    await expect(control).toBeVisible({ timeout: 20_000 });
    await expect(control).toHaveAccessibleName(name);
    await expect(control).toBeEnabled();
    await expect.poll(() => control.locator('option').count()).toBeGreaterThan(1);

    await control.focus();
    await expect(control).toBeFocused();
    await control.press('Home');
    await control.press('ArrowDown');
    await expect.poll(() => control.inputValue()).not.toBe('');
    await page.keyboard.press('Tab');
    await expect(control).not.toBeFocused();
    expect(exceptions).toEqual([]);
  });
}
