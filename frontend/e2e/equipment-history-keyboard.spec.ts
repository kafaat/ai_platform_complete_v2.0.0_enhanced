import { expect, test } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

test('keyboard and pointer can open and close equipment maintenance history', async ({ page }) => {
  await seedAuthAndRoutes(page, 'viewer');
  const equipment = {
    equipment_id: 'pump-test', name: 'مضخة الاختبار', type: 'pump',
    status: 'active', operating_hours: 18, purchase_date: null,
  };
  const summary = {
    assets: [equipment],
    intelligence: {
      schema_version: 'equipment_intelligence.v2', readiness: 'unknown', total_assets: 1,
      unavailable: 0, assessment_coverage: 0, service_due: 0, service_not_due: 0,
      service_not_evaluated: 1,
      assessments: [{
        asset_id: equipment.equipment_id, status: 'not_evaluated', basis: null,
        constraints: ['maintenance_policy_missing'],
      }],
    },
  };
  await page.route(url => url.pathname === '/api/v1/equipment', route => {
    const wantsSummary = new URL(route.request().url()).searchParams.get('summary') === 'true';
    return route.fulfill({ json: wantsSummary ? summary : [equipment] });
  });
  const maintenance = '/api/v1/equipment/pump-test/maintenance';
  const record = {
    maintenance_id: 'm-test', kind: 'inspection', status: 'done', scheduled_date: null,
    performed_date: '2026-09-15', cost_usd: 3.75, notes: 'فحص المرشح التجريبي',
  };
  await page.route(url => url.pathname === maintenance, route => route.fulfill({ json: [record] }));

  await page.goto('/ops/equipment');
  const row = page.getByRole('row').filter({ hasText: equipment.name });
  await expect(row).toBeVisible();
  const toggle = row.getByRole('button', { name: equipment.name, exact: true });
  await expect(toggle).toBeVisible();
  await toggle.focus();
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Tab');
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');

  const request = page.waitForRequest(req => new URL(req.url()).pathname === maintenance && req.method() === 'GET');
  await page.keyboard.press('Enter');
  await request;
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  const notes = page.getByText(record.notes, { exact: true });
  await expect(notes).toBeVisible();
  await expect(page.getByText('$3.75', { exact: true })).toBeVisible();

  await page.keyboard.press('Space');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(notes).toHaveCount(0);
  await row.getByRole('cell').last().click();
  await expect(notes).toBeVisible();
  await toggle.click();
  await expect(notes).toHaveCount(0);
});
