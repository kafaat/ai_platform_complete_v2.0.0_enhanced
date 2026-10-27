import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { cellCenterLonLat, utmToLonLat, zoneSamplePoint, type GridGeoInput } from './indicatorGridGeo';

// P3-CON-2 — نقطة أخذ العيّنة لمنطقة indicator-grid:
//   (أ) تُحسَب من تحويل الشبكة (grid_identity.transform بنظام CRS المصدر) لا باستيفاء
//       خطّيّ على bbox (غلاف مُحوَّل فقط؛ خاطئ لشبكة مُدارة/مُسقَطة)؛
//   (ب) تقع في خلية **صالحة** من خلايا المنطقة نفسها — متوسّط مواضع خلايا متفرّقة قد يقع
//       في خلية بلا بيانات (null) أو خارج الحقل.

function base(over: Partial<GridGeoInput>): GridGeoInput {
  return {
    bbox: [0, 0, 2, 2],
    rows: 2,
    cols: 2,
    grid: [[0.1, 0.2], [0.3, 0.4]],
    grid_identity: null,
    ...over,
  };
}

describe('cellCenterLonLat — grid transform, not bbox interpolation', () => {
  it('applies a rotated EPSG:4326 affine to the cell centre (audit witness: 1.75 not 2.25)', () => {
    const resp = base({
      bbox: [0, 0, 3, 3],
      grid_identity: { crs: 'EPSG:4326', transform: [1, 0.5, 0, 0.5, -1, 2], rows: 2, cols: 2 },
    });
    const p = cellCenterLonLat(resp, 0, 0);
    expect(p).not.toBeNull();
    expect(p!.method).toBe('affine');
    expect(p!.lon).toBeCloseTo(0.75, 12);
    expect(p!.lat).toBeCloseTo(1.75, 12);
  });

  it('north-up geographic grid without identity keeps the exact bbox centre (positive control)', () => {
    const p = cellCenterLonLat(base({}), 0, 0);
    expect(p!.method).toBe('bbox');
    expect(p!.lon).toBeCloseTo(0.5, 12);
    expect(p!.lat).toBeCloseTo(1.5, 12);
  });

  it('projects a UTM (EPSG:32638) grid through the transform to WGS84', () => {
    // خلية 10م في UTM 38N؛ مركز الخلية (0,0) = (532000, 1786000) — مرجع pyproj 3.7.2.
    const resp = base({
      bbox: [45.29, 16.15, 45.31, 16.16],
      grid_identity: { crs: 'EPSG:32638', transform: [10, 0, 531995, 0, -10, 1786005], rows: 2, cols: 2 },
    });
    const p = cellCenterLonLat(resp, 0, 0);
    expect(p!.method).toBe('affine');
    expect(p!.lon).toBeCloseTo(45.29931825, 7);
    expect(p!.lat).toBeCloseTo(16.154059891, 7);
  });

  it('identity whose shape does not match the grid is not trusted', () => {
    const resp = base({
      grid_identity: { crs: 'EPSG:4326', transform: [1, 0.5, 0, 0.5, -1, 2], rows: 4, cols: 4 },
    });
    expect(cellCenterLonLat(resp, 0, 0)!.method).toBe('bbox');
  });
});

describe('utmToLonLat — WGS84 transverse Mercator inverse (reference: pyproj 3.7.2)', () => {
  it.each([
    [32638, 532000.0, 1786000.0, 45.29931825, 16.154059891],
    [32638, 470123.4, 1790555.5, 44.720485303, 16.1952693],
    [32637, 780000.0, 1700000.0, 41.608125132, 15.361507201],
    [32738, 450000.0, 9100000.0, 44.546122541, -8.141780441],
  ])('EPSG:%i (%f, %f)', (epsg, e, n, lon, lat) => {
    const p = utmToLonLat(epsg, e, n);
    expect(p).not.toBeNull();
    // ‎1e-7° ≈ 1 سم — أدقّ بكثير من خلية 10م.
    expect(Math.abs(p![0] - lon)).toBeLessThan(1e-7);
    expect(Math.abs(p![1] - lat)).toBeLessThan(1e-7);
  });

  it('rejects non-UTM EPSG codes', () => {
    expect(utmToLonLat(3857, 0, 0)).toBeNull();
  });
});

describe('zoneSamplePoint — a valid cell inside the zone', () => {
  it('never lands in a null cell between two disjoint severe cells (audit witness)', () => {
    const resp = base({ bbox: [0, 0, 3, 1], rows: 1, cols: 3, grid: [[-0.2, null, -0.3]] });
    const p = zoneSamplePoint(resp, [[0, 0], [0, 2]]);
    expect(p).not.toBeNull();
    const [r, c] = p!.cell;
    expect(resp.grid[r][c]).not.toBeNull();
    expect([[0, 0], [0, 2]]).toContainEqual([r, c]);
    // إحداثيّ مركز الخليّة المختارة (لا 1.5 الواقع في العمود الفارغ).
    expect(p!.lon === 0.5 || p!.lon === 2.5).toBe(true);
    expect(p!.lat).toBeCloseTo(0.5, 12);
  });

  it('picks the valid zone cell nearest to the zone mean position', () => {
    const resp = base({
      bbox: [0, 0, 3, 3], rows: 3, cols: 3,
      grid: [[0.1, 0.1, 0.1], [0.1, 0.1, 0.1], [0.1, 0.1, 0.1]],
    });
    // حلقة حول المركز: المتوسّط (1,1) ليس من خلايا المنطقة ⇒ نختار أقرب خليّة منها.
    const ring: [number, number][] = [[0, 1], [1, 0], [1, 2], [2, 1]];
    const p = zoneSamplePoint(resp, ring);
    expect(ring).toContainEqual(p!.cell);
  });

  it('skips zone cells that the grid marks as nodata and returns null when none is valid', () => {
    const resp = base({ grid: [[null, 0.2], [null, null]] });
    expect(zoneSamplePoint(resp, [[0, 0], [1, 1], [0, 1]])!.cell).toEqual([0, 1]);
    expect(zoneSamplePoint(resp, [[0, 0], [1, 1]])).toBeNull();
    expect(zoneSamplePoint(resp, [])).toBeNull();
  });
});

describe('SpatialIndicatorsPage uses the transform-aware valid-cell sample point', () => {
  const src = readFileSync(join(process.cwd(), 'src/sections/SpatialIndicatorsPage.tsx'), 'utf8');
  it('mapApiZones delegates to zoneSamplePoint (no centroid-on-bbox interpolation)', () => {
    const body = src.slice(src.indexOf('function mapApiZones'), src.indexOf('// لون البكسل'));
    expect(body).toContain('zoneSamplePoint(');
    expect(body).not.toContain('(cc + 0.5) / cols');
    expect(body).not.toContain('(cr + 0.5) / rows');
  });
});
