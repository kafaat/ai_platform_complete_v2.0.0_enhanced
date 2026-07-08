import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(join(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');
const api = readFileSync(join(process.cwd(), 'src/services/api.ts'), 'utf8');
const platformFields = readFileSync(join(process.cwd(), '../services/sahool-platform/api/routers/fields.py'), 'utf8');
const rasterClient = readFileSync(join(process.cwd(), '../services/sahool-platform/api/raster_service_client.py'), 'utf8');

describe('MapHub historical imagery timeline thumbnails', () => {
  it('keeps a separate all-index timeline so thumbnails are not limited to the active index/month', () => {
    expect(source).toContain('timelineImageryDates');
    expect(source).toContain('fetchFieldImageryAvailableDates(fieldId, undefined, 240)');
    expect(source).toContain('summarizeTwoYearTimeline(timelineImageryDates)');
    expect(source).toContain('dateSelectorDates');
  });

  it('selecting a thumbnail switches date without changing the active analytical index', () => {
    expect(source).toContain('handleSelectImageryTimelineItem');
    expect(source).toContain('onClick={() => handleSelectImageryTimelineItem(d.date, d)}');
    expect(source).toContain("imageryDate={selectedImageryDate === 'latest' ? null : selectedImageryDate}");
    expect(source).toContain('لا نغيّر المؤشر التحليلي المختار');
    expect(source).not.toContain('setActiveIndicator(preferredTimelineIndex');
  });

  it('renders truecolor cdse thumbnails for every returned historical date', () => {
    expect(source).toContain('fieldCdseThumbnailUrl');
    expect(source).toContain("'truecolor'");
    expect(source).toContain('data-testid="imagery-timeline-items"');
    expect(source).toContain('alt={`مصغّرة صورة الحقل ${d.date}`}');
    expect(source).toContain('monthLabel(d.date)');
    expect(source).not.toContain('preferredTimelineIndex(d, activeIndicator)');
  });


  it('offers explicit 3/6/12/24 month backfill options', () => {
    expect(source).toContain('BACKFILL_MONTH_OPTIONS = [3, 6, 12, 24]');
    expect(source).toContain('data-testid="imagery-backfill-month-options"');
    expect(source).toContain('handlePrepareTwoYearImagery(months)');
    expect(source).toContain('months,');
  });

  it('requests enough available dates through the platform proxy', () => {
    expect(api).toContain('limit = 240');
    expect(api).toContain('params: { ...(index ? { index } : {}), limit }');
    expect(platformFields).toContain('limit: int = Query(240, ge=1, le=500)');
    // P2 raster facade: بناء limit/index انتقل من fields.py إلى raster_service_client.get_available_dates
    expect(rasterClient).toContain('limit: int = 240,');
    expect(rasterClient).toContain('params: dict[str, Any] = {"limit": limit}');
    expect(rasterClient).toContain('params["index"] = index');
  });
});
