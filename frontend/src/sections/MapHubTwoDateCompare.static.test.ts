import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// حارس انحدار: زرّ «المقارنة» في MapHub يدعم **مقارنة زمنيّة حقيقيّة** — نفس المؤشّر
// بين تاريخَين مخزَّنَين مختلفَين — لا مؤشّرَين في تاريخ واحد فقط. النمط الافتراضيّ
// (مؤشّران) يبقى؛ نمط «تاريخان» يمرّر تاريخاً مستقلّاً لكلّ لوحة إلى CompareMap.
const mapHub = readFileSync(join(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');

describe('MapHub two-date temporal compare', () => {
  it('exposes a compare-mode toggle (indicators ↔ dates) defaulting to indicators', () => {
    expect(mapHub).toContain("useState<'indicators' | 'dates'>('indicators')");
    expect(mapHub).toContain('data-testid="compare-mode-toggle"');
  });

  it('keeps an independent right-pane date for the temporal compare', () => {
    expect(mapHub).toContain('compareRightDate');
    expect(mapHub).toContain('data-testid="compare-left-date"');
    expect(mapHub).toContain('data-testid="compare-right-date"');
  });

  it('in date mode compares the SAME indicator across the two selected dates', () => {
    // اللوحة اليمنى في نمط التواريخ تستعمل نفس المؤشّر (leftLayer) لكن تاريخ compareRightDate.
    expect(mapHub).toContain(
      "imageryDate={compareRightDate === 'latest' ? null : compareRightDate}",
    );
    expect(mapHub).toContain("compareMode === 'dates'");
  });
});
