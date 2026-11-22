import { expect, test } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

// The circle-field and centre-pivot tools are first-class Arabic tools in the main map toolbar
// for roles that may edit fields (owner, manager), found by their accessible names.
test('the map toolbar offers the circle-field and centre-pivot tools to an owner', async ({ page }) => {
  await seedAuthAndRoutes(page, 'owner');
  await page.goto('/');
  const circle = page.getByRole('button', { name: 'حقل دائري' });
  await expect(circle).toBeVisible();
  await expect(page.getByRole('button', { name: 'تصميم الريّ المحوريّ' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'مناطق الإدارة' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Zones', exact: true })).toHaveCount(0);

  // «حقل دائري» opens the add-field dialog with the circle tool already selected.
  await circle.click();
  await expect(page.getByRole('button', { name: /دائرة \(ريّ محوريّ\)/ })).toHaveAttribute('aria-pressed', 'true');
});

test('a farmer, who cannot edit fields, does not get the field-design tools', async ({ page }) => {
  await seedAuthAndRoutes(page, 'farmer');
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'رسم/قياس' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'حقل دائري' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'تصميم الريّ المحوريّ' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'مناطق الإدارة' })).toHaveCount(0);
});

test.describe('mobile drawing workspace', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });
  test('layers collapse, circle and freehand can be measured, hints dismiss without clearing', async ({ page }, info) => {
    const gl = info.config.metadata.mapEngine === 'maplibre';
    await seedAuthAndRoutes(page);
    await page.goto('/');
    const settings = page.getByRole('button', { name: 'المزيد من الأدوات والطبقات' });
    await expect(settings).toHaveAttribute('aria-expanded', 'false');
    await settings.click();
    await expect(page.getByTestId('basemap-switcher')).toBeVisible();
    await settings.click();
    await page.getByTestId('btn-draw').click();
    const dock = page.getByRole('region', { name: 'أدوات القياس' });
    if (gl) await expect(dock).toHaveAttribute('data-draw-ready', 'true');
    const surface = gl ? page.getByTestId('hubmapgl-container') : page.locator('[data-testid="leaflet-map"] .leaflet-container');
    await dock.getByRole('button', { name: 'دائرة', exact: true }).click();
    await surface.scrollIntoViewIfNeeded();
    await surface.tap({ position: { x: 140, y: 144 } });
    await surface.tap({ position: { x: 190, y: 170 } });
    await expect(dock.getByTestId('measure-area')).toContainText('هكتار');
    await dock.getByRole('button', { name: 'إغلاق تعليمات الرسم' }).click();
    await expect(dock.getByTestId('measure-area')).toBeVisible();
    await dock.getByRole('button', { name: 'مسح القياسات' }).click();
    await expect(dock.getByTestId('measure-area')).toHaveCount(0);
    await dock.getByRole('button', { name: 'رسم حر', exact: true }).click();
    await drawStroke(page, surface);
    await expect(dock.getByTestId('measure-area')).toContainText('هكتار');
    const bounds = await page.getByTestId('btn-draw').boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(391);
  });

  test('a field outline drawn by touch reaches save and the resulting toast can be dismissed', async ({ page }) => {
    await seedAuthAndRoutes(page, 'owner');
    await page.route('**/api/v1/fields', route => route.request().method() === 'POST'
      ? route.fulfill({ json: { field_id: 'new-field' } }) : route.fallback());
    await page.goto('/');
    await page.getByTestId('btn-freehand-field').click();
    const dialog = page.getByRole('dialog', { name: 'حدود الحقل' });
    const surface = dialog.getByTestId('freehand-surface');
    const bounds = await surface.boundingBox();
    expect(bounds!.width).toBeGreaterThan(250);
    expect(bounds!.height).toBeGreaterThan(180);
    await drawStroke(page, surface, true);
    await expect(surface).toBeVisible();
    await expect(dialog.getByPlaceholder('مثال: حقل وادي سبأ')).toHaveCount(0);
    await drawStroke(page, surface);
    await dialog.getByPlaceholder('مثال: حقل وادي سبأ').fill('حقل التجربة');
    await dialog.getByPlaceholder('اسم المسؤول').fill('مدير التجربة');
    const saved = page.waitForRequest(req => req.method() === 'POST' && req.url().endsWith('/api/v1/fields'));
    await dialog.getByRole('button', { name: 'حفظ الحقل' }).click();
    const payload = (await saved).postDataJSON();
    expect(payload.geometry.type).toBe('Polygon');
    expect(payload.irrigation_type).toBeNull();
    const ring = payload.geometry.coordinates[0];
    expect(ring.length).toBeGreaterThanOrEqual(4);
    expect(ring[0]).toEqual(ring.at(-1));
    const toastClose = page.getByRole('button', { name: /إغلاق الإشعار.*حفظ|إغلاق الإشعار.*إضافة/ }).first();
    await toastClose.click();
    await expect(toastClose).toHaveCount(0);
  });
});

async function drawStroke(page: import('@playwright/test').Page, surface: import('@playwright/test').Locator, cancel = false) {
  await surface.scrollIntoViewIfNeeded();
  const box = (await surface.boundingBox())!;
  const x = Math.round(box.x + box.width * 0.4);
  const y = Math.round(box.y + box.height * 0.4);
  const touch = await page.context().newCDPSession(page);
  await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
  for (const [dx, dy] of [[30, 0], [60, 10], [64, 40], [34, 56], [4, 40], [0, 6]]) {
    await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x + dx, y: y + dy }] });
  }
  await touch.send('Input.dispatchTouchEvent', { type: cancel ? 'touchCancel' : 'touchEnd', touchPoints: [] });
  await touch.detach();
}
