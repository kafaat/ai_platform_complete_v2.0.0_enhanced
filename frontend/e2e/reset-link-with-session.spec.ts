import { test, expect } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

// The auth service mails reset links, and the new tenant owner's setup link, as
// /reset-password?token=…. The public cases live in app-smoke.spec.ts; this one
// needs a stored session, which that file deliberately never seeds.
//
// A stored session used to send the link to / through the signed-in router's catch-all.
test('a password-reset link opens the new-password step even with a stored session', async ({ page }) => {
  await seedAuthAndRoutes(page);
  let confirmed = 0;
  await page.route('**/auth/password-reset/confirm', (route) => {
    confirmed += 1;
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' });
  });
  await page.goto('/reset-password?token=e2e-not-a-real-token');
  await expect(page.getByText('تعيين كلمة مرور جديدة', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/reset-password$/);
  await page.locator('#reset-new-password').fill('Strong#Pass1');
  await page.locator('#reset-confirm-password').fill('Strong#Pass1');
  await page.locator('form button[type="submit"]').click();
  await expect(page.getByText('تم تغيير كلمة المرور بنجاح')).toBeVisible();
  expect(confirmed).toBe(1);
  // The reset revokes the old session, so a background /auth/ call may answer 401 and the app
  // logs out (client.ts dispatches this event). The success screen must stay, not remount
  // into the "send me a link" form.
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('sahool:auth:unauthorized')));
  await expect(page.getByText('تم تغيير كلمة المرور بنجاح')).toBeVisible();
  await expect(page.getByText('إعادة تعيين كلمة المرور', { exact: true })).toHaveCount(0);
  // Going back to sign in ends the old session instead of returning to the app.
  await page.getByRole('button', { name: 'العودة لتسجيل الدخول' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator('input[type="email"]')).toBeVisible();
  const stored = await page.evaluate(() => sessionStorage.getItem('sahool-auth') ?? '');
  expect(stored).not.toContain('"isAuthenticated":true');
});
