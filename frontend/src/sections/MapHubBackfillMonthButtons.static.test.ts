import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// أزرار مدد الصور التاريخيّة في شاشة الأقمار: 3/6/12/24 شهراً، كلٌّ يرسل months نفسه.
const source = readFileSync(join(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');

describe('MapHub historical imagery month buttons', () => {
  it('offers 3, 6, 12 and 24 months', () => {
    expect(source).toContain('const BACKFILL_MONTH_OPTIONS = [3, 6, 12, 24] as const;');
    expect(source).toContain('data-testid="imagery-backfill-month-options"');
  });

  it('wires every month button to the backfill handler with its own value', () => {
    expect(source).toContain('onClick={() => handlePrepareTwoYearImagery(months)}');
    // الطلب يحمل months المختار (preset=custom) ويقصّ على حدّ الحقل.
    expect(source).toMatch(/preset: 'custom' as const,\s*months,/);
    expect(source).toContain('clip_polygon_geojson: selected.geometry');
  });

  it('disables the buttons only while busy or without a field geometry', () => {
    const at = source.indexOf('imagery-backfill-month-options');
    expect(at).toBeGreaterThan(-1);
    const block = source.slice(at);
    expect(block).toContain('disabled={historicalBackfillBusy || !selected?.geometry}');
  });

  it('widens the timeline window to the chosen months after a backfill', () => {
    expect(source).toContain('setTimelineMonths(months);');
    expect(source).toContain('{ includeProvider: true, months: timelineMonths }');
  });
});
