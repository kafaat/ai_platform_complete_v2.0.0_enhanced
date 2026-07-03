import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(join(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');
const api = readFileSync(join(process.cwd(), 'src/services/api.ts'), 'utf8');

describe('MapHub two-year historical imagery backfill UI', () => {
  it('exposes a visible 24-month historical imagery action', () => {
    expect(source).toContain('two-year-imagery-backfill');
    expect(source).toContain('تجهيز سنتين تاريخية');
    expect(source).toContain('handlePrepareTwoYearImagery');
  });

  it('uses the platform-proxied backfill API with 24 months and field clipping geometry', () => {
    expect(source).toContain('runHistoricalImageryBackfill');
    expect(source).toContain('months: 24');
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

  // Regression: the raster-service backfill contract types `indices` as list[IndicatorKind],
  // which has NO 'truecolor' member (it is a rendering of the base scene, not an index) and
  // the handler only accepts a vegetation-index subset. Sending 'truecolor' 422s every call.
  it('does not send truecolor/raw as a backfill index (raster IndicatorKind contract)', () => {
    const handler = source.slice(source.indexOf('handlePrepareTwoYearImagery'));
    const payloadStart = handler.indexOf('const payload');
    const indicesBlock = handler.slice(0, payloadStart);
    // The indices array fed to the payload must be filtered to the supported set...
    expect(indicesBlock).toContain('BACKFILL_SUPPORTED_INDICES');
    // ...and must NOT unconditionally include the literal 'truecolor' entry.
    expect(indicesBlock).not.toContain("'truecolor', 'ndvi', 'ndmi'");
  });
});
