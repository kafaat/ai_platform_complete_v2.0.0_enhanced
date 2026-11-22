import { expect, test } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

// The circle-field and centre-pivot tools are first-class Arabic tools in the main map toolbar
// for roles that may edit fields (owner, manager), found by their accessible names.
test('the map toolbar offers the circle-field and centre-pivot tools to an owner', async ({ page }) => {
  await seedAuthAndRoutes(page, 'owner');
  await page.goto('/');
  const circle = page.getByRole('button', { name: 'حقل دائري' });
  await expect(circle).toBeVisible();
  // The pivot designer works on Leaflet (production). HubMapGL has no pivot click handler yet,
  // so the MapLibre build this config uses must not show an inert button.
  await expect(page.locator('.leaflet-container, .maplibregl-map').first()).toBeVisible();
  const leaflet = (await page.locator('.leaflet-container').count()) > 0;
  const pivot = page.getByRole('button', { name: 'تصميم الريّ المحوريّ' });
  if (leaflet) await expect(pivot).toBeVisible();
  else await expect(pivot).toHaveCount(0);
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
});
