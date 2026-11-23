import { expect, test, type Page } from '@playwright/test';
import { expectReadableText } from './support/readability';
import { seedAuthAndRoutes } from './support/seed';

const chat = '**/api/ai-agronomist/chat';
const badge = 'ai-source-badge';

async function ask(page: Page) {
  const input = page.getByPlaceholder(/اسأل عن NDVI/);
  await input.fill('ما الأدلة المتاحة؟');
  await input.press('Enter');
}

for (const theme of ['light', 'dark', 'cream']) {
  test(`available sources and citations on the advisor card in ${theme}`, async ({ page }) => {
    await seedAuthAndRoutes(page);
    await page.addInitScript(t => localStorage.setItem('sahool-theme', t), theme);
    await page.route(chat, route => route.fulfill({ json: {
      answer_ar: 'تتوفر مراجع.',
      evidence_sources: [
        { key: 'rag', label_ar: 'المراجع', available: true, count: 2 },
        { key: 'kg', label_ar: 'رسم المعرفة', available: false, count: 0 },
        { key: 'legacy', label_ar: 'ذاكرة الحقل' },
      ],
      annotations: { rag: [
        { chunk_id: 'a', publisher: 'FAO', source_uri: 'https://example.org/water', page: 12, source_revision: '2021' },
        { chunk_id: 'b', source_uri: 'tenant-upload://tenant-7/field.pdf' },
      ] },
      rag_available: true,
      advisory: { requires_human_review: false },
      audit_event: { persisted: true },
    } }));
    await page.goto('/assistant');
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await expect(page.getByTestId(badge)).toHaveCount(0);
    await ask(page);

    const source = page.getByTestId(badge);
    const refs = page.getByTestId('ai-citations');
    const link = refs.getByRole('link', { name: 'FAO' });
    await expect(source).toHaveText('SAHOOL AI Runtime · المراجع');
    await expect(link).toHaveAttribute('href', 'https://example.org/water');
    await expect(refs.getByRole('listitem').first()).toContainText('ص 12 · مراجعة 2021');
    await expect(refs.getByRole('link')).toHaveCount(1);
    await expect(refs).not.toContainText('tenant-7');
    await expect(page.getByTestId('ai-rag-unavailable')).toHaveCount(0);
    await expect(page.getByTestId('ai-audit-not-persisted')).toHaveCount(0);
    await expect(page.getByTestId('ai-advisory-notices')).toHaveCount(0);
    for (const item of [source, link, refs.getByText('field.pdf')]) await expectReadableText(item);
    const unavailable = page.getByTestId('ai-evidence-sources').getByText(/رسم المعرفة/);
    await expect(unavailable).toHaveText('رسم المعرفة · 0 · غير متاح');
    await expect(page.getByTestId('ai-evidence-sources')).toContainText('ذاكرة الحقل · التوافر غير مؤكّد');
    await expectReadableText(unavailable);
  });
}

test('empty retrieval and a failed audit are explained alongside missing evidence', async ({ page }) => {
  await seedAuthAndRoutes(page);
  await page.route(chat, route => route.fulfill({ json: {
    answer_ar: 'بيانات غير كافية.',
    evidence_sources: [{ key: 'rag', available: false, count: 0 }],
    rag_available: false, rag_unavailable_reason: 'TENANT_CORPUS_EMPTY',
    annotations: { rag: [], unverified_seed_references: [{ chunk_id: 'withheld' }] },
    advisory: { requires_human_review: true, evidence_missing: ['no_grounding_evidence'] },
    audit_event: { status: 'failed', persisted: false },
  } }));
  await page.goto('/assistant');
  await ask(page);
  await expect(page.getByTestId(badge)).toHaveText('SAHOOL AI Runtime · بلا أدلّة متاحة');
  await expect(page.getByTestId('ai-citations')).toHaveCount(0);
  const review = page.getByTestId('ai-advisory-notices');
  for (const [id, text] of [
    ['ai-rag-unavailable', 'لا توجد قاعدة معرفة مراجَعة لهذا الحساب بعد'],
    ['ai-audit-not-persisted', 'لم يُحفَظ سجلّ تدقيق لهذه الإجابة.'],
    ['ai-unverified-references', '1 مرجع لم يُتحقَّق منه'],
  ]) {
    const notice = page.getByTestId(id);
    await expect(notice).toContainText(text);
    await expectReadableText(notice);
  }
  await expectReadableText(review.getByText(/تحتاج مراجعة مختص/));
  await expectReadableText(review.getByText(/لا دليل مرجعيّ يسند الإجابة/));
});

test('a legacy response requests review and only reports audit uncertainty when supplied', async ({ page }) => {
  await seedAuthAndRoutes(page);
  await page.route(chat, route => route.fulfill({ json: { answer_ar: 'إجابة قديمة.' } }));
  await page.goto('/assistant');
  await ask(page);
  await expect(page.getByTestId(badge)).toHaveText('SAHOOL AI Runtime · بلا أدلّة متاحة');
  await expect(page.getByTestId('ai-advisory-notices')).toContainText('تحتاج مراجعة مختص');
  await expect(page.getByTestId('ai-citations')).toHaveCount(0);
  await expect(page.getByTestId('ai-rag-unavailable')).toHaveCount(0);
  await expect(page.getByTestId('ai-audit-not-persisted')).toHaveCount(0);
  await page.route(chat, route => route.fulfill({ json: {
    answer_ar: 'إجابة أخرى.', audit_event: { status: 'unconfirmed' },
  } }));
  await ask(page);
  await expect(page.getByTestId(badge)).toHaveCount(2);
  await expect(page.getByTestId('ai-audit-not-persisted')).toHaveText('لم يتأكّد حفظ سجلّ تدقيق لهذه الإجابة.');
});

test('a failed chat request shows a readable warning without attributing sources', async ({ page }) => {
  await seedAuthAndRoutes(page);
  await page.route(chat, route => route.fulfill({ status: 503, json: {} }));
  await page.goto('/assistant');
  await ask(page);
  await expectReadableText(page.getByText('تعذّر جلب الأدلة', { exact: true }));
  await expect(page.getByTestId(badge)).toHaveCount(0);
  await expect(page.getByTestId('ai-citations')).toHaveCount(0);
});
