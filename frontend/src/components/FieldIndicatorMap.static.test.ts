import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const SRC = readFileSync(resolve(__dirname, 'FieldIndicatorMap.tsx'), 'utf8');

describe('FieldIndicatorMap raster tile contract', () => {
  it('passes tenant id in TileJSON query and tile image URL', () => {
    expect(SRC).toContain('getTenantId()');
    expect(SRC).toContain('fieldIndicatorTileUrl(fieldId, normalizedIndex, date, tenantId, tileCacheVersion)');
    expect(SRC).toContain('...(tenantId ? { tid: tenantId } : {})');
  });

  it('does not mount indicator tiles when TileJSON is unavailable or available=false', () => {
    expect(SRC).toContain('setTileAvailable(false)');
    expect(SRC).toContain('r.data?.available === false');
    expect(SRC).toContain('tileAvailable === true &&');
  });

  it('shows indicator availability state before mounting tiles', () => {
    expect(SRC).toContain('indicator availability status');
    expect(SRC).toContain('جاري التحقق');
    expect(SRC).toContain('غير متاح');
    expect(SRC).toContain('متاح:');
  });

  it('keeps field boundary visible independently from indicator tile availability', () => {
    const polygonBlock = SRC.slice(SRC.indexOf('{fieldPolygon && fieldPolygon.length >= 3'), SRC.indexOf('{tools &&'));
    expect(polygonBlock).toContain('<Polygon');
    expect(polygonBlock).toContain('positions={fieldPolygon}');
  });
});
