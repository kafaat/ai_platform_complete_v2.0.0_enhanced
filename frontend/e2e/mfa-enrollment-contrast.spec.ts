import { expect, test } from '@playwright/test';
import { expectReadableText } from './support/readability';

test('MFA setup instructions, provisioning values and copy controls stay readable in the light sign-in page', async ({ page }) => {
  // Synthetic enrollment responses exercise the shipped screen and CSS without an account or backend.
  const secret = 'AAAAAAAAAAAAAAAA';
  const uri = `otpauth://totp/SAHOOL:enrollment%40example.test?secret=${secret}&issuer=SAHOOL`;
  await page.route('**/auth/login', route => route.fulfill({
    status: 403,
    json: { enrollment_token: 'setup-test', expires_in: 300 },
  }));
  await page.route('**/auth/mfa/setup', route => route.fulfill({
    json: {
      enrollment_token: 'activate-test', expires_in: 300,
      secret, provisioning_uri: uri,
    },
  }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/login');
  await page.getByLabel('البريد الإلكتروني').fill('enrollment@example.test');
  await page.getByLabel('كلمة المرور', { exact: true }).fill('Synthetic-Password-1');
  await page.getByRole('button', { name: 'تسجيل الدخول', exact: true }).click();
  await page.getByRole('button', { name: 'بدء تفعيل المصادقة الثنائيّة' }).click();

  const copyButtons = page.getByRole('button', { name: 'نسخ', exact: true });
  await expect(copyButtons).toHaveCount(2);
  const link = page.getByRole('link', { name: 'فتح في تطبيق المصادقة (على الهاتف)' });
  await expect(link).toHaveAttribute('href', uri);
  for (const element of [
    page.getByText(/^١\. أضِف الحساب/),
    page.getByText('يُعرَض مرّة واحدة فقط.', { exact: true }),
    page.getByText('المفتاح السرّيّ', { exact: true }),
    page.getByText('رابط otpauth', { exact: true }),
    page.getByTestId('mfa-enroll-secret'),
    page.getByTestId('mfa-enroll-uri'),
    copyButtons.nth(0), copyButtons.nth(1), link,
  ]) {
    await expectReadableText(element);
  }
});
