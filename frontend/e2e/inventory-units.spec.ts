import { expect, test } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

const baseItem = { category: 'seed', unit: 'kg', reorder_level: 5 };

test('inventory shows separate batch quantities and preserves comparable and legacy stock', async ({ page }) => {
  await seedAuthAndRoutes(page, 'viewer');
  await page.route(url => url.pathname === '/api/v1/inventory/items', route => {
    expect(new URL(route.request().url()).searchParams.get('unit_breakdown')).toBe('true');
    return route.fulfill({ json: [
      { ...baseItem, item_id: 'mixed', name: 'صنف متعدد الوحدات', total_quantity: null, low_stock: null,
        quantities_by_unit: [{ unit: 'kg', quantity: 2 }, { unit: 'L', quantity: 1.25 }, { unit: null, quantity: 0.0001 }] },
      { ...baseItem, item_id: 'empty', name: 'صنف بلا دفعات', total_quantity: 0, low_stock: true, quantities_by_unit: [] },
      { ...baseItem, item_id: 'known', name: 'صنف بوحدة واحدة', total_quantity: 6, low_stock: false,
        quantities_by_unit: [{ unit: 'kg', quantity: 6 }] },
      { ...baseItem, item_id: 'legacy', name: 'صنف من خادم أقدم', total_quantity: 8, low_stock: false },
    ] });
  });
  await page.route(url => url.pathname === '/api/v1/inventory/expiring', route => route.fulfill({ json: [] }));
  await page.goto('/ops/inventory');
  const mixed = page.getByRole('row').filter({ hasText: 'صنف متعدد الوحدات' });
  await expect(mixed.getByRole('cell', { name: '2 kg · 1.25 L · 0.0001 وحدة غير محددة', exact: true })).toBeVisible();
  await expect(mixed.getByText('تعذّر تقييم حدّ الطلب')).toBeVisible();
  await expect(mixed.getByText('مخزون منخفض')).toHaveCount(0);
  for (const [item, amount] of [['صنف بلا دفعات', '0'], ['صنف بوحدة واحدة', '6'], ['صنف من خادم أقدم', '8']]) {
    const row = page.getByRole('row').filter({ hasText: item });
    await expect(row.getByRole('cell', { name: amount, exact: true })).toBeVisible();
    await expect(row.getByRole('cell', { name: 'kg', exact: true })).toBeVisible();
    await expect(row.getByText('مخزون منخفض')).toHaveCount(amount === '0' ? 1 : 0);
  }
});

test('the Arabic category choices submit the inventory API enum', async ({ page }) => {
  await seedAuthAndRoutes(page, 'manager');
  await page.route(url => url.pathname === '/api/v1/inventory/items', route =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 201, json: { item_id: 'seed-test' } })
      : route.fulfill({ json: [] }));
  await page.goto('/ops/inventory');
  await page.getByRole('button', { name: 'إضافة صنف', exact: true }).click();
  const form = page.getByRole('dialog');
  const select = form.getByRole('combobox', { name: /الفئة/ });
  const categories = [
    ['أسمدة', 'fertilizer'], ['مبيدات', 'pesticide'], ['بذور', 'seed'],
    ['قطع غيار', 'spare_part'], ['أخرى', 'other'],
  ];
  for (const [label, value] of categories) {
    await expect(select.getByRole('option', { name: label, exact: true })).toHaveAttribute('value', value);
  }
  await select.selectOption({ label: 'بذور' });
  await form.getByPlaceholder('مثال: يوريا 46%').fill('بذور الاختبار');
  const posted = page.waitForRequest(req => req.method() === 'POST' && new URL(req.url()).pathname === '/api/v1/inventory/items');
  await form.getByRole('button', { name: 'حفظ الصنف' }).click();
  expect((await posted).postDataJSON()).toMatchObject({ category: 'seed', name: 'بذور الاختبار' });
  await expect(form).toHaveCount(0);
});
