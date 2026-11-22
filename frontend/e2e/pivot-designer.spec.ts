import { expect, test, type Page } from '@playwright/test';
import type { Map as GLMap } from 'maplibre-gl';
import { FIELDS } from './fixtures/fields';
import { seedAuthAndRoutes } from './support/seed';

const designerName = 'تصميم الريّ المحوريّ';
const placeName = 'وضع المحوري في مركز الخريطة';

async function openMap(page: Page, role: string, gl: boolean, fields = FIELDS) {
  await seedAuthAndRoutes(page, role);
  await page.route((url) => url.pathname === '/api/v1/fields', (route) => route.fulfill({ json: fields }));
  await page.goto('/fields/map-center');
  await page.getByTestId(`field-${FIELDS[0].field_id}`).click();
  const surface = page.locator(gl ? '.maplibregl-canvas' : '.leaflet-map.leaflet-container');
  await expect(surface).toBeVisible();
  await surface.scrollIntoViewIfNeeded();
  if (gl) await page.waitForFunction(() => Boolean(window.__hubmap?.getMap()));
  return surface;
}

declare global {
  interface Window {
    __hubmap?: { getMap: () => GLMap };
  }
}

async function expectPolygons(page: Page, gl: boolean, count: number) {
  if (gl) {
    await expect.poll(() => page.evaluate(() => {
      const map = window.__hubmap?.getMap();
      const layer = 'sahool-drawings-fill';
      if (!map?.getLayer(layer)) return 0;
      const features = map.queryRenderedFeatures({ layers: [layer] });
      return new Set(features.map((f) => f.id)).size;
    })).toBe(count);
  } else {
    await expect(page.locator('.leaflet-overlay-pane path[stroke="#38bdf8"]')).toHaveCount(count);
  }
}

for (const role of ['owner', 'manager']) {
  test(`${role} places, views and clears scoped pivot drafts`, async ({ page }, info) => {
    const gl = info.config.metadata.mapEngine === 'maplibre';
    const surface = await openMap(page, role, gl);
    const toggle = page.getByRole('button', { name: designerName, exact: true });
    await toggle.press('Enter');
    await expect(toggle).toHaveAttribute('aria-pressed', 'true');
    const status = page.getByTestId('pivot-designer-panel').getByRole('status');
    await surface.click();
    await expect(status).toHaveText('1 تصميم');
    await expectPolygons(page, gl, 1);

    // Keyboard placement uses the map's current viewport center after a pan.
    await surface.press('ArrowRight');
    await page.getByRole('button', { name: placeName }).press('Enter');
    await expect(status).toHaveText('2 تصميم');
    await expectPolygons(page, gl, 2);

    await page.getByTestId(`field-${FIELDS[1].field_id}`).click();
    await expect(status).toHaveText('0 تصميم');
    await expectPolygons(page, gl, 0);
    await page.getByTestId(`field-${FIELDS[0].field_id}`).click();
    await expect(status).toHaveText('2 تصميم');
    await expectPolygons(page, gl, 2);
    await page.getByTestId('btn-pivots').click();
    await expectPolygons(page, gl, 0);
    await page.getByTestId('btn-pivots').click();
    await page.getByTestId('basemap-switcher').getByRole('button', { name: 'خريطة فاتحة' }).click();
    await expectPolygons(page, gl, 2);

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await surface.click();
    await expect(status).toHaveText('2 تصميم');
    await page.getByRole('button', { name: 'مسح تصاميم Pivot' }).click();
    await expectPolygons(page, gl, 0);
    await expect(page.getByTestId('btn-save-pivot-drafts')).toHaveCount(0);
  });
}

test('a click over another field places one design on the selected field', async ({ page }, info) => {
  const gl = info.config.metadata.mapEngine === 'maplibre';
  // Put the second field on top of the selected one to exercise both click handlers.
  const [selected, other] = FIELDS;
  const surface = await openMap(page, 'owner', gl, [selected, { ...other, geometry: selected.geometry }]);
  const toggle = page.getByRole('button', { name: designerName });
  await toggle.click();
  await page.getByRole('spinbutton', { name: 'نصف القطر م' }).fill('320');
  await surface.click();
  await expectPolygons(page, gl, 1);
  await page.route('**/api/v1/drawing-features', (route) => route.fulfill({ json: route.request().postDataJSON() }));
  const request = page.waitForRequest((r) => r.method() === 'POST' && r.url().endsWith('/drawing-features'));
  await page.getByTestId('btn-save-pivot-drafts').click();
  const feature = (await request).postDataJSON();
  expect(feature.properties).toMatchObject({ fieldId: selected.field_id, pivot: { radius_m: 320 } });
  expect(feature.properties.pivot.center.lat).toBeCloseTo(selected.centroid_lat, 1);
  expect(feature.properties.pivot.center.lon).toBeCloseTo(selected.centroid_lon, 1);
  expect(feature.properties).not.toHaveProperty('localOwnerScope');
  await expect(page.getByTestId('btn-save-pivot-drafts')).toHaveCount(0);
  await expectPolygons(page, gl, 1);
});

for (const role of ['viewer', 'worker', 'agronomist']) {
  test(`${role} can view the map but cannot place a pivot`, async ({ page }, info) => {
    const gl = info.config.metadata.mapEngine === 'maplibre';
    const surface = await openMap(page, role, gl);
    await expect(page.getByRole('button', { name: designerName })).toHaveCount(0);
    await page.getByTestId('btn-pivots').click();
    await surface.click();
    await expect(page.getByRole('button', { name: placeName })).toHaveCount(0);
    await expect(page.getByTestId('pivot-designer-panel')).toHaveCount(0);
    await expectPolygons(page, gl, 0);
  });
}

test('changing the session owner discards the previous drafts on the mounted map', async ({ page }, info) => {
  const gl = info.config.metadata.mapEngine === 'maplibre';
  const surface = await openMap(page, 'manager', gl);
  const toggle = page.getByRole('button', { name: designerName });
  await toggle.click();
  await surface.click();
  await expectPolygons(page, gl, 1);

  // Exercise scope changes without a navigation that would trivially drop all React state.
  await page.evaluate(() => {
    const user = JSON.parse(sessionStorage.getItem('sahool_user')!);
    sessionStorage.setItem('sahool_user', JSON.stringify({ ...user, id: 2 }));
  });
  await page.getByTestId('btn-pivots').click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await toggle.click();
  await expect(page.getByTestId('pivot-designer-panel').getByRole('status')).toHaveText('0 تصميم');
  await expectPolygons(page, gl, 0);
});
