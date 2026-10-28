import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { dateHasPersistedCog } from './persistedCog';

// P2-FE-1 — مصدر البلاطات (COG المحفوظ /tiles مقابل CDSE الحيّ /cdse-tiles) يجب أن يُشتقّ
// بنفس القاعدة لكلّ لوحة تعرض (مؤشّر، تاريخ): العرض المفرد ولوحتا المقارنة. كانت
// CompareMap لا تستقبل preferPersistedCog فتسقط دائماً إلى /cdse-tiles حتّى لتاريخ له COG.
const DATES = [
  { date: '2026-05-22', has_cog: true, indices: ['NDVI', 'NDMI', 'NDSI'] },
  { date: '2026-05-07', has_cog: true, indices: ['NDVI'] },
  { date: '2026-04-20', has_cog: false, indices: [] },
];

describe('dateHasPersistedCog — one rule for single and compare views', () => {
  it('true only when the date has a COG that explicitly lists the indicator', () => {
    expect(dateHasPersistedCog('ndvi', '2026-05-07', DATES)).toBe(true);
    expect(dateHasPersistedCog('ndmi', '2026-05-07', DATES)).toBe(false);
    expect(dateHasPersistedCog('ndvi', '2026-04-20', DATES)).toBe(false);
    expect(dateHasPersistedCog('ndvi', '2026-01-01', DATES)).toBe(false);
  });

  it('salinity is persisted under the NDSI name', () => {
    expect(dateHasPersistedCog('salinity', '2026-05-22', DATES)).toBe(true);
    expect(dateHasPersistedCog('salinity', '2026-05-07', DATES)).toBe(false);
  });

  it("'latest' / null means any persisted date for the indicator", () => {
    expect(dateHasPersistedCog('ndmi', 'latest', DATES)).toBe(true);
    expect(dateHasPersistedCog('ndmi', null, DATES)).toBe(true);
    expect(dateHasPersistedCog('ndre', 'latest', DATES)).toBe(false);
  });

  it('no indicator / empty indices never switches to /tiles', () => {
    expect(dateHasPersistedCog(null, '2026-05-22', DATES)).toBe(false);
    expect(dateHasPersistedCog('ndvi', '2026-05-22', [{ date: '2026-05-22', has_cog: true }])).toBe(false);
  });
});

describe('MapHub compare panes carry the persisted-COG source decision', () => {
  const mapHub = readFileSync(join(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');
  const compareFn = mapHub.slice(mapHub.indexOf('function CompareMap('));

  it('CompareMap accepts preferPersistedCog and forwards it to HubMap', () => {
    const sig = compareFn.slice(0, compareFn.indexOf('{\n  const legend'));
    expect(sig).toContain('preferPersistedCog');
    expect(compareFn).toContain('preferPersistedCog={preferPersistedCog');
  });

  it('every <CompareMap> passes a per-pane preferPersistedCog', () => {
    const uses = mapHub.match(/<CompareMap [^>]*\/>/g) ?? [];
    expect(uses.length).toBe(4);
    for (const u of uses) expect(u).toContain('preferPersistedCog={');
  });

  it('the temporal (dates) right pane derives its source from compareRightDate', () => {
    expect(mapHub).toContain('dateHasPersistedCog(leftLayer, compareRightDate, availableImageryDates)');
  });
});
