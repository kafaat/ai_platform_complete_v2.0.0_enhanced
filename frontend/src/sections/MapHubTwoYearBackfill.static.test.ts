import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(join(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');
const api = readFileSync(join(process.cwd(), 'src/services/api.ts'), 'utf8');

describe('MapHub two-year historical imagery backfill UI', () => {
  it('exposes a visible 24-month historical imagery action', () => {
    expect(source).toContain('two-year-imagery-backfill');
    expect(source).toContain('تجهيز 24 شهر');
    expect(source).toContain('handlePrepareTwoYearImagery');
  });

  it('uses the platform-proxied backfill API with 24 months and field clipping geometry', () => {
    expect(source).toContain('runHistoricalImageryBackfill');
    expect(source).toContain('months,');
    expect(source).toContain('clip_polygon_geojson: selected.geometry');
    expect(source).toContain("preset: 'custom'");
  });

  it('keeps the API client pointed at the platform proxy historical backfill endpoint', () => {
    expect(api).toContain('/api/v1/fields/${fieldId}/imagery/backfill');
    expect(api).toContain('HistoricalImageryBackfillPayload');
  });

  it('renders actual cdse thumbnails inside the two-year timeline cards', () => {
    expect(source).toContain('fieldCdseThumbnailUrl');
    expect(source).toContain('alt={`مصغّرة صورة الحقل ${d.date}`}');
    expect(source).toContain('data-testid="imagery-timeline-items"');
  });

  // Regression: all MapHub-visible CDSE layers that users expect to persist historically
  // must be allowed into backfill. salinity is a UI alias and must be sent to raster-service
  // as its backend IndicatorKind value, ndsi.
  it('includes core thumbnails and advanced top-20 indices in persisted historical backfill', () => {
    const handler = source.slice(source.indexOf('handlePrepareTwoYearImagery'));
    const payloadStart = handler.indexOf('const payload');
    const indicesBlock = handler.slice(0, payloadStart);
    expect(indicesBlock).toContain('BACKFILL_SUPPORTED_INDICES');
    expect(indicesBlock).toContain('RAW_IMAGERY_INDEX_ID');
    for (const idx of ['ndwi', 'salinity', 'reci', 'gci', 'arvi', 'sipi', 'nbr', 'ccci', 'vari', 'gli', 'bsi']) {
      expect(indicesBlock).toContain(`'${idx}'`);
    }
    expect(source).toContain('CORE_TIMELINE_THUMBNAIL_INDEX_IDS');
    expect(source).toContain('ADVANCED_ANALYSIS_INDEX_IDS');
    expect(indicesBlock).toContain("idx === 'salinity' ? 'ndsi' : idx");
  });
});
