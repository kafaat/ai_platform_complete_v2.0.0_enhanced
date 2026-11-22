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

// Public-only checks: no credentials, API form submission or demo bypass.
test('signup has a shareable URL, survives refresh and uses a telephone input', async ({ page }) => {
  await page.goto('/signup');
  await expect(page.getByRole('heading', { name: 'إنشاء حساب' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'إنشاء حساب' })).toBeVisible();

  const phone = page.getByPlaceholder('+9677…');
  await expect(phone).toHaveAttribute('type', 'tel');
  await expect(phone).toHaveAttribute('autocomplete', 'tel');
  await expect(phone).toHaveAttribute('inputmode', 'tel');

  await page.getByRole('button', { name: 'تسجيل الدخول' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator('#login-email')).toBeVisible();
});

test('password recovery keeps its own URL through refresh and browser back', async ({ page }) => {
  await page.goto('/login');
  await page.locator('#login-email').fill('example+recovery@example.test');
  await page.getByRole('button', { name: 'نسيت كلمة المرور؟' }).click();
  await expect(page.getByPlaceholder('you@example.com')).toHaveValue('example+recovery@example.test');
  await expect(page).toHaveURL(/\/forgot-password$/);
  await expect(page.getByText('إعادة تعيين كلمة المرور', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('إعادة تعيين كلمة المرور', { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator('#login-email')).toBeVisible();
});

test('login has production CSS utilities after the reset layer', async ({ page }) => {
  await page.goto('/login');
  const styles = await page.locator('#login-email').evaluate((field) => {
    const css = getComputedStyle(field);
    const title = getComputedStyle(document.querySelector('h1')!);
    const submit = document.querySelector('button[type="submit"]')!;
    return {
      top: css.paddingTop,
      inline: css.paddingLeft,
      titleSize: title.fontSize,
      submitHeight: submit.getBoundingClientRect().height,
    };
  });
  expect(styles.top).toBe('12px');
  expect(styles.inline).toBe('16px');
  expect(styles.titleSize).toBe('24px');
  expect(styles.submitHeight).toBeGreaterThanOrEqual(40);
});

test('all public auth pages fit a phone viewport without horizontal scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ['/login', '/signup', '/forgot-password']) {
    await page.goto(path);
    const extraWidth = await page.evaluate(() =>
      Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth
    );
    expect(extraWidth, `${path} must not overflow horizontally`).toBeLessThanOrEqual(1);
  }
});


// The auth service mails reset links, and the new tenant owner's setup link, as
// /reset-password?token=…. They used to open the invitation page («قبول دعوة الانضمام»).
test('a password-reset link opens the new-password step, not the invitation page', async ({ page }) => {
  await page.goto('/reset-password?token=e2e-not-a-real-token');
  await expect(page.getByText('تعيين كلمة مرور جديدة', { exact: true })).toBeVisible();
  const password = page.locator('input[autocomplete="new-password"]');
  await expect(password).toBeVisible();
  await expect(page.getByText('قبول دعوة الانضمام')).toHaveCount(0);
  // The token leaves the address bar, and typing keeps the step (it is held in state).
  await expect(page).toHaveURL(/\/reset-password$/);
  await password.fill('Strong#Pass1');
  await expect(page.getByText('تعيين كلمة مرور جديدة', { exact: true })).toBeVisible();
  // A reload no longer carries the token, so it asks for a new link, never the invitation.
  await page.reload();
  await expect(page.getByText('إعادة تعيين كلمة المرور', { exact: true })).toBeVisible();
  await expect(page.getByText('قبول دعوة الانضمام')).toHaveCount(0);
});

test('an invitation token wins on any other path and survives the URL clean-up', async ({ page }) => {
  for (const path of ['/signup?token=e2e-invite', '/accept-invitation?token=e2e-invite', '/?token=e2e-invite']) {
    await page.goto(path);
    const heading = page.getByRole('heading', { name: 'قبول دعوة الانضمام' });
    await expect(heading).toBeVisible();
    await expect(page).not.toHaveURL(/token=/);
    await page.locator('input').first().fill('اسم تجريبي');
    await expect(heading).toBeVisible();
  }
});
