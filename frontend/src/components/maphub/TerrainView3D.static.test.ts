import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(
  resolve(__dirname, 'TerrainView3D.tsx'),
  'utf8',
);

describe('TerrainView3D — computed terrain from real DEM (honest)', () => {
  it('fetches computed field terrain via the shared hook', () => {
    expect(source).toContain("import { useFieldTerrain } from '../../hooks/useApi'");
    expect(source).toContain('useFieldTerrain(fieldId)');
  });

  it('prefers server-computed stats and shows an honest reason when not computed', () => {
    expect(source).toContain('t?.computed');
    // honest fail-closed messaging — no fabricated numbers.
    expect(source).toContain("'dem-not-configured'");
    expect(source).toContain('غير مُهيّأ');
    expect(source).toContain('water_harvesting');
  });

  it('keeps 3D terrain-RGB rendering an explicit pending state (no fake relief)', () => {
    expect(source).toContain('بانتظار مصدر بلاطات DEM');
  });
});
