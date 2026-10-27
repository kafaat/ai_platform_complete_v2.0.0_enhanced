import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { GRID_SEVERITY_COLOR, gridSeverityColor } from './indicatorGridSeverity';

// P3-CON-1 — دلالة شدّة مناطق indicator-grid: `severity` في استجابة raster-service هي
// **شدّة المشكلة** لا كمّيّة المؤشّر (indicator_grid.classify_zones: لـNDMI القيمة < 0
// ⇒ high، و≥ 0.3 ⇒ low). كانت AnalyticsPage تلوّن low بالأحمر وhigh بالأخضر فتعكس
// دلالة الخطر: NDMI -0.2 (جفاف شديد) يظهر أخضر و+0.6 (رطب) يظهر أحمر.
const RED = '#dc2626';
const GREEN = '#16a34a';

describe('indicator-grid severity colours (high = red, low = green)', () => {
  it('maps problem severity to danger colours', () => {
    expect(gridSeverityColor('high')).toBe(RED);
    expect(gridSeverityColor('low')).toBe(GREEN);
    expect(gridSeverityColor('medium')).toBe(GRID_SEVERITY_COLOR.medium);
    expect(GRID_SEVERITY_COLOR.medium).not.toBe(RED);
    expect(GRID_SEVERITY_COLOR.medium).not.toBe(GREEN);
  });

  it('NDMI zones as the backend emits them: dry (-0.2, high) is red, moist (+0.6, low) is green', () => {
    // أشكال مطابقة لعقد classify_zones (id/severity/mean/cells).
    const dry = { id: 'zone_high', severity: 'high' as const, mean: -0.2, cells: [[0, 0]] };
    const moist = { id: 'zone_low', severity: 'low' as const, mean: 0.6, cells: [[0, 1]] };
    expect(gridSeverityColor(dry.severity)).toBe(RED);
    expect(gridSeverityColor(moist.severity)).toBe(GREEN);
  });

  it('unknown severity is neutral, never a health colour', () => {
    expect(gridSeverityColor(undefined)).not.toBe(GREEN);
    expect(gridSeverityColor('bogus')).not.toBe(RED);
    expect(gridSeverityColor('bogus')).not.toBe(GREEN);
  });

  it('AnalyticsPage colours NDMI zone bars through the shared severity map (no inverted local map)', () => {
    const src = readFileSync(join(process.cwd(), 'src/sections/AnalyticsPage.tsx'), 'utf8');
    expect(src).toContain('gridSeverityColor(z.severity)');
    expect(src).not.toMatch(/low:\s*'#dc2626'/);
    expect(src).not.toMatch(/high:\s*'#16a34a'/);
  });
});
