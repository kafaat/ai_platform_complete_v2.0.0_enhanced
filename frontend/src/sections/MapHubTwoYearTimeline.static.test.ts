import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(join(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');

describe('MapHub two-year imagery timeline', () => {
  it('adds a visible historical imagery timeline toggle and panel', () => {
    expect(source).toContain('two-year-imagery-timeline-toggle');
    expect(source).toContain('two-year-imagery-timeline');
    expect(source).toContain('Timeline الصور الجوية · السلسلة التاريخية');
  });

  it('lets the server bound the timeline range instead of a brittle client-side cutoff', () => {
    // العرض البصري لا يقتصر على «آخر سنتين» بقصٍّ عميلٍ صلب؛ يعرض كل التواريخ الجاهزة
    // التي أرجعها الخادم حتى حدّ الـlimit/السنتين — الخادم يحدّد النطاق الزمني الفعليّ.
    expect(source).toContain('summarizeTwoYearTimeline');
    expect(source).not.toContain('730 * 24 * 60 * 60 * 1000');
    expect(source).toContain('الخادم يحدّد النطاق الزمني الفعلي');
  });

  it('surfaces scene readiness and cloud cover in the timeline UI', () => {
    expect(source).toContain('cloudBandColor');
    expect(source).toContain('جاهز');
    expect(source).toContain('ينتظر COG');
    expect(source).toContain('متوسط غيوم');
  });
});


describe('TIMELINE-PROVIDER-DATES — محور الالتقاط الحقيقيّ من المزوّد (طلب 2026-07-12)', () => {
  const maphub = source;
  const api = readFileSync(join(process.cwd(), 'src/services/api.ts'), 'utf8');
  const rasterRouter = readFileSync(
    join(process.cwd(), '../services/raster-service/routers/fields.py'),
    'utf8',
  );

  it('timeline fetch merges provider capture dates for the SELECTED indicator', () => {
    // كلا موضعَي الجلب (الأوّليّ + تحديث ما-بعد-backfill) يطلبان تواريخ المزوّد.
    expect(maphub.split('includeProvider: true').length - 1).toBeGreaterThanOrEqual(2);
    expect(api).toContain('include_provider: true');
  });

  it('timeline window follows the selected period (3/6/12/24) — not a hardcoded 24 months', () => {
    // إصلاح 2026-07-13: زرّ الفترة يقود نافذة الشريط عبر حالة timelineMonths، فلا
    // يُسحَب 24 شهراً دائماً. الجلب الأوّليّ يمرّر timelineMonths؛ تحديث ما-بعد-backfill
    // يمرّر months (الفترة المختارة)؛ والمعالِج يضبط setTimelineMonths(months).
    expect(maphub).toContain('const [timelineMonths, setTimelineMonths]');
    expect(maphub).toContain('includeProvider: true, months: timelineMonths');
    expect(maphub).toContain('setTimelineMonths(months)');
    expect(maphub).not.toContain('{ includeProvider: true, months: 24 }');
  });

  it('raster endpoint merges STAC capture dates honestly (has_cog=false, declared errors)', () => {
    expect(rasterRouter).toContain('include_provider: bool = Query(');
    expect(rasterRouter).toContain('fetch_field_geometry');
    expect(rasterRouter).toContain('provider_dates_error');
    // غير المعالَج يُضاف has_cog=False — لا ادّعاء جاهزيّة.
    expect(rasterRouter).toContain('has_cog=False');
  });

  it('pending provider dates render with their capture date and no fake readiness', () => {
    expect(maphub).toContain("d.has_cog ? 'جاهز' : 'ينتظر COG'");
  });
});
