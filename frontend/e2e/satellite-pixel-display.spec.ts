import { expect, test } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

// Two vertical colour cells in a 2×1 PNG. Scaling it to a 256 px tile reveals
// a smoothed transition immediately, without contacting the imagery provider.
const TILE = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAD0lEQVR4nGNg+M9wR5cLAAf6AhMZjzUOAAAAAElFTkSuQmCC', 'base64');

test('satellite indicator tiles stay pixelated while the basemap keeps its own rendering', async ({ page }) => {
  await seedAuthAndRoutes(page);
  await page.route(/\/(?:cdse-)?tilejson(?:\?|$)/, (route) => route.fulfill({ json: { available: true } }));
  await page.route(/\/(?:cdse-)?tiles\//, (route) => route.fulfill({ contentType: 'image/png', body: TILE }));
  await page.goto('/health/satellite');

  const overlay = page.locator('.sahool-indicator-pixels img.leaflet-tile-loaded').first();
  const base = page.locator('.leaflet-layer:not(.sahool-indicator-pixels) img.leaflet-tile-loaded').first();
  await expect(overlay).toHaveCSS('image-rendering', 'pixelated');
  await expect(base).not.toHaveCSS('image-rendering', 'pixelated');
  expect(await overlay.evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBe(2);
});
