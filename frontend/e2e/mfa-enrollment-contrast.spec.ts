import { expect, test, type Locator } from '@playwright/test';

async function expectReadableText(element: Locator) {
  await expect(element).toBeVisible();
  const result = await element.evaluate(node => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const context = canvas.getContext('2d', { willReadFrequently: true })!;
    const luminance = (color: string) => {
      // Tailwind may return oklch(), so use the browser's sRGB conversion.
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      const rgb = Array.from(context.getImageData(0, 0, 1, 1).data).slice(0, 3);
      const linear = rgb.map(channel => {
        const value = channel / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      });
      return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
    };
    let surface: Element | null = node;
    while (surface) {
      const background = getComputedStyle(surface).backgroundColor;
      if (background !== 'transparent' && background !== 'rgba(0, 0, 0, 0)') {
        const foreground = getComputedStyle(node).color;
        const foregroundL = luminance(foreground);
        const backgroundL = luminance(background);
        return {
          foreground,
          background,
          contrast: (Math.max(foregroundL, backgroundL) + 0.05) / (Math.min(foregroundL, backgroundL) + 0.05),
        };
      }
      surface = surface.parentElement;
    }
    throw new Error('The enrollment text must have a painted background');
  });
  expect(result.contrast, JSON.stringify(result)).toBeGreaterThanOrEqual(4.5);
}

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
