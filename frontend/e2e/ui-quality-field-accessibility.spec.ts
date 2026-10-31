/** Real-browser, hermetic UI contract inspired by Impeccable/Hallmark; no external package. */
import { test, expect } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

// Block only concrete functional/a11y regressions, not subjective aesthetics.
for (const route of ['/health/spatial', '/health/maestro', '/irrigation/plan']) {
  test('field selection is keyboard-operable and named: ' + route, async ({ page }) => {
    const exceptions: string[] = [];
    page.on('pageerror', (error) => exceptions.push(error.message));
    await seedAuthAndRoutes(page);
    await page.goto(route, { waitUntil: 'domcontentloaded' });
    await expect.poll(() => new URL(page.url()).pathname, { timeout: 20_000 }).toBe(route);
    const control = page.getByRole('combobox').first();
    await expect(control).toBeVisible({ timeout: 20_000 });
    // Accessible names must be usable by screen readers and voice navigation.
    await expect(control).toHaveAccessibleName(/\S/);
    await control.focus();
    await expect(control).toBeFocused();
    await page.keyboard.press('Tab');
    expect(exceptions).toEqual([]);
  });
}
